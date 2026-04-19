"""
PromptBuilder – construcción de prompts versionados.
Separa instrucciones del sistema, contexto RAG y consulta del usuario.
"""
from __future__ import annotations
from src.core.domain.models import SolicitudRecomendacion
from src.core.ports.interfaces import Fragmento


SYSTEM_PROMPT_V1 = """Eres un experto en logística agrícola colombiana especializado en \
selección de vehículos de transporte. Tu rol es analizar solicitudes de transporte \
y recomendar el vehículo óptimo de la flota disponible.

REGLAS DE RAZONAMIENTO:
1. Considera SIEMPRE la capacidad del vehículo vs el peso total de la carga.
2. Para productos perecederos que requieren frío (frutas tropicales, flores, lácteos), \
prioriza vehículos refrigerados cuando estén disponibles.
3. Justifica la selección considerando: capacidad, tipo de producto, costo estimado \
y condiciones de la ruta.
4. Si ningún vehículo es ideal, selecciona el mejor disponible y alerta sobre las \
limitaciones.
5. Usa el conocimiento especializado del contexto documental recuperado.

FORMATO DE RESPUESTA (JSON estricto, sin markdown):
{
  "vehiculo_id": "<id del vehículo seleccionado>",
  "justificacion": "<explicación en lenguaje natural, máximo 400 palabras>",
  "alternativas": [
    {"id": "<id>", "motivo": "<ventajas y desventajas vs recomendado>"}
  ],
  "alertas": [
    {"nivel": "alta|media|baja", "mensaje": "<descripción de la alerta>"}
  ],
  "tiempo_estimado_min": <entero>,
  "desglose_costo": {
    "combustible_cop": <número>,
    "peajes_cop": <número>,
    "viaticos_cop": <número>,
    "seguro_cop": <número>,
    "imprevistos_cop": <número>
  }
}

Responde ÚNICAMENTE con el JSON. Sin texto adicional, sin bloques de código."""


class PromptBuilder:
    """Construye el prompt final combinando sistema, contexto RAG y solicitud."""

    VERSION = "v1"

    def build_system_prompt(self) -> str:
        return SYSTEM_PROMPT_V1

    def build_user_prompt(
        self,
        solicitud: SolicitudRecomendacion,
        fragmentos: list[Fragmento],
    ) -> str:
        contexto = self._formatear_contexto(fragmentos)
        solicitud_txt = self._formatear_solicitud(solicitud)
        return f"""CONTEXTO DOCUMENTAL RECUPERADO:
{contexto}

---
SOLICITUD DE TRANSPORTE:
{solicitud_txt}

Analiza la solicitud usando el contexto documental y genera la recomendación en el \
formato JSON indicado."""

    # ── helpers ──────────────────────────────────────────────

    def _formatear_contexto(self, fragmentos: list[Fragmento]) -> str:
        if not fragmentos:
            return "(sin contexto documental disponible)"
        bloques = []
        for i, f in enumerate(fragmentos, 1):
            bloques.append(
                f"[Doc {i} | {f.categoria} | {f.fuente} | score={f.score:.2f}]\n{f.contenido}"
            )
        return "\n\n".join(bloques)

    def _formatear_solicitud(self, s: SolicitudRecomendacion) -> str:
        productos_txt = "\n".join(
            f"  - {p.nombre}: {p.cantidad} {p.unidad}"
            for p in s.productos
        )
        flota_txt = "\n".join(
            f"  - {v.id} ({v.tipo.value}): {v.capacidad_kg} kg, "
            f"{'refrigerado' if v.refrigerado else 'sin refrigeración'}"
            + (f", matrícula {v.matricula}" if v.matricula else "")
            for v in s.flota_disponible
        )
        return f"""Pedido: {s.pedido.identificador}
Fecha entrega: {s.pedido.fecha_entrega}
Prioridad: {s.pedido.prioridad.value}
Canal: {s.canal.value}
Cliente: {s.cliente.nombre} — {s.cliente.direccion}
  Coordenadas: {s.cliente.latitud}, {s.cliente.longitud}

Productos ({s.peso_total_kg:.0f} kg total):
{productos_txt}

Requiere refrigeración (estimado): {'SÍ' if s.requiere_refrigeracion else 'NO'}

Flota disponible:
{flota_txt}"""
