"""
PromptBuilder – construcción de prompts versionados.
Los costos y tiempos son calculados por CostCalculator (ADR-0006),
no por el LLM. El LLM solo elige vehículo y redacta justificación.
"""
from __future__ import annotations

from src.core.domain.models import SolicitudRecomendacion
from src.core.ports.interfaces import Fragmento


_SYSTEM_BASE = """<system_role>
Eres un Ingeniero de Logística Agrícola en Colombia. Tu única función es asignar el vehículo óptimo basado en datos técnicos, normativos y de carga.
</system_role>

<context_rules>
1. Prioridad Frío: Si el producto es perecedero (flores, frutas, lácteos), usa refrigeración.
2. Capacidad: El peso de la carga debe ser ≤ capacidad del vehículo.
3. Fallback: Si no hay un vehículo ideal, elige el más cercano y genera una alerta "alta".
4. Exclusión: Prohibido mencionar costos o tiempos de tránsito (estos los calcula otro sistema).
</context_rules>

<workflow>
1. Analizar el peso y tipo de producto en la solicitud del usuario.
2. Comparar contra el <document_context> y <graph_context> proporcionado.
3. Seleccionar el "vehiculo_id" con mejor ajuste técnico.
4. Redactar una justificación técnica breve (< 400 palabras).
</workflow>

<output_format>
Responde exclusivamente en formato JSON plano. Sin bloques de código markdown, sin texto introductorio, sin comentarios.
{{
  "vehiculo_id": "string",
  "justificacion": "string",
  "alternativas": [{{"id": "string", "motivo": "string"}}],
  "alertas": [{{"nivel": "alta|media|baja", "mensaje": "string"}}]
}}
</output_format>"""

_STRICT_SUFFIX = """

<constraints>
- No usar ```json ... ```
- No incluir texto fuera de las llaves del JSON.
- Nivel de alerta solo: alta, media, baja.
</constraints>

<example>
{{"vehiculo_id":"VEH-02","justificacion":"El VEH-02 cuenta con termoking activo para lácteos y capacidad de 3.5T, adecuada para los 1.2T solicitados.","alternativas":[{{"id":"VEH-01","motivo":"Mayor capacidad pero carece de refrigeración."}}],"alertas":[{{"nivel":"baja","mensaje":"Verificar precintos de seguridad."}}]}}
</example>"""

SYSTEM_PROMPT_V1 = _SYSTEM_BASE.replace("{{", "{").replace("}}", "}")


class PromptBuilder:
    """Construye el prompt final combinando sistema, contexto RAG y solicitud."""

    VERSION = "v2"

    def build_system_prompt(self, strict_mode: bool = False) -> str:
        if strict_mode:
            base = _SYSTEM_BASE.replace("{{", "{").replace("}}", "}")
            suffix = _STRICT_SUFFIX.replace("{{", "{").replace("}}", "}")
            return base + suffix
        return SYSTEM_PROMPT_V1

    def build_user_prompt(
        self,
        solicitud: SolicitudRecomendacion,
        fragmentos: list[Fragmento],
        contexto_grafo: dict | None = None,
        strict_mode: bool = False,
    ) -> str:
        if strict_mode:
            return self._build_user_prompt_xml(solicitud, fragmentos, contexto_grafo or {})
        return self._build_user_prompt_plain(solicitud, fragmentos, contexto_grafo or {})

    def _build_user_prompt_plain(
        self,
        solicitud: SolicitudRecomendacion,
        fragmentos: list[Fragmento],
        contexto_grafo: dict,
    ) -> str:
        semantico = self._formatear_contexto(fragmentos)
        estructurado = self._formatear_grafo(contexto_grafo)
        solicitud_txt = self._formatear_solicitud(solicitud)
        todos_ids = self._todos_los_ids_flota(solicitud)
        return (
            f"<document_context>\n{semantico}\n</document_context>\n\n"
            f"<graph_context>\n{estructurado}\n</graph_context>\n\n"
            f"<request>\n{solicitud_txt}\n</request>\n\n"
            f"Asigna el vehículo óptimo siguiendo el workflow definido.\n"
            f"IMPORTANTE: la flota disponible es [{todos_ids}]. "
            f"Una vez elijas el vehículo óptimo, incluye en 'alternativas' "
            f"una entrada por cada vehículo que NO hayas seleccionado, explicando por qué fue descartado."
        )

    def _build_user_prompt_xml(
        self,
        solicitud: SolicitudRecomendacion,
        fragmentos: list[Fragmento],
        contexto_grafo: dict,
    ) -> str:
        doc_ctx = self._xml_document_context(fragmentos)
        graph_ctx = self._xml_graph_context(contexto_grafo)
        transport = self._xml_transport_request(solicitud)
        fleet = self._xml_available_fleet(solicitud)
        todos_ids = self._todos_los_ids_flota(solicitud)
        return (
            f"<input_data>\n"
            f"{doc_ctx}\n\n"
            f"{graph_ctx}\n\n"
            f"{transport}\n\n"
            f"{fleet}\n"
            f"</input_data>\n\n"
            f"<instruction_trigger>\n"
            f"Analiza los datos anteriores y genera el JSON con los siguientes campos OBLIGATORIOS:\n"
            f'- "vehiculo_id": ID del vehículo seleccionado de la flota [{todos_ids}].\n'
            f'- "justificacion": explicación técnica en español de por qué ese vehículo es el óptimo (OBLIGATORIO, no puede estar vacío).\n'
            f'- "alternativas": una entrada por cada vehículo de [{todos_ids}] que NO hayas seleccionado, '
            f"explicando por qué fue descartado.\n"
            f'- "alertas": lista de alertas si hay limitaciones, o lista vacía.\n'
            f"</instruction_trigger>"
        )

    # ── helpers compartidos ───────────────────────────────────

    def _todos_los_ids_flota(self, solicitud: SolicitudRecomendacion) -> str:
        return ", ".join(v.id for v in solicitud.flota_disponible)

    # ── helpers formato plano ─────────────────────────────────

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

    # ── helpers formato XML (strict_mode) ─────────────────────

    def _xml_document_context(self, fragmentos: list[Fragmento]) -> str:
        if not fragmentos:
            return "  <document_context>(sin contexto documental disponible)</document_context>"
        lines = []
        for i, f in enumerate(fragmentos, 1):
            lines.append(f"    [Doc {i} | {f.categoria} | Score: {f.score:.2f}]: {f.contenido}")
        return "  <document_context>\n" + "\n".join(lines) + "\n  </document_context>"

    def _xml_graph_context(self, ctx: dict) -> str:
        lines = []

        corredor = ctx.get("corredor")
        if corredor:
            lines.append(
                f"    <corridor>{corredor.get('nombre', 'N/A')} | "
                f"Distancia: {corredor.get('distancia_km', '?')} km | "
                f"Estado: {corredor.get('estado_general', '?')} | "
                f"Carga_estimada: {corredor.get('tiempo_estimado_min_carga', '?')} min</corridor>"
            )

        specs = []
        for r in ctx.get("requisitos_productos", []):
            if r.get("nombre_encontrado"):
                specs.append(
                    f"      - {r['nombre_encontrado']}: "
                    f"Temp {r.get('temp_min_c', '?')}–{r.get('temp_max_c', '?')} °C | "
                    f"Humedad {r.get('humedad_pct', '?')}% | "
                    f"Requiere: {r.get('tipo_vehiculo_requerido', 'N/A')}"
                )
        for n in ctx.get("normativa", []):
            if n.get("numero"):
                specs.append(f"      - Normativa: {n.get('nombre', n['numero'])}")
        if specs:
            lines.append("    <product_specs>\n" + "\n".join(specs) + "\n    </product_specs>")

        if not lines:
            lines.append("    (sin datos del grafo disponibles)")

        return "  <graph_context>\n" + "\n".join(lines) + "\n  </graph_context>"

    def _xml_transport_request(self, s: SolicitudRecomendacion) -> str:
        def _fmt(u) -> str:
            partes = [u.ciudad]
            if u.departamento:
                partes.append(u.departamento)
            return ", ".join(partes)

        productos = "\n".join(
            f"      - {p.nombre}: {p.cantidad} {p.unidad}" for p in s.productos
        )
        intra_urbana = s.origen.ciudad.lower() == s.destino.ciudad.lower()
        nota = (
            "\n    <!-- Entrega intra-urbana: sin corredor inter-ciudad disponible -->"
            if intra_urbana else ""
        )
        return (
            f'  <transport_request id="{s.pedido.identificador}">{nota}\n'
            f"    <delivery_date>{s.pedido.fecha_entrega}</delivery_date>\n"
            f"    <priority>{s.pedido.prioridad.value}</priority>\n"
            f"    <route>{_fmt(s.origen)} -> {_fmt(s.destino)}</route>\n"
            f'    <payload total="{s.peso_total_kg:.0f}kg">\n{productos}\n    </payload>\n'
            f"    <requirements>Refrigeración: {'SÍ' if s.requiere_refrigeracion else 'NO'}</requirements>\n"
            f"  </transport_request>"
        )

    def _xml_available_fleet(self, s: SolicitudRecomendacion) -> str:
        vehicles = []
        for v in s.flota_disponible:
            features = "Refrigerado" if v.refrigerado else "Sin refrigeración"
            plate = f"\n      <plate>{v.matricula}</plate>" if v.matricula else ""
            vehicles.append(
                f'    <vehicle id="{v.id}">\n'
                f"      <type>{v.tipo.value}</type>\n"
                f"      <capacity>{v.capacidad_kg}kg</capacity>\n"
                f"      <features>{features}</features>{plate}\n"
                f"    </vehicle>"
            )
        return "  <available_fleet>\n" + "\n".join(vehicles) + "\n  </available_fleet>"

