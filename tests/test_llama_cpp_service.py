"""Testes mockados para LlamaCppClient (sem baixar GGUF de verdade)."""

from __future__ import annotations

import json
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from context_broker_multiagent.services.llama_cpp_service import (
    LlamaCppClient,
    LlamaCppError,
)


@pytest.fixture
def fake_gguf(tmp_path: Path) -> Path:
    model = tmp_path / "qwen2.5-3b-instruct-q4_k_m.gguf"
    model.write_bytes(b"GGUF\x00\x00\x00\x00")
    return model


@pytest.fixture
def reset_llama_singleton():
    """Limpa o cache de classe do LlamaCppClient antes/depois de cada teste."""
    LlamaCppClient._model = None
    LlamaCppClient._model_path = None
    yield
    LlamaCppClient._model = None
    LlamaCppClient._model_path = None


@pytest.fixture
def mock_llama_cpp_module(monkeypatch):
    """Injeta um modulo llama_cpp falso para evitar carregar binarios nativos."""
    fake_llama = MagicMock()
    fake_instance = MagicMock()
    fake_instance.create_chat_completion.return_value = {
        "choices": [
            {
                "message": {
                    "content": json.dumps(
                        {
                            "response_type": "conversation",
                            "assistant_message": "Olá! resposta do mock llama.cpp",
                            "confidence": 0.95,
                        }
                    )
                }
            }
        ]
    }
    fake_llama.return_value = fake_instance

    fake_module = types.ModuleType("llama_cpp")
    fake_module.Llama = fake_llama
    monkeypatch.setitem(sys.modules, "llama_cpp", fake_module)
    return fake_llama, fake_instance


def test_missing_gguf_raises_with_friendly_message(tmp_path, reset_llama_singleton):
    client = LlamaCppClient(model_path=tmp_path / "naoexiste.gguf")
    with pytest.raises(LlamaCppError) as exc:
        client._ensure_loaded()
    assert "scripts/download_qwen_gguf.py" in str(exc.value)


@pytest.mark.asyncio
async def test_list_models_lists_only_gguf(tmp_path, reset_llama_singleton):
    (tmp_path / "qwen-a.gguf").write_bytes(b"x")
    (tmp_path / "qwen-b.gguf").write_bytes(b"y")
    (tmp_path / "ignored.txt").write_text("not gguf")

    client = LlamaCppClient(model_path=tmp_path / "qwen-a.gguf")
    models = await client.list_models()
    assert models == ["qwen-a.gguf", "qwen-b.gguf"]


@pytest.mark.asyncio
async def test_resolve_model_returns_filename_when_present(fake_gguf, reset_llama_singleton):
    client = LlamaCppClient(model_path=fake_gguf)
    assert await client.resolve_model() == fake_gguf.name


@pytest.mark.asyncio
async def test_chat_messages_calls_create_chat_completion(
    fake_gguf,
    reset_llama_singleton,
    mock_llama_cpp_module,
):
    fake_llama, fake_instance = mock_llama_cpp_module
    client = LlamaCppClient(model_path=fake_gguf, n_ctx=1024, n_threads=2)

    raw = await client.chat_messages(
        [{"role": "user", "content": "olá"}], json_mode=True
    )

    fake_llama.assert_called_once()
    init_kwargs = fake_llama.call_args.kwargs
    assert init_kwargs["model_path"] == str(fake_gguf)
    assert init_kwargs["n_ctx"] == 1024
    assert init_kwargs["n_threads"] == 2

    fake_instance.create_chat_completion.assert_called_once()
    call_kwargs = fake_instance.create_chat_completion.call_args.kwargs
    assert call_kwargs["response_format"] == {"type": "json_object"}
    assert call_kwargs["messages"][0]["content"] == "olá"

    parsed = json.loads(raw)
    assert parsed["response_type"] == "conversation"


@pytest.mark.asyncio
async def test_model_loaded_once_across_calls(
    fake_gguf,
    reset_llama_singleton,
    mock_llama_cpp_module,
):
    """Modelo deve permanecer em RAM — não recarregar a cada chat."""
    fake_llama, _ = mock_llama_cpp_module
    client = LlamaCppClient(model_path=fake_gguf)

    await client.chat_messages([{"role": "user", "content": "primeira"}])
    await client.chat_messages([{"role": "user", "content": "segunda"}])
    await client.chat_messages([{"role": "user", "content": "terceira"}])

    assert fake_llama.call_count == 1  # construtor da classe Llama uma única vez
