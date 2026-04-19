"""
FastAPI adapter – adaptador de entrada REST.
Expone POST /api/v1/vehicle-recommendation con validación Pydantic
y documentación OpenAPI automática.
"""
from __future__ import annotations
import logging
import os
from datetime import date
from typing import Annotated, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator, model_validator
import uuid

from src.core.domain.models import (
    Canal, Cliente, Pedido, Prioridad, Producto,
    SolicitudRecomendacion, TipoVehiculo, VehiculoDisponible,
)
from src.core.services.recommendation_service import RecommendationService
from src.config import get_settings, build_recommendation_service, build_recommendation_service_with_llm

logger = logging.getLogger(__name__)

# ── Pydantic schemas de entrada ───────────────────────────────

class PedidoSchema(BaseModel):
    identificador: str = Field(..., min_length=1, description="ID alfanumérico del pedido")
    fecha_entrega: date = Field(..., description="Fecha ISO 8601")
    prioridad: Prioridad


class ProductoSchema(BaseModel):
    nombre: str = Field(..., min_length=1)
    cantidad: float = Field(..., gt=0)
    unidad: str = Field(..., pattern="^(kg|ton|unidades)$")


class ClienteSchema(BaseModel):
    nombre: str = Field(..., min_length=1)
    direccion: str = Field(..., min_length=5)
    latitud: float = Field(..., ge=-4.5, le=13.0)   # rango Colombia
    longitud: float = Field(..., ge=-81.0, le=-66.0)


class VehiculoSchema(BaseModel):
    id: str = Field(..., min_length=1)
    tipo: TipoVehiculo
    capacidad_kg: float = Field(..., gt=0)
    refrigerado: bool
    matricula: Optional[str] = None


class RecomendacionRequest(BaseModel):
    pedido: PedidoSchema
    productos: list[ProductoSchema] = Field(..., min_length=1)
    cliente: ClienteSchema
    canal: Canal
    flota_disponible: list[VehiculoSchema] = Field(..., min_length=1)
    llm_provider: Optional[str] = Field(
        None,
        description="Proveedor LLM a usar: anthropic, openai, google, ollama. Si no se especifica, usa el configurado en el servidor.",
    )

    @model_validator(mode="after")
    def ids_unicos(self):
        ids = [v.id for v in self.flota_disponible]
        if len(ids) != len(set(ids)):
            raise ValueError("Los IDs de la flota_disponible deben ser únicos.")
        return self


# ── Pydantic schemas de salida ────────────────────────────────

class VehiculoRecomendadoSchema(BaseModel):
    id: str
    tipo: str
    matricula: Optional[str]


class AlternativaSchema(BaseModel):
    id: str
    motivo: str


class AlertaSchema(BaseModel):
    nivel: str
    mensaje: str


class DesgloseCostoSchema(BaseModel):
    combustible_cop: float
    peajes_cop: float
    viaticos_cop: float
    seguro_cop: float
    imprevistos_cop: float
    total_cop: float


class RecomendacionResponse(BaseModel):
    trace_id: str
    vehiculo_recomendado: VehiculoRecomendadoSchema
    justificacion: str
    alternativas: list[AlternativaSchema]
    alertas: list[AlertaSchema]
    costo_estimado_cop: float
    desglose_costo: DesgloseCostoSchema
    tiempo_estimado_min: int


# ── Aplicación FastAPI ────────────────────────────────────────

def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="API RAG – Selección Inteligente de Vehículo",
        description=(
            "API agnóstica al consumidor para recomendar el vehículo óptimo "
            "de transporte agrícola usando Retrieval-Augmented Generation."
        ),
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # ── Dependencia: servicios cacheados por proveedor LLM ───
    _services: dict[str, RecommendationService] = {}

    def get_service(llm_provider: str | None = None) -> RecommendationService:
        key = llm_provider or settings.llm_provider
        if key not in _services:
            _services[key] = build_recommendation_service_with_llm(settings, key)
        return _services[key]

    # ── Middleware de autenticación ───────────────────────────
    @app.middleware("http")
    async def auth_middleware(request: Request, call_next):
        # Paths que no requieren token
        public = {"/docs", "/redoc", "/openapi.json", "/health", "/metrics"}
        if request.url.path in public:
            return await call_next(request)

        token = request.headers.get("Authorization", "")
        expected = f"Bearer {settings.api_secret_token}"
        if token != expected:
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={
                    "trace_id": str(uuid.uuid4()),
                    "error": "Token de autenticación ausente o inválido.",
                },
            )
        return await call_next(request)

    # ── Manejo global de errores ──────────────────────────────
    @app.exception_handler(Exception)
    async def global_error_handler(request: Request, exc: Exception):
        trace_id = str(uuid.uuid4())
        logger.error("Error interno trace_id=%s: %s", trace_id, exc, exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"trace_id": trace_id, "error": "Error interno del servidor."},
        )

    # ── Endpoints ─────────────────────────────────────────────

    @app.get("/health", tags=["ops"])
    def health():
        return {"status": "ok", "service": "rag-vehicle-api"}

    @app.post(
        "/api/v1/vehicle-recommendation",
        response_model=RecomendacionResponse,
        status_code=200,
        tags=["recommendations"],
        summary="Recomienda el vehículo óptimo para un pedido agrícola",
    )
    def recomendar_vehiculo(
        request: RecomendacionRequest,
    ) -> RecomendacionResponse:
        service = get_service(request.llm_provider)
        # Mapear schema → dominio
        pedido = Pedido(
            identificador=request.pedido.identificador,
            fecha_entrega=request.pedido.fecha_entrega,
            prioridad=request.pedido.prioridad,
        )
        productos = [
            Producto(nombre=p.nombre, cantidad=p.cantidad, unidad=p.unidad)
            for p in request.productos
        ]
        cliente = Cliente(
            nombre=request.cliente.nombre,
            direccion=request.cliente.direccion,
            latitud=request.cliente.latitud,
            longitud=request.cliente.longitud,
        )
        flota = [
            VehiculoDisponible(
                id=v.id, tipo=v.tipo,
                capacidad_kg=v.capacidad_kg,
                refrigerado=v.refrigerado,
                matricula=v.matricula,
            )
            for v in request.flota_disponible
        ]
        solicitud = SolicitudRecomendacion(
            pedido=pedido, productos=productos,
            cliente=cliente, canal=request.canal,
            flota_disponible=flota,
        )

        recomendacion = service.recomendar(solicitud)

        # Mapear dominio → schema de respuesta
        v = recomendacion.vehiculo_recomendado
        d = recomendacion.desglose_costo
        return RecomendacionResponse(
            trace_id=recomendacion.trace_id,
            vehiculo_recomendado=VehiculoRecomendadoSchema(
                id=v.id, tipo=v.tipo.value, matricula=v.matricula
            ),
            justificacion=recomendacion.justificacion,
            alternativas=[
                AlternativaSchema(id=a.id, motivo=a.motivo)
                for a in recomendacion.alternativas
            ],
            alertas=[
                AlertaSchema(nivel=al.nivel.value, mensaje=al.mensaje)
                for al in recomendacion.alertas
            ],
            costo_estimado_cop=recomendacion.costo_estimado_cop,
            desglose_costo=DesgloseCostoSchema(
                combustible_cop=d.combustible_cop,
                peajes_cop=d.peajes_cop,
                viaticos_cop=d.viaticos_cop,
                seguro_cop=d.seguro_cop,
                imprevistos_cop=d.imprevistos_cop,
                total_cop=d.total_cop,
            ),
            tiempo_estimado_min=recomendacion.tiempo_estimado_min,
        )

    return app


app = create_app()
