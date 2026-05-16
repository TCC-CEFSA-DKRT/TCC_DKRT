"""Configuração central via variáveis de ambiente."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


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
    fiware_api_key: str = ""

    slm_enabled: bool = False
    slm_provider: str = "ollama"  # ollama | transformers | heuristic (forçado se slm_enabled=false)
    slm_model: str = "microsoft/phi-2"  # usado apenas com slm_provider=transformers

    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5"
    ollama_timeout_seconds: float = 120.0

    chat_history_max_turns: int = 5

    mcp_server_host: str = "127.0.0.1"
    mcp_server_port: int = 8000

    agent_timeout_seconds: float = 30.0

    knowledge_chunks_path: Path = PROJECT_ROOT / "knowledge" / "chunks" / "chunks.jsonl"


@lru_cache
def get_settings() -> Settings:
    return Settings()
