"""Fase 3 — teste de assinatura da AuditRepositoryPort. Ver
.cursor/specs/fase3.spec.md, secao 4 (ultimo bullet).

Torna o requisito de seguranca "impossivel esquecer tenant num endpoint novo"
verificavel por maquina: varre TODOS os metodos publicos da porta (exceto
create_run, que recebe o AuditRun inteiro — e ja carrega tenant embutido) e
falha se algum deles nao tiver `tenant` como parametro obrigatorio (sem
default). Roda sem banco, sem rede — puro `inspect`.
"""

import inspect

from auditor.domain.ports.audit_repository_port import AuditRepositoryPort

_EXEMPT_METHODS = {"create_run"}  # recebe AuditRun inteiro, que ja tem .tenant


def _public_methods(protocol_cls) -> list[tuple[str, object]]:
    return [
        (name, member)
        for name, member in inspect.getmembers(protocol_cls, predicate=inspect.isfunction)
        if not name.startswith("_") and name not in _EXEMPT_METHODS
    ]


def test_every_non_exempt_method_requires_tenant_explicitly():
    offenders = []
    methods = _public_methods(AuditRepositoryPort)
    assert methods, "nenhum metodo encontrado — a porta mudou de forma inesperada?"

    for name, member in methods:
        signature = inspect.signature(member)
        tenant_param = signature.parameters.get("tenant")
        if tenant_param is None:
            offenders.append(f"{name}: sem parametro 'tenant'")
        elif tenant_param.default is not inspect.Parameter.empty:
            offenders.append(f"{name}: 'tenant' tem valor padrao ({tenant_param.default!r})")

    assert not offenders, (
        "Todo metodo de AuditRepositoryPort (exceto create_run) deve exigir "
        f"'tenant' obrigatorio, sem default. Violacoes: {offenders}"
    )


def test_create_run_is_exempt_but_still_carries_tenant_via_the_run_object():
    # Documenta o motivo da excecao, nao so aplica ela.
    signature = inspect.signature(AuditRepositoryPort.create_run)
    assert "tenant" not in signature.parameters
    assert "run" in signature.parameters
