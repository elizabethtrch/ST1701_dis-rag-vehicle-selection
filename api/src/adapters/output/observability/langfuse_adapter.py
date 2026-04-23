"""
LangfuseAdapter – registra trazas de inferencia en Langfuse (self-hosted).
"""
from __future__ import annotations

import logging

from src.core.ports.interfaces import ObservabilityPort

logger = logging.getLogger(__name__)


class LangfuseAdapter(ObservabilityPort):

    def __init__(self, public_key: str, secret_key: str, host: str) -> None:
        try:
            from langfuse import Langfuse
        except ImportError as exc:
            raise ImportError("Instala langfuse: pip install langfuse") from exc

        import os
        os.environ.setdefault("LANGFUSE_SDK_TELEMETRY_DISABLED", "true")
        from langfuse import Langfuse
        self._client = Langfuse(
            public_key=public_key,
            secret_key=secret_key,
            host=host,
        )

    def trace_recommendation(
        self,
        trace_id: str,
        solicitud_id: str,
        proveedor: str,
        modelo: str,
        system_prompt: str,
        user_prompt: str,
        respuesta: str,
        tokens_entrada: int,
        tokens_salida: int,
        latencia_ms: int,
        vehiculo_seleccionado: str,
        metadata: dict | None = None,
    ) -> None:
        try:
            logger.info(
                "Langfuse trace → solicitud=%s proveedor=%s modelo=%s vehiculo=%s",
                solicitud_id, proveedor, modelo, vehiculo_seleccionado,
            )
            trace = self._client.trace(
                id=trace_id,
                name="rag-vehicle-recommendation",
                input={"solicitud_id": solicitud_id},
                output={"vehiculo_seleccionado": vehiculo_seleccionado},
                metadata=metadata or {},
            )
            trace.generation(
                name="llm-inference",
                model=modelo,
                model_parameters={"provider": proveedor},
                input=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                output=respuesta,
                usage={
                    "input": tokens_entrada,
                    "output": tokens_salida,
                    "total": tokens_entrada + tokens_salida,
                },
                metadata={"latencia_ms": latencia_ms},
            )
        except Exception as exc:
            logger.warning("Langfuse trace falló (non-fatal): %s", exc)

    def score_recommendation(
        self,
        trace_id: str,
        scores: dict[str, float],
        comments: dict[str, str] | None = None,
    ) -> None:
        comments = comments or {}
        for name, value in scores.items():
            try:
                self._client.score(
                    trace_id=trace_id,
                    name=name,
                    value=value,
                    comment=comments.get(name),
                )
            except Exception as exc:
                logger.warning("Langfuse score '%s' falló (non-fatal): %s", name, exc)

    def flush(self) -> None:
        try:
            self._client.flush()
        except Exception as exc:
            logger.warning("Langfuse flush falló: %s", exc)


class NullObservabilityAdapter(ObservabilityPort):
    """No-op: usado cuando Langfuse no está configurado."""

    def trace_recommendation(self, *args, **kwargs) -> None:
        pass

    def score_recommendation(self, *args, **kwargs) -> None:
        pass

    def flush(self) -> None:
        pass

