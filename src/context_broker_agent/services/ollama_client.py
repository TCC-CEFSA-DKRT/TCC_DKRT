"""Cliente HTTP para API Ollama (Qwen2.5 e outros SLMs locais)."""

from __future__ import annotations

import aiohttp

from context_broker_multiagent.config import get_settings


class OllamaError(Exception):
    """Erro ao comunicar com o Ollama."""


class OllamaClient:
    """Wrapper mínimo da API REST do Ollama."""

    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        timeout_seconds: float | None = None,
    ) -> None:
        settings = get_settings()
        self.base_url = (base_url or settings.ollama_base_url).rstrip("/")
        self.model = model or settings.ollama_model
        self.timeout_seconds = timeout_seconds or settings.ollama_timeout_seconds

    async def list_models(self) -> list[str]:
        """Lista modelos instalados (`ollama list`)."""
        url = f"{self.base_url}/api/tags"
        timeout = aiohttp.ClientTimeout(total=self.timeout_seconds)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url) as resp:
                if resp.status >= 400:
                    text = await resp.text()
                    raise OllamaError(f"HTTP {resp.status}: {text[:300]}")
                data = await resp.json()
        return [m.get("name", "") for m in data.get("models", []) if m.get("name")]

    async def resolve_model(self) -> str:
        """Garante que self.model existe no Ollama (ex.: qwen2.5 → qwen2.5:3b)."""
        models = await self.list_models()
        if not models:
            raise OllamaError(
                f"Nenhum modelo no Ollama. Instale com: ollama pull {self.model}"
            )
        if self.model in models:
            return self.model
        prefix = f"{self.model}:"
        for name in models:
            if name.startswith(prefix) or name.split(":")[0] == self.model.split(":")[0]:
                self.model = name
                return self.model
        raise OllamaError(
            f"Modelo '{self.model}' não encontrado. Instalados: {', '.join(models)}. "
            f"No chat use: /model {models[0]}"
        )

    async def chat(
        self,
        *,
        system: str,
        user: str,
        json_mode: bool = True,
    ) -> str:
        """Envia mensagens ao endpoint /api/chat e retorna o conteúdo da resposta."""
        await self.resolve_model()
        payload: dict = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": False,
        }
        if json_mode:
            payload["format"] = "json"

        url = f"{self.base_url}/api/chat"
        timeout = aiohttp.ClientTimeout(total=self.timeout_seconds)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, json=payload) as resp:
                text = await resp.text()
                if resp.status >= 400:
                    raise OllamaError(f"HTTP {resp.status}: {text[:500]}")
                data = await resp.json(content_type=None)

        message = data.get("message") or {}
        content = message.get("content", "")
        if not content:
            raise OllamaError("Resposta vazia do Ollama")
        return content

    async def chat_messages(
        self,
        messages: list[dict[str, str]],
        *,
        json_mode: bool = True,
    ) -> str:
        """Chat multi-turn (/api/chat) com histórico de mensagens."""
        await self.resolve_model()
        payload: dict = {
            "model": self.model,
            "messages": messages,
            "stream": False,
        }
        if json_mode:
            payload["format"] = "json"

        url = f"{self.base_url}/api/chat"
        timeout = aiohttp.ClientTimeout(total=self.timeout_seconds)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, json=payload) as resp:
                text = await resp.text()
                if resp.status >= 400:
                    raise OllamaError(f"HTTP {resp.status}: {text[:500]}")
                data = await resp.json(content_type=None)

        content = (data.get("message") or {}).get("content", "")
        if not content:
            raise OllamaError("Resposta vazia do Ollama")
        return content
