"""
PromptBuilder – construcción de prompts versionados.
Los costos y tiempos son calculados por CostCalculator (ADR-0006),
no por el LLM. El LLM solo elige vehículo y redacta justificación.
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
3. Justifica la selección considerando: capacidad, tipo de producto y condiciones de la ruta.
4. Si ningún vehículo es ideal, selecciona el mejor disponible y alerta sobre las limitaciones.
5. Usa el contexto documental y el contexto estructurado del grafo proporcionados.

IMPORTANTE: Los costos y tiempos de tránsito son calculados por el sistema con datos \
reales del grafo de conocimiento. NO los incluyas en tu respuesta.

FORMATO DE RESPUESTA (JSON estricto, sin markdown):
{
  "vehiculo_id": "<id del vehículo seleccionado>",
  "justificacion": "<explicación en lenguaje natural, máximo 400 palabras>",
  "alternativas": [
    {"id": "<id>", "motivo": "<ventajas y desventajas vs el recomendado>"}
  ],
  "alertas": [
    {"nivel": "alta|media|baja", "mensaje": "<descripción de la alerta>"}
  ]
}

Responde ÚNICAMENTE con el JSON. Sin texto adicional, sin bloques de código."""


class PromptBuilder:
    """Construye el prompt final combinando sistema, contexto RAG y solicitud."""

    VERSION = "v2"

    def build_system_prompt(self) -> str:
        return SYSTEM_PROMPT_V1

    def build_user_prompt(
        self,
        solicitud: SolicitudRecomendacion,
        fragmentos: list[Fragmento],
        contexto_grafo: dict | None = None,
    ) -> str:
        semantico = self._formatear_contexto(fragmentos)
        estructurado = self._formatear_grafo(contexto_grafo or {})
        solicitud_txt = self._formatear_solicitud(solicitud)
        return (
            f"CONTEXTO DOCUMENTAL (recuperación semántica):\n{semantico}\n\n"
            f"CONTEXTO ESTRUCTURADO (grafo de conocimiento):\n{estructurado}\n\n"
            f"---\n"
            f"SOLICITUD DE TRANSPORTE:\n{solicitud_txt}\n\n"
            f"Elige el vehículo óptimo y justifica en el formato JSON indicado."
        )

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

    def _formatear_grafo(self, ctx: dict) -> str:
        if not ctx:
            return "(sin datos del grafo disponibles)"
        lines = []

        corredor = ctx.get("corredor")
        if corredor:
            lines.append(
                f"[Corredor] {corredor.get('nombre', 'N/A')} — "
                f"{corredor.get('distancia_km', '?')} km, "
                f"estado: {corredor.get('estado_general', '?')}, "
                f"tiempo estimado carga: {corredor.get('tiempo_estimado_min_carga', '?')} min"
            )

        for r in ctx.get("requisitos_productos", []):
            if r.get("nombre_encontrado"):
                lines.append(
                    f"[Producto] {r['nombre_encontrado']}: "
                    f"temp {r.get('temp_min_c', '?')}–{r.get('temp_max_c', '?')} °C, "
                    f"humedad {r.get('humedad_pct', '?')}%, "
                    f"vehículo: {r.get('tipo_vehiculo_requerido', 'N/A')}"
                )

        for n in ctx.get("normativa", []):
            if n.get("numero"):
                lines.append(f"[Normativa] {n.get('nombre', n['numero'])}")

        tarifas_con_valor = [t for t in ctx.get("tarifas", []) if t.get("valor_cop")]
        if tarifas_con_valor:
            lines.append(f"[Tarifas] {len(tarifas_con_valor)} tarifa(s) disponibles para el corredor")

        return "\n".join(lines) if lines else "(grafo sin datos relevantes para esta consulta)"

    def _formatear_solicitud(self, s: SolicitudRecomendacion) -> str:
        productos_txt = "\n".join(
            f"  - {p.nombre}: {p.cantidad} {p.unidad}" for p in s.productos
        )
        flota_txt = "\n".join(
            f"  - {v.id} ({v.tipo.value}): {v.capacidad_kg} kg, "
            f"{'refrigerado' if v.refrigerado else 'sin refrigeración'}"
            + (f", matrícula {v.matricula}" if v.matricula else "")
            for v in s.flota_disponible
        )
        def _fmt_ubicacion(u) -> str:
            partes = [u.ciudad]
            if u.departamento:
                partes.append(u.departamento)
            if u.direccion:
                partes.append(u.direccion)
            return ", ".join(partes)

        intra_urbana = s.origen.ciudad.lower() == s.destino.ciudad.lower()
        ruta_nota = (
            "⚠ Entrega intra-urbana (origen y destino en la misma ciudad). "
            "No hay corredor inter-ciudad disponible en el grafo; "
            "la selección se basa en características del producto y flota."
            if intra_urbana else ""
        )
        return (
            f"Pedido: {s.pedido.identificador}\n"
            f"Fecha entrega: {s.pedido.fecha_entrega}\n"
            f"Prioridad: {s.pedido.prioridad.value}\n"
            f"Canal: {s.canal.value}\n"
            f"Origen: {_fmt_ubicacion(s.origen)}\n"
            f"Destino: {_fmt_ubicacion(s.destino)}\n"
            + (f"{ruta_nota}\n" if ruta_nota else "")
            + f"\nProductos ({s.peso_total_kg:.0f} kg total):\n{productos_txt}\n\n"
            f"Requiere refrigeración (estimado): {'SÍ' if s.requiere_refrigeracion else 'NO'}\n\n"
            f"Flota disponible:\n{flota_txt}"
        )

