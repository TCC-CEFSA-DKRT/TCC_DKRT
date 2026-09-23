"""Handler Lambda da API REST — ADR-0017. Substitui o Uvicorn do EC2
(`modules/compute`, Fase 9) atras do ALB (`modules/lambda_compute`,
`image_config.command` deste Dockerfile default): o ALB encaminha o
request HTTP diretamente para esta funcao (target type `lambda`, sem API
Gateway — ver `docs/design/implantacao-aws.html`, card "Compute"), Mangum
traduz o evento do ALB para ASGI e chama a MESMA app FastAPI de
`interfaces/rest/app.py`, sem duplicar nenhuma rota.

`bootstrap_settings_from_aws()` roda no module-level, ou seja, uma unica
vez por cold start do container Lambda — precisa terminar antes de
`create_app()` importar (transitivamente) `infrastructure.config.container`,
que instancia `Settings()` (lru_cache) na primeira chamada a
`get_settings()`. Chamadas subsequentes (warm start) reusam o mesmo
processo/os.environ ja' populado; `load_database_url_from_rds_managed_secret`/
`load_env_vars_from_parameter_store` nunca sobrescrevem uma env var ja'
presente, entao chamar de novo em cada cold start novo e' seguro e nao
custa nada em warm start (a funcao so' e' executada uma vez, aqui).

`start_background_workers=False`: o Worker roda como funcao Lambda propria
(`worker_handler.py`), acionada pelo event source mapping da fila SQS, nao
por uma task asyncio em background dentro do processo da API — um
container Lambda de API pode ser reciclado/congelado a qualquer momento
entre invocacoes, o que tornaria um `AuditWorker`/`CatalogSyncScheduler` em
background la' dentro nao-confiavel (ver `interfaces/rest/app.py`,
`_make_lifespan`)."""

from __future__ import annotations

from auditor.interfaces.aws_lambda._bootstrap import bootstrap_settings_from_aws

bootstrap_settings_from_aws()

from mangum import Mangum  # noqa: E402  (import apos o bootstrap de proposito)

from auditor.interfaces.rest.app import create_app  # noqa: E402

app = create_app(start_background_workers=False)

handler = Mangum(app, lifespan="auto")
