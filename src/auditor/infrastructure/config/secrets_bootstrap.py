"""Bootstrap de segredos para o Lambda de producao (ADR-0017), rodando UMA
VEZ por cold start, antes de `Settings()` (pydantic-settings) ser
instanciado — o equivalente, para Lambda, ao que o `user_data`/systemd do
EC2 (Fase 9, `api.sh.tftpl`/`worker.sh.tftpl`) faz escrevendo um `.env`:
popular `os.environ` com os valores reais, para o resto do container
(`infrastructure.config.container`) funcionar exatamente como no EC2, sem
nenhuma mudanca downstream.

Dois armazenamentos distintos, cada um pelo motivo certo (nao por
inconsistencia):

- **Secrets Manager**, so' para a senha do RDS: quando
  `modules/database` usa `manage_master_user_password=true` (Fase 9), a
  AWS gerencia esse segredo automaticamente e SO' o expõe via Secrets
  Manager — Parameter Store nao e' uma opcao aqui, e' uma decisao da
  propria feature do RDS, nao do ADR-0017.
- **Parameter Store (SecureString)**, para os segredos que o PROJETO cria
  (credenciais do Orion do cliente, chave de assinatura JWT) — decisao do
  ADR-0017, no lugar do Secrets Manager comum usado por
  `environments/academy`/`modules/secrets`: mesma criptografia via KMS,
  sem o custo por segredo/mes.

`Settings` continua sem saber nada de AWS — so' le `os.environ`/`.env`,
testavel sem mocks de boto3. Este modulo e' o unico lugar que fala com as
APIs de segredo da AWS.
"""

from __future__ import annotations

import json
import os
from typing import Mapping


def load_database_url_from_rds_managed_secret(
    *,
    secret_arn: str,
    host: str,
    port: int,
    database_name: str,
    driver: str = "postgresql+asyncpg",
    sslmode: str = "require",
    secretsmanager_client: object | None = None,
) -> None:
    """Monta `DATABASE_URL` a partir do segredo gerenciado do RDS
    (`{"username": ..., "password": ...}`, formato fixo do recurso
    `manage_master_user_password` — ver `modules/database/outputs.tf`,
    `master_user_secret_arn`) e grava em `os.environ["DATABASE_URL"]`.
    Nunca sobrescreve se a variavel ja' estiver presente (permite override
    manual em teste/execucao local)."""
    if "DATABASE_URL" in os.environ:
        return

    client = secretsmanager_client if secretsmanager_client is not None else _default_secretsmanager_client()
    response = client.get_secret_value(SecretId=secret_arn)
    credentials = json.loads(response["SecretString"])

    os.environ["DATABASE_URL"] = (
        f"{driver}://{credentials['username']}:{credentials['password']}"
        f"@{host}:{port}/{database_name}?sslmode={sslmode}"
    )


def load_env_vars_from_parameter_store(
    parameter_names_by_env_var: Mapping[str, str],
    *,
    ssm_client: object | None = None,
) -> None:
    """Para cada `{ENV_VAR: nome_do_parametro}`, busca o valor (sempre com
    `WithDecryption=True` — obrigatorio para `SecureString`) e grava em
    `os.environ[ENV_VAR]`. Nunca sobrescreve uma variavel ja' presente.

    Usado hoje para deixar `JWT_SIGNING_KEY`/`BROKER_API_KEY_ENCRYPTION_KEYS`
    disponiveis no ambiente do Lambda (a infraestrutura do
    `modules/parameter_store` já os provisiona, ADR-0017/ADR-0019) — ambos
    sao lidos por `Settings` (`jwt_signing_key`/
    `broker_api_key_encryption_keys`). `ORION_CREDENTIALS_JSON` continua
    sendo carregado por este mesmo mecanismo, mas sem consumidor
    downstream: `Settings` nao tem esse campo (`extra="ignore"`) — gap
    conhecido, fora do escopo deste ADR."""
    if not parameter_names_by_env_var:
        return

    client = ssm_client if ssm_client is not None else _default_ssm_client()

    for env_var, parameter_name in parameter_names_by_env_var.items():
        if env_var in os.environ:
            continue
        response = client.get_parameter(Name=parameter_name, WithDecryption=True)
        os.environ[env_var] = response["Parameter"]["Value"]


def _default_secretsmanager_client() -> object:
    import boto3

    return boto3.client("secretsmanager")


def _default_ssm_client() -> object:
    import boto3

    return boto3.client("ssm")
