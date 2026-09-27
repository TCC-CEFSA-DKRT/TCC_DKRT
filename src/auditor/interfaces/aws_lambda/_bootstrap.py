"""Bootstrap de configuracao compartilhado pelos tres handlers Lambda
(api_handler, worker_handler, worker_dlq_handler) — ADR-0017. Roda no
module-level de cada handler (ou seja, uma vez por cold start do
container), antes de qualquer import que acabe instanciando
`Settings`/`container.get_*` — mesmo raciocinio do comentario em
`infrastructure/config/secrets_bootstrap.py`.

Le a PROPRIA localizacao dos segredos (ARN do RDS-managed secret, nomes dos
parametros no Parameter Store) de variaveis de ambiente simples — essas
NAO sao segredo, sao só "onde procurar o segredo" (equivalente a um
`.tfvars`), e por isso podem ser variaveis de ambiente Lambda comuns
(`modules/lambda_compute` as define via Terraform, ver `environment` do
`aws_lambda_function`)."""

from __future__ import annotations

import os

from auditor.infrastructure.config.secrets_bootstrap import (
    load_database_url_from_rds_managed_secret,
    load_env_vars_from_parameter_store,
)


def bootstrap_settings_from_aws() -> None:
    secret_arn = os.environ.get("DB_MASTER_USER_SECRET_ARN")
    if secret_arn:
        load_database_url_from_rds_managed_secret(
            secret_arn=secret_arn,
            host=os.environ["DB_HOST"],
            port=int(os.environ["DB_PORT"]),
            database_name=os.environ["DB_NAME"],
        )

    parameter_names_by_env_var = {}
    if "ORION_CREDENTIALS_PARAMETER_NAME" in os.environ:
        parameter_names_by_env_var["ORION_CREDENTIALS_JSON"] = os.environ[
            "ORION_CREDENTIALS_PARAMETER_NAME"
        ]
    if "JWT_SIGNING_KEY_PARAMETER_NAME" in os.environ:
        parameter_names_by_env_var["JWT_SIGNING_KEY"] = os.environ[
            "JWT_SIGNING_KEY_PARAMETER_NAME"
        ]
    if "BROKER_API_KEY_ENCRYPTION_KEYS_PARAMETER_NAME" in os.environ:
        parameter_names_by_env_var["BROKER_API_KEY_ENCRYPTION_KEYS"] = os.environ[
            "BROKER_API_KEY_ENCRYPTION_KEYS_PARAMETER_NAME"
        ]
    load_env_vars_from_parameter_store(parameter_names_by_env_var)
