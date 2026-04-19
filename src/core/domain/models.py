"""
Entidades del dominio – Selección inteligente de vehículo.
Sin dependencias externas; solo tipos de la stdlib.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Optional
import uuid


class Prioridad(str, Enum):
    ALTA = "alta"
    MEDIA = "media"
    BAJA = "baja"


class Canal(str, Enum):
    MAYORISTA = "mayorista"
    MINORISTA = "minorista"
    EXPORTACION = "exportacion"
    INSTITUCIONAL = "institucional"


class TipoVehiculo(str, Enum):
    TERRESTRE = "TERRESTRE"
    AEREO = "AEREO"
    ACUATICO = "ACUATICO"


class NivelAlerta(str, Enum):
    ALTA = "alta"
    MEDIA = "media"
    BAJA = "baja"


@dataclass(frozen=True)
class Producto:
    nombre: str
    cantidad: float
    unidad: str  # kg | ton | unidades


@dataclass(frozen=True)
class Cliente:
    nombre: str
    direccion: str
    latitud: float
    longitud: float


@dataclass(frozen=True)
class VehiculoDisponible:
    id: str
    tipo: TipoVehiculo
    capacidad_kg: float
    refrigerado: bool
    matricula: Optional[str] = None


@dataclass(frozen=True)
class Pedido:
    identificador: str
    fecha_entrega: date
    prioridad: Prioridad


@dataclass(frozen=True)
class SolicitudRecomendacion:
    pedido: Pedido
    productos: list[Producto]
    cliente: Cliente
    canal: Canal
    flota_disponible: list[VehiculoDisponible]

    @property
    def peso_total_kg(self) -> float:
        total = 0.0
        for p in self.productos:
            if p.unidad == "ton":
                total += p.cantidad * 1000
            else:
                total += p.cantidad
        return total

    @property
    def requiere_refrigeracion(self) -> bool:
        frios = {
            "aguacate", "aguacate hass", "plátano", "banano", "mango",
            "fresa", "mora", "tomate", "lechuga", "espinaca",
            "leche", "queso", "flores", "rosas",
        }
        nombres = {p.nombre.lower() for p in self.productos}
        return bool(nombres & frios)


@dataclass
class Alternativa:
    id: str
    motivo: str


@dataclass
class Alerta:
    nivel: NivelAlerta
    mensaje: str


@dataclass
class DesgloseCosto:
    combustible_cop: float
    peajes_cop: float
    viaticos_cop: float
    seguro_cop: float
    imprevistos_cop: float

    @property
    def total_cop(self) -> float:
        return (
            self.combustible_cop
            + self.peajes_cop
            + self.viaticos_cop
            + self.seguro_cop
            + self.imprevistos_cop
        )


@dataclass
class RecomendacionVehiculo:
    trace_id: str
    vehiculo_recomendado: VehiculoDisponible
    justificacion: str
    alternativas: list[Alternativa]
    alertas: list[Alerta]
    costo_estimado_cop: float
    desglose_costo: DesgloseCosto
    tiempo_estimado_min: int
    fragmentos_consultados: list[str] = field(default_factory=list)

    @classmethod
    def nuevo_trace(cls, **kwargs) -> "RecomendacionVehiculo":
        return cls(trace_id=str(uuid.uuid4()), **kwargs)
