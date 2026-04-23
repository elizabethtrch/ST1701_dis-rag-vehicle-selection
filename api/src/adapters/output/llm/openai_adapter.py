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
        temperature: float = 0.2,
        timeout: float = 60.0,
    ) -> None:
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise ImportError("Instala openai: pip install openai") from exc

        self._model = model
        self._temperature = temperature
        self._timeout = timeout
        self._client = OpenAI(
            api_key=api_key or os.environ["OPENAI_API_KEY"],
            timeout=timeout,
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
        import openai

        try:
            response = self._client.chat.completions.create(
                model=self._model,
                max_tokens=max_tokens,
                temperature=self._temperature,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            )
            texto = response.choices[0].message.content or ""
            usage = response.usage
            return LLMResponse(
                texto=texto,
                tokens_entrada=usage.prompt_tokens,
                tokens_salida=usage.completion_tokens,
                modelo=response.model,
            )
        except openai.AuthenticationError as exc:
            logger.error("OpenAI: API key inválida: %s", exc)
            raise
        except openai.RateLimitError as exc:
            logger.error("OpenAI: rate limit alcanzado: %s", exc)
            raise
        except openai.APITimeoutError as exc:
            logger.error("OpenAI: timeout (%.0fs): %s", self._timeout, exc)
            raise
        except openai.APIConnectionError as exc:
            logger.error("OpenAI: error de conexión: %s", exc)
            raise
        except openai.APIError as exc:
            logger.error("OpenAI: error de API [%s]: %s", type(exc).__name__, exc)
            raise

    def count_tokens(self, text: str) -> int:
        try:
            import tiktoken
            enc = tiktoken.encoding_for_model(self._model)
            return len(enc.encode(text))
        except Exception:
            return len(text) // 4

