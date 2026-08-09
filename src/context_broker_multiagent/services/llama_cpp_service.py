"""LlamaCppClient — backend SLM in-process via llama-cpp-python (GGUF/Qwen2.5).

Vantagens sobre Ollama:
- Roda no mesmo processo Python (sem daemon externo).
- Modelo permanece em RAM entre turns (cold start único na primeira chamada).
- Controle direto dos flags (n_threads, n_batch, n_ubatch, n_ctx, flash_attn).
- Distribuível: basta o pacote pip + arquivo GGUF.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from threading import Lock
from typing import Any

from context_broker_multiagent.config import get_settings

logger = logging.getLogger(__name__)


class LlamaCppError(RuntimeError):
    """Erro ao comunicar com o backend llama.cpp."""


class LlamaCppClient:
    """Wrapper assíncrono sobre llama_cpp.Llama, compatível com OllamaClient.

    O modelo é carregado uma única vez (cache de classe) e compartilhado entre
    instâncias para evitar recarregar 2GB toda vez que o serviço é instanciado.
    """

    _model: Any = None
    _model_path: Path | None = None
    _load_lock = Lock()

    def __init__(
        self,
        model_path: Path | str | None = None,
        n_ctx: int | None = None,
        n_threads: int | None = None,
        n_batch: int | None = None,
        n_ubatch: int | None = None,
        flash_attn: bool | None = None,
        mlock: bool | None = None,
        n_gpu_layers: int | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        verbose: bool | None = None,
    ) -> None:
        settings = get_settings()
        self.model_path = Path(model_path or settings.llama_model_path)
        self.n_ctx = n_ctx if n_ctx is not None else settings.llama_n_ctx
        self.n_threads = n_threads if n_threads is not None else settings.llama_n_threads
        self.n_batch = n_batch if n_batch is not None else settings.llama_n_batch
        self.n_ubatch = n_ubatch if n_ubatch is not None else settings.llama_n_ubatch
        self.flash_attn = flash_attn if flash_attn is not None else settings.llama_flash_attn
        self.mlock = mlock if mlock is not None else settings.llama_mlock
        self.n_gpu_layers = (
            n_gpu_layers if n_gpu_layers is not None else settings.llama_n_gpu_layers
        )
        self.max_tokens = max_tokens if max_tokens is not None else settings.llama_max_tokens
        self.temperature = (
            temperature if temperature is not None else settings.llama_temperature
        )
        self.verbose = verbose if verbose is not None else settings.llama_verbose

    @property
    def model(self) -> str:
        """Nome amigável (compat com OllamaClient.model usado no /status)."""
        return self.model_path.name

    @model.setter
    def model(self, _: str) -> None:
        # Mantido por compat com OllamaClient.model = "..." em /model command;
        # alterar GGUF em runtime exigiria reload, fora do escopo deste cliente.
        pass

    def _ensure_loaded(self) -> Any:
        """Carrega o modelo GGUF apenas uma vez por processo."""
        cls = type(self)
        if cls._model is not None and cls._model_path == self.model_path:
            return cls._model

        if not self.model_path.exists():
            raise LlamaCppError(
                f"Modelo GGUF não encontrado em {self.model_path}. "
                "Baixe com: python scripts/download_qwen_gguf.py"
            )

        with cls._load_lock:
            if cls._model is not None and cls._model_path == self.model_path:
                return cls._model
            try:
                from llama_cpp import Llama
            except ImportError as exc:
                raise LlamaCppError(
                    "llama-cpp-python não instalado. Execute: "
                    "pip install -e .[slm-cpp]"
                ) from exc

            logger.info(
                "Carregando GGUF %s (n_ctx=%d, threads=%d, flash_attn=%s)",
                self.model_path.name,
                self.n_ctx,
                self.n_threads,
                self.flash_attn,
            )
            cls._model = Llama(
                model_path=str(self.model_path),
                n_ctx=self.n_ctx,
                n_threads=self.n_threads,
                n_batch=self.n_batch,
                n_ubatch=self.n_ubatch,
                flash_attn=self.flash_attn,
                use_mlock=self.mlock,
                n_gpu_layers=self.n_gpu_layers,
                verbose=self.verbose,
            )
            cls._model_path = self.model_path
        return cls._model

    async def list_models(self) -> list[str]:
        """Modelos GGUF descobertos no diretório do modelo configurado."""
        directory = self.model_path.parent
        if not directory.exists():
            return []
        return sorted(p.name for p in directory.glob("*.gguf"))

    async def resolve_model(self) -> str:
        """No-op para llama_cpp: o modelo é fixo no path. Garante que existe."""
        if not self.model_path.exists():
            raise LlamaCppError(
                f"Modelo GGUF ausente: {self.model_path}. "
                "Baixe com `python scripts/download_qwen_gguf.py`."
            )
        return self.model

    async def chat(
        self,
        *,
        system: str,
        user: str,
        json_mode: bool = True,
    ) -> str:
        """Compat com OllamaClient.chat (system + user single-turn)."""
        return await self.chat_messages(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            json_mode=json_mode,
        )

    async def chat_messages(
        self,
        messages: list[dict[str, str]],
        *,
        json_mode: bool = True,
    ) -> str:
        """Chat multi-turn via Llama.create_chat_completion (executado em thread)."""
        return await asyncio.to_thread(self._chat_messages_sync, messages, json_mode)

    def _chat_messages_sync(
        self,
        messages: list[dict[str, str]],
        json_mode: bool,
    ) -> str:
        model = self._ensure_loaded()
        kwargs: dict[str, Any] = {
            "messages": messages,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        try:
            result = model.create_chat_completion(**kwargs)
        except Exception as exc:
            raise LlamaCppError(f"Falha na inferência llama.cpp: {exc}") from exc

        choices = result.get("choices") or []
        if not choices:
            raise LlamaCppError("Resposta sem choices do llama.cpp")
        content = (choices[0].get("message") or {}).get("content", "").strip()
        if not content:
            raise LlamaCppError("Resposta vazia do llama.cpp")

        if json_mode:
            try:
                json.loads(content)
            except json.JSONDecodeError:
                logger.debug("llama.cpp não retornou JSON estrito; segue raw")
        return content
