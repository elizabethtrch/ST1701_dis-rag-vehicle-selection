"""
OpenAIAdapter – adaptador de salida para GPT-4o / GPT-4o-mini.
Implementa el puerto LLMProvider.
"""
from __future__ import annotations
import logging
import os
from src.core.ports.interfaces import LLMProvider, LLMResponse

logger = logging.getLogger(__name__)


class OpenAIAdapter(LLMProvider):

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "gpt-4o-mini",
    ) -> None:
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise ImportError("Instala openai: pip install openai") from exc

        self._model = model
        from openai import OpenAI
        self._client = OpenAI(api_key=api_key or os.environ["OPENAI_API_KEY"])

    @property
    def nombre_modelo(self) -> str:
        return self._model

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 1500,
    ) -> LLMResponse:
        response = self._client.chat.completions.create(
            model=self._model,
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        texto = response.choices[0].message.content
        usage = response.usage
        return LLMResponse(
            texto=texto,
            tokens_entrada=usage.prompt_tokens,
            tokens_salida=usage.completion_tokens,
            modelo=self._model,
        )

    def count_tokens(self, text: str) -> int:
        return len(text) // 4
