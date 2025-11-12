from __future__ import annotations

import asyncio
from dataclasses import dataclass

import httpx


class GroqClientError(RuntimeError):
    """Raised when the Groq API request fails."""


@dataclass
class GroqClient:
    api_key: str
    model: str = "llama-3-70b"
    timeout: float = 20.0

    _base_url: str = "https://api.groq.com/openai/v1/chat/completions"

    async def ask(self, question: str, *, stock_context: str) -> str:
        if not self.api_key:
            raise GroqClientError("Chave da API Groq não configurada.")

        payload = {
            "model": self.model,
            "temperature": 0.2,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Você é o assistente inteligente da Eos Cafés Especiais. "
                        "Responda em português brasileiro, de forma curta e objetiva, "
                        "usando emojis de café quando fizer sentido. Utilize os dados de estoque "
                        "fornecidos a seguir sempre que uma pergunta envolver quantidades: \n" + stock_context
                    ),
                },
                {"role": "user", "content": question},
            ],
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(self._base_url, headers=headers, json=payload)
                response.raise_for_status()
        except (httpx.HTTPError, asyncio.TimeoutError) as exc:  # pragma: no cover - thin wrapper
            raise GroqClientError("Não foi possível obter resposta da Groq.") from exc

        data = response.json()
        try:
            return data["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError) as exc:  # pragma: no cover - defensive
            raise GroqClientError("Resposta inválida recebida da Groq.") from exc
