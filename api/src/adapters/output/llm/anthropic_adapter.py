"""
AnthropicAdapter – adaptador de salida para Claude (Anthropic).
Implementa el puerto LLMProvider.
"""
from __future__ import annotations
import logging
import os
from src.core.ports.interfaces import LLMProvider, LLMResponse

logger = logging.getLogger(__name__)


class AnthropicAdapter(LLMProvider):

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "claude-opus-4-6",
    ) -> None:
        try:
            import anthropic
        except ImportError as exc:
            raise ImportError("Instala anthropic: pip install anthropic") from exc

        self._model = model
        self._client = anthropic.Anthropic(
            api_key=api_key or os.environ["ANTHROPIC_API_KEY"]
        )

    @property
    def nombre_modelo(self) -> str:
        return self._model

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 1500,
    ) -> LLMResponse:
        import anthropic
        try:
            message = self._client.messages.create(
                model=self._model,
                max_tokens=max_tokens,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            )
            texto = message.content[0].text
            return LLMResponse(
                texto=texto,
                tokens_entrada=message.usage.input_tokens,
                tokens_salida=message.usage.output_tokens,
                modelo=self._model,
            )
        except anthropic.APIError as exc:
            logger.error("Error Anthropic API: %s", exc)
            raise

    def count_tokens(self, text: str) -> int:
        # Estimación simple: 1 token ≈ 4 caracteres
        return len(text) // 4
