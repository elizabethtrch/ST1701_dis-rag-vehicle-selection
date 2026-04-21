"""
Tests unitarios – RecommendationService y ResponseParser.
Usan dobles de prueba (fakes) sin llamadas reales a LLM ni ChromaDB.
"""
from __future__ import annotations
import json
import sys
import os
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from src.core.domain.models import (
    Canal, NivelAlerta, Pedido, Prioridad,
    Producto, SolicitudRecomendacion, TipoVehiculo, Ubicacion, VehiculoDisponible,
)
from src.core.ports.interfaces import (
    EmbeddingProvider, Fragmento, KnowledgeRepository, LLMProvider, LLMResponse,
)
from src.core.services.recommendation_service import RecommendationService
from src.core.utils.response_parser import ResponseParser, ParseError
from src.core.utils.prompt_builder import PromptBuilder


# ── Fakes (dobles de prueba) ──────────────────────────────────

class FakeKnowledgeRepo(KnowledgeRepository):
    def __init__(self, fragmentos: list[Fragmento] = None):
        self._fragmentos = fragmentos or [
            Fragmento(
                id="f1", contenido="El aguacate requiere transporte refrigerado entre 5 y 8 grados.",
                categoria="products", fuente="fichas_tecnicas.md", score=0.95
            ),
            Fragmento(
                id="f2", contenido="Camión furgón refrigerado 5 ton: ideal para frutas tropicales.",
                categoria="fleet", fuente="catalogo_flota.json", score=0.88
            ),
        ]

    def search_semantic(self, query, k=5, categoria=None):
        if categoria:
            return [f for f in self._fragmentos if f.categoria == categoria][:k]
        return self._fragmentos[:k]

    def upsert_chunk(self, chunk_id, contenido, categoria, fuente, metadata=None):
        pass

    def list_by_category(self, categoria):
        return [f for f in self._fragmentos if f.categoria == categoria]

    def count(self):
        return len(self._fragmentos)


class FakeLLMProvider(LLMProvider):
    def __init__(self, respuesta_json: dict, strict: bool = False):
        self._respuesta = respuesta_json
        self._strict = strict

    @property
    def nombre_modelo(self):
        return "fake-model-v1"

    @property
    def strict_output(self):
        return self._strict

    def generate(self, system_prompt, user_prompt, max_tokens=1500):
        return LLMResponse(
            texto=json.dumps(self._respuesta),
            tokens_entrada=500,
            tokens_salida=200,
            modelo="fake-model-v1",
        )

    def count_tokens(self, text):
        return len(text) // 4


# ── Fixture de solicitud ──────────────────────────────────────

def _solicitud_base() -> SolicitudRecomendacion:
    return SolicitudRecomendacion(
        pedido=Pedido(
            identificador="PED-TEST-001",
            fecha_entrega=date(2025, 6, 15),
            prioridad=Prioridad.ALTA,
        ),
        productos=[
            Producto(nombre="Aguacate Hass", cantidad=1200, unidad="kg"),
            Producto(nombre="Plátano hartón", cantidad=800, unidad="kg"),
        ],
        origen=Ubicacion(ciudad="Medellín", departamento="Antioquia"),
        destino=Ubicacion(ciudad="Bogotá", departamento="Cundinamarca"),
        canal=Canal.MAYORISTA,
        flota_disponible=[
            VehiculoDisponible(id="VEH-015", tipo=TipoVehiculo.TERRESTRE, capacidad_kg=3500, refrigerado=True, matricula="ABC123"),
            VehiculoDisponible(id="VEH-022", tipo=TipoVehiculo.TERRESTRE, capacidad_kg=2000, refrigerado=False, matricula="XYZ789"),
        ],
    )


def _respuesta_llm_valida():
    return {
        "vehiculo_id": "VEH-015",
        "justificacion": "El VEH-015 se selecciona porque cuenta con refrigeración y capacidad suficiente para 2000 kg de carga perecedera.",
        "alternativas": [{"id": "VEH-022", "motivo": "Sin refrigeración, no apto para aguacate en clima cálido."}],
        "alertas": [{"nivel": "media", "mensaje": "Verificar temperatura antes de cargue."}],
        "tiempo_estimado_min": 420,
        "desglose_costo": {
            "combustible_cop": 280000,
            "peajes_cop": 75000,
            "viaticos_cop": 90000,
            "seguro_cop": 8500,
            "imprevistos_cop": 68025,
        },
    }


# ══════════════════════════════════════════════════════════════
# Tests del dominio
# ══════════════════════════════════════════════════════════════

class TestSolicitudRecomendacion:
    def test_peso_total_kg_mezcla_unidades(self):
        sol = SolicitudRecomendacion(
            pedido=Pedido("X", date.today(), Prioridad.BAJA),
            productos=[
                Producto("Papa", 2, "ton"),
                Producto("Yuca", 500, "kg"),
            ],
            origen=Ubicacion(ciudad="Tunja"),
            destino=Ubicacion(ciudad="Bogotá"),
            canal=Canal.MINORISTA,
            flota_disponible=[
                VehiculoDisponible("V1", TipoVehiculo.TERRESTRE, 5000, False)
            ],
        )
        assert sol.peso_total_kg == 2500.0

    def test_requiere_refrigeracion_aguacate(self):
        sol = _solicitud_base()
        assert sol.requiere_refrigeracion is True

    def test_no_requiere_refrigeracion_papa(self):
        sol = SolicitudRecomendacion(
            pedido=Pedido("X", date.today(), Prioridad.BAJA),
            productos=[Producto("Papa", 1000, "kg")],
            origen=Ubicacion(ciudad="Tunja"),
            destino=Ubicacion(ciudad="Bogotá"),
            canal=Canal.MINORISTA,
            flota_disponible=[VehiculoDisponible("V1", TipoVehiculo.TERRESTRE, 5000, False)],
        )
        assert sol.requiere_refrigeracion is False


# ══════════════════════════════════════════════════════════════
# Tests de RecommendationService
# ══════════════════════════════════════════════════════════════

class TestRecommendationService:
    def _service(self, llm_resp=None):
        repo = FakeKnowledgeRepo()
        llm = FakeLLMProvider(llm_resp or _respuesta_llm_valida())
        return RecommendationService(knowledge_repo=repo, llm_provider=llm)

    def test_recomendar_retorna_recomendacion(self):
        service = self._service()
        result = service.recomendar(_solicitud_base())
        assert result.trace_id
        assert result.vehiculo_recomendado.id == "VEH-015"

    def test_trace_id_es_uuid(self):
        import uuid
        service = self._service()
        result = service.recomendar(_solicitud_base())
        parsed = uuid.UUID(result.trace_id)
        assert str(parsed) == result.trace_id

    def test_vehiculo_fallback_cuando_id_invalido(self):
        resp = _respuesta_llm_valida()
        resp["vehiculo_id"] = "VEH-INEXISTENTE"
        service = self._service(resp)
        result = service.recomendar(_solicitud_base())
        # Debe usar el de mayor capacidad como fallback
        assert result.vehiculo_recomendado.id == "VEH-015"

    def test_alternativas_limitadas_a_dos(self):
        resp = _respuesta_llm_valida()
        resp["alternativas"] = [
            {"id": "V1", "motivo": "a"},
            {"id": "V2", "motivo": "b"},
            {"id": "V3", "motivo": "c"},
        ]
        service = self._service(resp)
        result = service.recomendar(_solicitud_base())
        assert len(result.alternativas) <= 2

    def test_costo_total_coherente(self):
        service = self._service()
        result = service.recomendar(_solicitud_base())
        d = result.desglose_costo
        expected = d.combustible_cop + d.peajes_cop + d.viaticos_cop + d.seguro_cop + d.imprevistos_cop
        assert abs(result.costo_estimado_cop - expected) < 1

    def test_strict_output_false_por_defecto(self):
        llm = FakeLLMProvider(_respuesta_llm_valida())
        assert llm.strict_output is False

    def test_strict_output_activa_prompt_extendido(self):
        captured = {}

        class CapturingPromptBuilder(PromptBuilder):
            def build_system_prompt(self, strict_mode=False):
                captured["strict_mode"] = strict_mode
                return super().build_system_prompt(strict_mode=strict_mode)

        llm = FakeLLMProvider(_respuesta_llm_valida(), strict=True)
        service = RecommendationService(
            knowledge_repo=FakeKnowledgeRepo(),
            llm_provider=llm,
            prompt_builder=CapturingPromptBuilder(),
        )
        service.recomendar(_solicitud_base())
        assert captured["strict_mode"] is True


# ══════════════════════════════════════════════════════════════
# Tests de ResponseParser
# ══════════════════════════════════════════════════════════════

class TestResponseParser:
    def _parser(self):
        return ResponseParser()

    def test_parse_json_valido(self):
        parser = self._parser()
        solicitud = _solicitud_base()
        texto = json.dumps(_respuesta_llm_valida())
        result = parser.parse(texto, solicitud, ["f1", "f2"])
        assert result.vehiculo_recomendado.id == "VEH-015"
        assert result.justificacion != ""

    def test_parse_json_con_markdown(self):
        parser = self._parser()
        texto = "```json\n" + json.dumps(_respuesta_llm_valida()) + "\n```"
        result = parser.parse(texto, _solicitud_base(), [])
        assert result.vehiculo_recomendado.id == "VEH-015"

    def test_parse_nivel_alerta(self):
        parser = self._parser()
        result = parser.parse(json.dumps(_respuesta_llm_valida()), _solicitud_base(), [])
        assert result.alertas[0].nivel == NivelAlerta.MEDIA

    def test_parse_json_invalido_lanza_error(self):
        parser = self._parser()
        try:
            parser.parse("esto no es json válido ni tiene llaves", _solicitud_base(), [])
            assert False, "Debió lanzar ParseError"
        except ParseError:
            pass

    def test_fragmentos_consultados_en_resultado(self):
        parser = self._parser()
        ids = ["frag-001", "frag-002"]
        result = parser.parse(json.dumps(_respuesta_llm_valida()), _solicitud_base(), ids)
        assert result.fragmentos_consultados == ids

    def test_parse_schema_alternativo_selected_vehicle(self):
        parser = self._parser()
        texto = json.dumps({
            "selected_vehicle": {
                "vehicle_id": "VEH-015",
                "capacity_kg": 3500.0,
                "refrigerated": True,
                "justification": {
                    "reason": "Cumple refrigeración y capacidad.",
                    "reliability": "Mantiene cadena de frío en los 414 km.",
                },
                "alternative_vehicles": [{"vehicle_id": "VEH-022", "capacity_kg": 2000}],
            },
            "refrigeration_needed": True,
        })
        result = parser.parse(texto, _solicitud_base(), [])
        assert result.vehiculo_recomendado.id == "VEH-015"
        assert "Cumple refrigeración" in result.justificacion
        assert result.justificacion != "Sin justificación disponible."

    def test_parse_schema_con_reasoning_lista(self):
        parser = self._parser()
        texto = json.dumps({
            "selected_vehicle": {
                "vehicle_id": "VEH-015",
                "reasoning": [
                    {"factor": "Capacity", "value": "Capacidad suficiente para 2000 kg."},
                    {"factor": "Refrigeration", "value": "Cumple cadena de frío."},
                ],
            }
        })
        result = parser.parse(texto, _solicitud_base(), [])
        assert result.vehiculo_recomendado.id == "VEH-015"
        assert "Capacidad suficiente" in result.justificacion

    def test_parse_alternativas_agnostico_a_nombre_de_campo(self):
        parser = self._parser()
        for campo_motivo in ("motivo", "justificacion", "explicacion", "reason_for_exclusion", "descripcion"):
            texto = json.dumps({
                "vehiculo_id": "VEH-015",
                "justificacion": "Cumple requisitos.",
                "alternativas": [{"vehiculo_id": "VEH-022", campo_motivo: "Sin refrigeración."}],
                "alertas": [],
            })
            result = parser.parse(texto, _solicitud_base(), [])
            assert result.alternativas[0].id == "VEH-022", f"falló con campo '{campo_motivo}'"
            assert result.alternativas[0].motivo != "", f"motivo vacío con campo '{campo_motivo}'"

    def test_parse_alternativas_con_campos_alternativos(self):
        parser = self._parser()
        texto = json.dumps({
            "selected_vehicle": {"id": "VEH-015"},
            "justificacion": "Cumple refrigeración.",
            "alternatives": [
                {
                    "vehicle_id": "VEH-022",
                    "reason_for_exclusion": "No tiene refrigeración para productos perecederos.",
                }
            ],
        })
        result = parser.parse(texto, _solicitud_base(), [])
        assert len(result.alternativas) == 1
        assert result.alternativas[0].id == "VEH-022"
        assert "refrigeración" in result.alternativas[0].motivo

    def test_parse_schema_justification_como_lista(self):
        parser = self._parser()
        texto = json.dumps({
            "selected_vehicle": {
                "id": "VEH-015",
                "capacity": 3500.0,
                "refrigerated": True,
            },
            "justification": [
                "El vehículo VEH-015 cumple con refrigeración.",
                "La carga de 1200 kg se ajusta a la capacidad.",
            ],
        })
        result = parser.parse(texto, _solicitud_base(), [])
        assert result.vehiculo_recomendado.id == "VEH-015"
        assert "refrigeración" in result.justificacion
        assert result.justificacion != "Sin justificación disponible."

    def test_parse_json_con_comentarios_js(self):
        parser = self._parser()
        texto = (
            '{\n'
            '  "vehiculo_id": "VEH-015", // vehículo seleccionado\n'
            '  "justificacion": "Cumple requisitos.",\n'
            '  "alternativas": [],\n'
            '  "alertas": [] /* sin alertas */\n'
            '}'
        )
        result = parser.parse(texto, _solicitud_base(), [])
        assert result.vehiculo_recomendado.id == "VEH-015"


# ══════════════════════════════════════════════════════════════
# Tests de PromptBuilder
# ══════════════════════════════════════════════════════════════

class TestPromptBuilder:
    def test_system_prompt_no_vacio(self):
        pb = PromptBuilder()
        assert len(pb.build_system_prompt()) > 100

    def test_user_prompt_contiene_datos_pedido(self):
        pb = PromptBuilder()
        solicitud = _solicitud_base()
        fragmentos = [
            Fragmento("f1", "Contenido de prueba", "products", "test.md", 0.9)
        ]
        prompt = pb.build_user_prompt(solicitud, fragmentos)
        assert "PED-TEST-001" in prompt
        assert "Aguacate Hass" in prompt
        assert "VEH-015" in prompt
        assert "Contenido de prueba" in prompt
        assert "Medellín" in prompt
        assert "Bogotá" in prompt

    def test_user_prompt_indica_refrigeracion(self):
        pb = PromptBuilder()
        prompt = pb.build_user_prompt(_solicitud_base(), [])
        assert "SÍ" in prompt  # requiere_refrigeracion = True para aguacate

    def test_user_prompt_menciona_vehiculos_alternativos(self):
        pb = PromptBuilder()
        prompt = pb.build_user_prompt(_solicitud_base(), [])
        assert "alternativas" in prompt
        assert "VEH-022" in prompt  # único vehículo no primero en la flota base

    def test_user_prompt_strict_usa_xml(self):
        pb = PromptBuilder()
        prompt = pb.build_user_prompt(_solicitud_base(), [], strict_mode=True)
        assert "<input_data>" in prompt
        assert "<transport_request" in prompt
        assert "<available_fleet>" in prompt
        assert "<instruction_trigger>" in prompt

    def test_user_prompt_strict_contiene_datos_pedido(self):
        pb = PromptBuilder()
        fragmentos = [Fragmento("f1", "Contenido de prueba", "products", "test.md", 0.9)]
        prompt = pb.build_user_prompt(_solicitud_base(), fragmentos, strict_mode=True)
        assert "PED-TEST-001" in prompt
        assert "Aguacate Hass" in prompt
        assert "VEH-015" in prompt
        assert "VEH-022" in prompt
        assert "Medellín" in prompt
        assert "Bogotá" in prompt

    def test_user_prompt_normal_no_usa_xml(self):
        pb = PromptBuilder()
        prompt = pb.build_user_prompt(_solicitud_base(), [], strict_mode=False)
        assert "<input_data>" not in prompt
        assert "<available_fleet>" not in prompt

    def test_system_prompt_normal_sin_restricciones_absolutas(self):
        pb = PromptBuilder()
        prompt = pb.build_system_prompt(strict_mode=False)
        assert "<constraints>" not in prompt
        assert "<example>" not in prompt

    def test_system_prompt_strict_tiene_ejemplo_y_restricciones(self):
        pb = PromptBuilder()
        prompt = pb.build_system_prompt(strict_mode=True)
        assert "<example>" in prompt
        assert "<constraints>" in prompt
        assert "vehiculo_id" in prompt

    def test_strict_mode_no_altera_campos_del_schema(self):
        pb = PromptBuilder()
        normal = pb.build_system_prompt(strict_mode=False)
        strict = pb.build_system_prompt(strict_mode=True)
        for campo in ("vehiculo_id", "justificacion", "alternativas", "alertas"):
            assert campo in normal
            assert campo in strict


# ── Runner manual ─────────────────────────────────────────────

if __name__ == "__main__":
    import traceback

    suites = [
        TestSolicitudRecomendacion,
        TestRecommendationService,
        TestResponseParser,
        TestPromptBuilder,
    ]

    total = passed = failed = 0
    for suite_cls in suites:
        suite = suite_cls()
        methods = [m for m in dir(suite) if m.startswith("test_")]
        print(f"\n{'═'*50}")
        print(f"  {suite_cls.__name__}")
        print(f"{'═'*50}")
        for method in methods:
            total += 1
            try:
                getattr(suite, method)()
                print(f"  ✓  {method}")
                passed += 1
            except Exception as exc:
                print(f"  ✗  {method}")
                traceback.print_exc()
                failed += 1

    print(f"\n{'─'*50}")
    print(f"  Resultado: {passed}/{total} pasaron  |  {failed} fallaron")
    print(f"{'─'*50}\n")
    sys.exit(0 if failed == 0 else 1)
