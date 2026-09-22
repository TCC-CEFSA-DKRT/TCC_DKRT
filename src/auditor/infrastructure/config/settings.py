"""Settings — pydantic-settings lendo de variaveis de ambiente/.env. Ver
docs/plano_refatoracao_v3.md, Parte III, 2.2
(infrastructure/config/settings.py) e .env.example.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    fiware_broker_url: str = "http://localhost:1026"
    fiware_service: str = "openiot"
    fiware_service_path: str = "/"
    database_url: str = "postgresql+asyncpg://auditor:auditor@localhost:5433/auditor"

    # Fase 7 (.cursor/specs/fase7.spec.md, secao 5) -- Ollama local/dev.
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:7b-instruct"

    # Fase 8 (.cursor/specs/fase8.spec.md, secao 9): o frontend Angular
    # roda via `ng serve` (porta padrao 4200) contra esta API local -- sem
    # CORS liberado para essa origem, todo fetch do navegador falharia
    # antes mesmo de chegar num router. Lista separada por virgula via env
    # (CORS_ALLOWED_ORIGINS) para producao poder restringir/trocar sem
    # mudar codigo.
    cors_allowed_origins: str = "http://localhost:4200"

    # Follow-up pos-Fase 8: intervalo (s) entre sincronizacoes automaticas
    # do catalogo de Smart Data Models (CatalogSyncScheduler, rodando em
    # background dentro do processo da API -- ver interfaces/rest/app.py).
    # Default 24h: o catalogo upstream nao muda com frequencia maior que
    # isso na pratica; `audit catalog sync` (CLI) continua disponivel para
    # forcar uma sincronizacao imediata quando necessario.
    catalog_sync_interval_seconds: float = 86400.0

    # ADR-0017 -- corrige um gap real encontrado ao implementar o Lambda de
    # producao: container.get_job_queue() retornava sempre LocalJobQueue(),
    # mesmo com QUEUE_BACKEND=sqs/SQS_QUEUE_URL ja' escritos pelo
    # user_data do EC2 desde a Fase 9 (api.sh.tftpl/worker.sh.tftpl) -- os
    # dois nunca eram lidos pela aplicacao. "local" (default, dev) usa
    # LocalJobQueue; "sqs" troca para SqsJobQueue (exige sqs_queue_url).
    queue_backend: str = "local"
    sqs_queue_url: str | None = None
    sqs_dead_letter_queue_url: str | None = None

    @property
    def cors_allowed_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_allowed_origins.split(",") if origin.strip()]
