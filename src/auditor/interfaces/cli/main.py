"""CLI (Typer). Ver .cursor/specs/fase4.spec.md, secao 5.

    audit run --tenant openiot --entity-type Streetlight
    audit run --tenant openiot --entity-type Streetlight --entity-id urn:ngsi-ld:Streetlight:001
    audit status --run-id <uuid>

`--tenant`/`--service-path` sao opcionais nos dois comandos — quando
omitidos, caem para FIWARE_SERVICE/FIWARE_SERVICE_PATH de .env (Settings),
o que faz `audit status --run-id <uuid>` funcionar sem repetir o tenant a
cada chamada num ambiente de desenvolvimento de tenant unico.

`run` e `status` chamam o mesmo `RunAuditUseCase`/`AuditRepositoryPort` que
a API REST (via o mesmo composition root, `infrastructure/config/container`)
— nenhuma logica de auditoria duplicada entre CLI e API.

`catalog sync` dispara `SyncCatalogUseCase` (Fase 8, secao 7) -- que
permanece administrativo por design (sem endpoint HTTP), mas ate' este
comando existir nao havia NENHUM jeito de popular o que `GET /catalog`
mostra fora dos testes unitarios; o resultado fica visivel na tela
Catalog do frontend depois de rodar este comando uma vez.
"""

from __future__ import annotations

import asyncio
import secrets
from uuid import UUID

import typer
from cryptography.fernet import InvalidToken
from sqlalchemy.exc import IntegrityError

from auditor.domain.entities.audit_run import AuditRun
from auditor.domain.value_objects.entity_type import EntityType
from auditor.domain.value_objects.tenant import Tenant
from auditor.infrastructure.config.container import (
    get_run_audit_use_case,
    get_settings,
    get_sync_catalog_use_case,
    get_sync_knowledge_base_use_case,
    get_tenant_account_repository,
    get_unit_of_work,
)

app = typer.Typer(help="CLI do FIWARE Conformance Auditor.")


def _resolve_tenant(tenant: str | None, service_path: str | None) -> Tenant:
    settings = get_settings()
    return Tenant(
        fiware_service=tenant if tenant is not None else settings.fiware_service,
        fiware_service_path=service_path or settings.fiware_service_path,
    )


def _print_summary(audit_run: AuditRun) -> None:
    s = audit_run.summary
    typer.echo(f"status: {audit_run.status.value}")
    typer.echo(
        "summary: "
        f"total={s.total_entities} conformant={s.conformant_count} "
        f"non_conformant={s.non_conformant_count} partial={s.partial_count} "
        f"no_model={s.no_model_count} schema_unavailable={s.schema_unavailable_count}"
    )


@app.command()
def run(
    tenant: str = typer.Option(None, "--tenant", help="Fiware-Service (default: FIWARE_SERVICE)."),
    entity_type: str = typer.Option(None, "--entity-type", help="Tipo NGSI a auditar (omitir = todos)."),
    entity_id: str = typer.Option(None, "--entity-id", help="Uma entidade especifica."),
    service_path: str = typer.Option(None, "--service-path", help="Fiware-ServicePath (default: /)."),
) -> None:
    """Executa uma auditoria e imprime o run_id e o status final quando termina."""
    t = _resolve_tenant(tenant, service_path)
    et = EntityType(entity_type) if entity_type else None

    async def _run() -> tuple[UUID, AuditRun | None]:
        use_case = get_run_audit_use_case()
        run_id = await use_case.execute(t, et, entity_id)
        uow = get_unit_of_work()
        async with uow:
            audit_run = await uow.audits.get_by_id(run_id, t)
        return run_id, audit_run

    try:
        run_id, audit_run = asyncio.run(_run())
    except Exception as exc:  # nunca um traceback cru na tela do usuario final
        typer.echo(f"Erro ao executar auditoria: {exc}", err=True)
        raise typer.Exit(code=1)

    typer.echo(f"run_id: {run_id}")
    if audit_run is not None:
        _print_summary(audit_run)


@app.command()
def status(
    run_id: str = typer.Option(..., "--run-id", help="UUID do run."),
    tenant: str = typer.Option(None, "--tenant", help="Fiware-Service (default: FIWARE_SERVICE)."),
    service_path: str = typer.Option(None, "--service-path", help="Fiware-ServicePath (default: /)."),
) -> None:
    """Consulta o status de um run existente."""
    try:
        parsed_run_id = UUID(run_id)
    except ValueError:
        typer.echo(f"run_id invalido: {run_id!r} (esperado um UUID).", err=True)
        raise typer.Exit(code=1)

    t = _resolve_tenant(tenant, service_path)

    async def _status() -> AuditRun | None:
        uow = get_unit_of_work()
        async with uow:
            return await uow.audits.get_by_id(parsed_run_id, t)

    try:
        audit_run = asyncio.run(_status())
    except Exception as exc:
        typer.echo(f"Erro ao consultar status: {exc}", err=True)
        raise typer.Exit(code=1)

    if audit_run is None:
        typer.echo(f"Run '{run_id}' nao encontrado para o tenant '{t.fiware_service}'.", err=True)
        raise typer.Exit(code=1)

    typer.echo(f"run_id: {audit_run.id}")
    _print_summary(audit_run)


catalog_app = typer.Typer(help="Comandos administrativos do catalogo de Smart Data Models.")
app.add_typer(catalog_app, name="catalog")


@catalog_app.command("sync")
def catalog_sync() -> None:
    """Sincroniza o catalogo de Smart Data Models (SyncCatalogUseCase) e
    registra o resultado -- visivel depois em `GET /catalog` e na tela
    Catalog do frontend, que ate' este comando existir sempre mostrava
    "nunca sincronizado" (nenhum outro gatilho existia no projeto)."""

    async def _sync():
        use_case = get_sync_catalog_use_case()
        return await use_case.execute()

    try:
        result = asyncio.run(_sync())
    except Exception as exc:  # nunca um traceback cru na tela do usuario final
        typer.echo(f"Erro ao sincronizar catalogo: {exc}", err=True)
        raise typer.Exit(code=1)

    if not result.success:
        typer.echo(f"Falha ao sincronizar catalogo: {result.reason}", err=True)
        raise typer.Exit(code=1)

    typer.echo(f"Catalogo sincronizado: {result.models_count} modelos.")


knowledge_app = typer.Typer(help="Comandos administrativos da base de conhecimento do RAG.")
app.add_typer(knowledge_app, name="knowledge")


@knowledge_app.command("sync")
def knowledge_sync() -> None:
    """Sincroniza knowledge_chunks a partir dos YAML curados em knowledge/
    (SyncKnowledgeBaseUseCase) -- ate' este comando existir nao havia
    NENHUM jeito de popular o indice do RAG fora dos testes de integracao;
    sem isso, PgVectorRetriever.retrieve() sempre voltava vazio em
    producao, mesmo com o corpus curado e valido em disco. Mesmo gap ja
    corrigido para o catalogo (ver `catalog sync` acima)."""

    async def _sync():
        use_case = get_sync_knowledge_base_use_case()
        return await use_case.execute()

    try:
        result = asyncio.run(_sync())
    except Exception as exc:  # nunca um traceback cru na tela do usuario final
        typer.echo(f"Erro ao sincronizar base de conhecimento: {exc}", err=True)
        raise typer.Exit(code=1)

    typer.echo(
        f"Base de conhecimento sincronizada: {result.total} chunks "
        f"({result.created} novos, {result.updated} atualizados, {result.deleted} removidos)."
    )


tenant_app = typer.Typer(help="Comandos administrativos das contas de tenant (ADR-0019).")
app.add_typer(tenant_app, name="tenant")


@tenant_app.command("rotate-keys")
def tenant_rotate_keys() -> None:
    """Re-cifra toda tenant_accounts.broker_api_key_encrypted com a primeira
    chave de BROKER_API_KEY_ENCRYPTION_KEYS (ADR-0019)."""

    async def _rotate() -> int:
        return await get_tenant_account_repository().rotate_encryption()

    try:
        count = asyncio.run(_rotate())
    except InvalidToken:
        typer.echo(
            "Erro ao rotacionar chaves: alguma linha nao decifra com nenhuma chave de "
            "BROKER_API_KEY_ENCRYPTION_KEYS; nada foi alterado.",
            err=True,
        )
        raise typer.Exit(code=1)
    except Exception as exc:
        typer.echo(f"Erro ao rotacionar chaves: {exc}", err=True)
        raise typer.Exit(code=1)

    typer.echo(f"Chaves rotacionadas: {count} linhas re-cifradas com a chave atual.")


_REGISTER_CONSTRAINT_MESSAGES = {
    "pk_tenant_accounts": "ja existe conta para este Fiware-Service/Fiware-ServicePath",
    "uq_tenant_accounts_login_email": "este email ja esta em uso",
}


@tenant_app.command("register")
def tenant_register(
    tenant: str = typer.Option(..., "--tenant", help="Fiware-Service."),
    service_path: str = typer.Option("/", "--service-path", help="Fiware-ServicePath."),
    broker_url: str = typer.Option(..., "--broker-url", help="URL do Orion do tenant."),
    broker_api_key: str = typer.Option(None, "--broker-api-key", help="Api key do broker (cifrada em repouso)."),
    email: str = typer.Option(None, "--email", help="Login SaaS (omitir = conta self-hosted, sem login)."),
    password: str = typer.Option(None, "--password", help="Senha inicial (omitida com --email = gerada e exibida uma unica vez)."),
) -> None:
    """Cadastra uma conta em tenant_accounts (ADR-0019)."""
    if password is not None and (email is None or not password):
        typer.echo("--password exige --email e nao pode ser vazia.", err=True)
        raise typer.Exit(code=1)
    if email is not None and not tenant:
        typer.echo("--email (conta SaaS) exige --tenant nao vazio.", err=True)
        raise typer.Exit(code=1)
    generated_password = secrets.token_urlsafe(16) if email is not None and password is None else None

    async def _register() -> None:
        await get_tenant_account_repository().create(
            Tenant(fiware_service=tenant, fiware_service_path=service_path),
            broker_url=broker_url,
            broker_api_key=broker_api_key,
            login_email=email,
            password=password if password is not None else generated_password,
        )

    try:
        asyncio.run(_register())
    except IntegrityError as exc:
        reason = next(
            (msg for name, msg in _REGISTER_CONSTRAINT_MESSAGES.items() if name in str(exc.orig)),
            "restricao do banco violada",
        )
        typer.echo(f"Erro ao registrar tenant: {reason}.", err=True)
        raise typer.Exit(code=1)
    except Exception as exc:
        typer.echo(f"Erro ao registrar tenant: {exc}", err=True)
        raise typer.Exit(code=1)

    typer.echo(f"Conta registrada: {tenant} {service_path}")
    if generated_password is not None:
        typer.echo(f"Senha inicial (exibida uma unica vez): {generated_password}")


if __name__ == "__main__":
    app()
