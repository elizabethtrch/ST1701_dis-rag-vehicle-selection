"""
GoogleAdapter – adaptador para Gemini.
"""
from __future__ import annotations
import logging
import os
from src.core.ports.interfaces import LLMProvider, LLMResponse

logger = logging.getLogger(__name__)


class GoogleAdapter(LLMProvider):

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "gemini-1.5-flash",
    ) -> None:
        try:
            import google.generativeai as genai
        except ImportError as exc:
            raise ImportError(
                "Instala google-generativeai: pip install google-generativeai"
            ) from exc

        import google.generativeai as genai
        self._model_name = model
        genai.configure(api_key=api_key or os.environ["GOOGLE_API_KEY"])
        self._model = genai.GenerativeModel(model)

    @property
    def nombre_modelo(self) -> str:
        return self._model_name

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 1500,
    ) -> LLMResponse:
        prompt_completo = f"{system_prompt}\n\n{user_prompt}"
        response = self._model.generate_content(prompt_completo)
        texto = response.text
        # Gemini no siempre expone conteo de tokens de forma sencilla
        tokens_in = len(prompt_completo) // 4
        tokens_out = len(texto) // 4
        return LLMResponse(
            texto=texto,
            tokens_entrada=tokens_in,
            tokens_salida=tokens_out,
            modelo=self._model_name,
        )

    def count_tokens(self, text: str) -> int:
        return len(text) // 4
