"""Configuração central via variáveis de ambiente."""

import os
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _default_threads() -> int:
    """Heurística de threads para llama.cpp: núcleos físicos ≈ logical/2 (HT)."""
    cpu = os.cpu_count() or 4
    return max(1, cpu // 2)


class Settings(BaseSettings):
    """Configurações do DKRT carregadas de `.env`."""

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    fiware_broker_url: str = "http://localhost:1026"
    fiware_service: str = "openiot"
    fiware_service_path: str = "/"
    quantumleap_url: str = "http://localhost:8668"
    fiware_api_key: str = ""

    slm_enabled: bool = False
    slm_provider: str = "ollama"  # ollama | llama_cpp | transformers | heuristic
    slm_model: str = "microsoft/phi-2"  # usado apenas com slm_provider=transformers

    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5"
    ollama_timeout_seconds: float = 120.0

    llama_model_path: Path = (
        PROJECT_ROOT / "models" / "qwen2.5-3b-instruct-q4_k_m.gguf"
    )
    llama_model_repo: str = "Qwen/Qwen2.5-3B-Instruct-GGUF"
    llama_model_file: str = "qwen2.5-3b-instruct-q4_k_m.gguf"
    llama_n_ctx: int = 2048
    llama_n_threads: int = _default_threads()
    llama_n_batch: int = 512
    llama_n_ubatch: int = 512
    llama_flash_attn: bool = False
    llama_mlock: bool = False
    llama_n_gpu_layers: int = 0
    llama_max_tokens: int = 512
    llama_temperature: float = 0.4
    llama_verbose: bool = False

    chat_history_max_turns: int = 5

    mcp_server_host: str = "127.0.0.1"
    mcp_server_port: int = 8000

    agent_timeout_seconds: float = 30.0

    knowledge_chunks_path: Path = PROJECT_ROOT / "knowledge" / "chunks" / "chunks.jsonl"


@lru_cache
def get_settings() -> Settings:
    return Settings()