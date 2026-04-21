"""
OllamaAdapter – adaptador para servidor Ollama local vía HTTP.
"""
from __future__ import annotations
import json
import urllib.request
from src.core.ports.interfaces import LLMProvider, LLMResponse


class OllamaAdapter(LLMProvider):
    """Invoca un servidor Ollama local vía HTTP."""

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "llama3.1",
        temperature: float = 0.2,
        top_p: float = 0.9,
        top_k: int = 40,
        repeat_penalty: float = 1.1,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model_name = model
        self._options = {
            "temperature": temperature,
            "top_p": top_p,
            "top_k": top_k,
            "repeat_penalty": repeat_penalty,
        }

    @property
    def nombre_modelo(self) -> str:
        return self._model_name

    @property
    def strict_output(self) -> bool:
        return True

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 1500,
    ) -> LLMResponse:
        payload = json.dumps({
            "model": self._model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "format": "json",
            "stream": False,
            "options": {"num_predict": max_tokens, **self._options},
        }).encode()

        req = urllib.request.Request(
            f"{self._base_url}/api/chat",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=600) as resp:
            data = json.loads(resp.read())

        texto = data.get("message", {}).get("content", "")
        return LLMResponse(
            texto=texto,
            tokens_entrada=data.get("prompt_eval_count", 0),
            tokens_salida=data.get("eval_count", 0),
            modelo=self._model_name,
        )

    def count_tokens(self, text: str) -> int:
        return len(text) // 4

