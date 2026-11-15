"""Caixa-preta da borda HTTP (RF-03..RF-07): so' request -> status/corpo.

A API roda in-process (httpx.ASGITransport) com dependencias substituidas por
fakes — sem Orion, Postgres, fila ou Ollama. Tecnicas: classes de
equivalencia (CE) e analise de valor-limite (AVL) sobre os campos de entrada
validados por `schemas.py`; casos com defeito conhecido ficam como xfail
estrito e sao descritos no relatorio de defeitos."""

from __future__ import annotations

from datetime import datetime, timezone

import httpx
import pytest

from auditor.domain.ports.audit_repository_port import Page
from auditor.domain.ports.command_interpreter_port import AuditCommandInterpretation
from auditor.domain.value_objects.tenant import Tenant
from auditor.infrastructure.config.container import (
    get_interpret_audit_command_use_case,
    get_run_audit_use_case,
    get_selfhosted_accounts,
    get_settings,
    get_tenant_account_repository,
    get_unit_of_work,
)
from auditor.infrastructure.config.settings import Settings
from auditor.infrastructure.persistence.tenant_account_repository import TenantAccount, hash_password
from auditor.interfaces.rest import app as app_module
from auditor.interfaces.rest.schemas import COMMAND_TEXT_MAX_LENGTH

from .casos import Caso, param

H = {"Fiware-Service": "openiot", "Fiware-ServicePath": "/"}


# --- fakes minimos (sem I/O) -------------------------------------------------
class _RunAudit:
    async def start(self, tenant, entity_type=None, entity_id=None):
        from uuid import uuid4

        return uuid4()


class _Interpret:
    async def execute(self, tenant, command_text):
        return AuditCommandInterpretation(None, None, 0.0, command_text)


class _Repo:
    async def list_runs(self, tenant, filters):
        return Page(items=[], page=filters.page, page_size=filters.page_size, total=0)

    async def list_run_summaries_over_time(self, tenant, entity_type):
        return []


class _Uow:
    audits = _Repo()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return None


class _Accounts:
    """Contas self-hosted: get_single/create/replace_tenant (RF-06)."""

    def __init__(self):
        self.atual = None
        self.criadas = []

    async def get_single(self):
        return self.atual

    async def create(self, tenant, broker_url, broker_api_key=None):
        self.criadas.append((tenant, broker_url))

    async def replace_tenant(self, atual, novo, broker_url, broker_api_key=None):
        self.criadas.append((novo, broker_url))


class _Logins:
    def __init__(self, senha="senha-correta-123"):
        agora = datetime.now(timezone.utc)
        self._conta = TenantAccount(
            Tenant("acme", "/"), "https://orion.example.com", None, "user@example.com",
            hash_password(senha), agora, agora,
        )

    async def get_by_login_email(self, email):
        return self._conta if email.strip().lower() == "user@example.com" else None


def _cliente(monkeypatch, settings=None, accounts=None, logins=None):
    settings = settings or Settings(_env_file=None)
    monkeypatch.setattr(app_module, "get_settings", lambda: settings)
    app = app_module.create_app()
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_run_audit_use_case] = lambda: _RunAudit()
    app.dependency_overrides[get_interpret_audit_command_use_case] = lambda: _Interpret()
    app.dependency_overrides[get_unit_of_work] = lambda: _Uow()
    app.dependency_overrides[get_selfhosted_accounts] = lambda: accounts
    if logins is not None:
        app.dependency_overrides[get_tenant_account_repository] = lambda: logins
    # raise_app_exceptions=False: uma excecao nao tratada vira resposta 500,
    # como acontece num servidor real (o cliente de teste nao a relanca).
    transporte = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    return httpx.AsyncClient(transport=transporte, base_url="http://t")


_PRE_SEM = "API no ar com dependências simuladas; sem autenticação (modo self-hosted)."


def _c(id, req, tec, nome, dados, esperado, prio="Média", defeito=None, pre=_PRE_SEM, desc=None):
    return Caso(id, req, tec, nome, desc or "Enviar a requisição HTTP e verificar o status.", pre, dados, esperado, prio, defeito)


# ============================ RF-03: POST /audits/interpret ===================
_DESC_NL = "POST /audits/interpret com {command_text: <texto>}."
_NL = [  # (id, nome, texto-ou-corpo, status, tecnica, defeito)
    ("CT-API-01", "Vazio (0 caracteres): limite inferior −", "", 422, "AVL", None),
    ("CT-API-02", "1 caractere: limite inferior", "a", 200, "AVL", None),
    ("CT-API-03", "2 caracteres: limite inferior +", "ab", 200, "AVL", None),
    ("CT-API-04", "499 caracteres: limite superior −", "a" * 499, 200, "AVL", None),
    ("CT-API-05", "500 caracteres: limite superior", "a" * COMMAND_TEXT_MAX_LENGTH, 200, "AVL", None),
    ("CT-API-06", "501 caracteres: limite superior +", "a" * 501, 422, "AVL", None),
    ("CT-API-07", "Frase típica em português", "audite os postes de luz", 200, "CE", None),
    ("CT-API-08", "Somente espaços (comando semanticamente vazio)", "   ", 422, "CE", "D-06"),
]
CASOS_NL = [
    (_c(i, "RF-03", t, n, f"command_text={texto[:12]!r}… (len={len(texto)})", f"HTTP {st}",
        "Alta" if t == "AVL" else "Média", d, desc=_DESC_NL), texto, st)
    for i, n, texto, st, t, d in _NL
]


@pytest.mark.asyncio
@pytest.mark.parametrize("caso,texto,status", [param(*t) for t in CASOS_NL])
async def test_interpret_command_text(monkeypatch, caso, texto, status):
    async with _cliente(monkeypatch) as c:
        r = await c.post("/audits/interpret", json={"command_text": texto}, headers=H)

    assert r.status_code == status


_NL_INV = [
    ("CT-API-09", "Campo command_text ausente", {}),
    ("CT-API-10", "command_text com tipo errado (número)", {"command_text": 123}),
    ("CT-API-11", "command_text nulo", {"command_text": None}),
]
CASOS_NL_INV = [(_c(i, "RF-03", "CE", n, str(b), "HTTP 422", desc=_DESC_NL), b) for i, n, b in _NL_INV]


@pytest.mark.asyncio
@pytest.mark.parametrize("caso,corpo", [param(*t) for t in CASOS_NL_INV])
async def test_interpret_corpo_invalido(monkeypatch, caso, corpo):
    async with _cliente(monkeypatch) as c:
        r = await c.post("/audits/interpret", json=corpo, headers=H)

    assert r.status_code == 422


# ============================ RF-04: POST /audits ============================
_AU = [
    ("CT-API-12", "Auditoria de um tipo", {"entity_type": "Streetlight"}, 202, None),
    ("CT-API-13", "Auditoria ampla (corpo vazio)", {}, 202, None),
    ("CT-API-14", "entity_type com tipo errado (número)", {"entity_type": 5}, 422, None),
    ("CT-API-15", "entity_type só com espaços", {"entity_type": "   "}, 422, "D-06"),
]
CASOS_AU = [(_c(i, "RF-04", "CE", n, str(b), f"HTTP {st}", "Alta", d, desc="POST /audits com o corpo indicado."), b, st) for i, n, b, st, d in _AU]


@pytest.mark.asyncio
@pytest.mark.parametrize("caso,corpo,status", [param(*t) for t in CASOS_AU])
async def test_criar_auditoria(monkeypatch, caso, corpo, status):
    async with _cliente(monkeypatch) as c:
        r = await c.post("/audits", json=corpo, headers=H)

    assert r.status_code == status


# ============================ RF-05: GET /audits (paginacao) ==================
# Contrato proposto no plano de testes: page >= 1 e 1 <= page_size <= 100.
_PG = [
    ("CT-PAG-01", "page=1 (limite inferior)", "page=1", 200, "AVL", None),
    ("CT-PAG-02", "page=0 (abaixo do limite)", "page=0", 422, "AVL", "D-01"),
    ("CT-PAG-03", "page=-1", "page=-1", 422, "AVL", "D-01"),
    ("CT-PAG-04", "page=abc (tipo inválido)", "page=abc", 422, "CE", None),
    ("CT-PAG-05", "page_size=1 (limite inferior)", "page_size=1", 200, "AVL", None),
    ("CT-PAG-06", "page_size=0 (abaixo do limite)", "page_size=0", 422, "AVL", "D-01"),
    ("CT-PAG-07", "page_size=-5", "page_size=-5", 422, "AVL", "D-01"),
    ("CT-PAG-08", "page_size=100 (limite superior)", "page_size=100", 200, "AVL", None),
    ("CT-PAG-09", "page_size=101 (acima do limite)", "page_size=101", 422, "AVL", "D-01"),
    ("CT-PAG-10", "page_size=1000000 (carga abusiva)", "page_size=1000000", 422, "AVL", "D-01"),
    ("CT-PAG-11", "Filtro status válido", "status=failed", 200, "CE", None),
    ("CT-PAG-12", "Filtro status inexistente", "status=invalido", 422, "CE", None),
    ("CT-PAG-13", "Sem parâmetros (padrões)", "", 200, "CE", None),
]
CASOS_PG = [(_c(i, "RF-05", t, n, f"GET /audits?{q}", f"HTTP {st}", "Alta" if d else "Média", d, desc="GET /audits com a query indicada."), q, st) for i, n, q, st, t, d in _PG]


@pytest.mark.asyncio
@pytest.mark.parametrize("caso,query,status", [param(*t) for t in CASOS_PG])
async def test_listar_execucoes(monkeypatch, caso, query, status):
    async with _cliente(monkeypatch) as c:
        r = await c.get(f"/audits?{query}", headers=H)

    assert r.status_code == status


_SUM = [
    ("CT-PAG-14", "summary-over-time com tipo válido", "entity_type=Streetlight", 200, None),
    ("CT-PAG-15", "summary-over-time sem o parâmetro", "", 422, None),
    ("CT-PAG-16", "summary-over-time com tipo vazio", "entity_type=", 422, "D-02"),
]
CASOS_SUM = [(_c(i, "RF-05", "CE", n, f"GET /audits/summary-over-time?{q}", f"HTTP {st}", "Alta", d, desc="GET com a query indicada."), q, st) for i, n, q, st, d in _SUM]


@pytest.mark.asyncio
@pytest.mark.parametrize("caso,query,status", [param(*t) for t in CASOS_SUM])
async def test_resumo_no_tempo(monkeypatch, caso, query, status):
    async with _cliente(monkeypatch) as c:
        r = await c.get(f"/audits/summary-over-time?{query}", headers=H)

    assert r.status_code == status


# ============================ RF-06: PUT /config ==============================
_OK = {"broker_url": "http://orion:1026", "fiware_service": "openiot", "fiware_service_path": "/"}
_CFG = [  # (id, nome, campo, valor, status, tecnica)
    ("CT-CFG-01", "Configuração válida", "broker_url", "http://orion:1026", 200, "CE"),
    ("CT-CFG-02", "broker_url https com porta", "broker_url", "https://orion.exemplo.com:1026", 200, "CE"),
    ("CT-CFG-03", "broker_url com esquema ftp", "broker_url", "ftp://orion", 422, "CE"),
    ("CT-CFG-04", "broker_url sem esquema", "broker_url", "orion:1026", 422, "CE"),
    ("CT-CFG-05", "broker_url com espaço", "broker_url", "http://or ion", 422, "CE"),
    ("CT-CFG-06", "broker_url só com esquema", "broker_url", "http://", 422, "CE"),
    ("CT-CFG-07", "fiware_service vazio (0): limite inferior", "fiware_service", "", 200, "AVL"),
    ("CT-CFG-08", "fiware_service com 1 caractere", "fiware_service", "a", 200, "AVL"),
    ("CT-CFG-09", "fiware_service com 50 caracteres: limite superior", "fiware_service", "a" * 50, 200, "AVL"),
    ("CT-CFG-10", "fiware_service com 51 caracteres: limite superior +", "fiware_service", "a" * 51, 422, "AVL"),
    ("CT-CFG-11", "fiware_service com hífen", "fiware_service", "open-iot", 422, "CE"),
    ("CT-CFG-12", "fiware_service com acento", "fiware_service", "ação", 422, "CE"),
    ("CT-CFG-13", "fiware_service com underscore e dígitos", "fiware_service", "tenant_01", 200, "CE"),
    ("CT-CFG-14", "service_path raiz '/'", "fiware_service_path", "/", 200, "CE"),
    ("CT-CFG-15", "service_path com 2 níveis", "fiware_service_path", "/a/b", 200, "CE"),
    ("CT-CFG-16", "service_path sem barra inicial", "fiware_service_path", "a", 422, "CE"),
    ("CT-CFG-17", "service_path terminando em '/'", "fiware_service_path", "/a/", 422, "CE"),
    ("CT-CFG-18", "service_path com '//'", "fiware_service_path", "//", 422, "CE"),
]
CASOS_CFG = [
    (_c(i, "RF-06", t, n, f"{campo}={v[:20]!r}", f"HTTP {st}", "Alta" if st == 200 and i.endswith("01") else "Média",
        desc="PUT /config com o corpo válido, trocando apenas o campo indicado."), campo, v, st)
    for i, n, campo, v, st, t in _CFG
]


@pytest.mark.asyncio
@pytest.mark.parametrize("caso,campo,valor,status", [param(*t) for t in CASOS_CFG])
async def test_configurar_broker(monkeypatch, caso, campo, valor, status):
    contas = _Accounts()
    async with _cliente(monkeypatch, accounts=contas) as c:
        r = await c.put("/config", json={**_OK, campo: valor}, headers=H)

    assert r.status_code == status
    assert len(contas.criadas) == (1 if status == 200 else 0)  # 422 nunca persiste


CASO_CFG_503 = _c("CT-CFG-19", "RF-06", "CE", "Sem chave de criptografia configurada", "accounts=None (sem BROKER_API_KEY_ENCRYPTION_KEYS)", "HTTP 503", "Alta")


@pytest.mark.asyncio
@pytest.mark.req("RF-06")
async def test_ct_cfg_19_sem_chave_de_criptografia_retorna_503(monkeypatch):
    async with _cliente(monkeypatch, accounts=None) as c:
        r = await c.put("/config", json=_OK, headers=H)

    assert r.status_code == 503


# ============================ RF-07: POST /auth/login (SaaS) ==================
_SAAS = Settings(_env_file=None, deployment_mode="saas", jwt_signing_key="k" * 32)
_PRE_LOGIN = "Modo SaaS; conta user@example.com cadastrada com senha 'senha-correta-123'."
_AUT = [  # (id, nome, corpo, status, tecnica)
    ("CT-AUT-01", "Credenciais corretas", {"login_email": "user@example.com", "password": "senha-correta-123"}, 200, "CE"),
    ("CT-AUT-02", "E-mail correto, senha errada", {"login_email": "user@example.com", "password": "errada"}, 401, "CE"),
    ("CT-AUT-03", "E-mail inexistente", {"login_email": "nao@existe.com", "password": "senha-correta-123"}, 401, "CE"),
    ("CT-AUT-04", "Senha vazia", {"login_email": "user@example.com", "password": ""}, 401, "AVL"),
    ("CT-AUT-05", "E-mail em maiúsculas (insensível a caixa)", {"login_email": "USER@Example.com", "password": "senha-correta-123"}, 200, "CE"),
    ("CT-AUT-06", "Campo password ausente", {"login_email": "user@example.com"}, 422, "CE"),
    ("CT-AUT-07", "Corpo vazio", {}, 422, "CE"),
]
CASOS_AUT = [
    (Caso(i, "RF-07", t, n, "POST /auth/login com o corpo indicado.", _PRE_LOGIN,
          str({k: ("***" if k == "password" else v) for k, v in b.items()}), f"HTTP {st}", "Alta"), b, st)
    for i, n, b, st, t in _AUT
]


@pytest.mark.asyncio
@pytest.mark.parametrize("caso,corpo,status", [param(*t) for t in CASOS_AUT])
async def test_login(monkeypatch, caso, corpo, status):
    async with _cliente(monkeypatch, settings=_SAAS, logins=_Logins()) as c:
        r = await c.post("/auth/login", json=corpo)

    assert r.status_code == status
    if status == 200:
        cookie = r.headers["set-cookie"].lower()
        assert "httponly" in cookie and "secure" in cookie and "samesite=strict" in cookie
    if status == 401:  # mesma mensagem para senha errada e usuario inexistente
        assert r.json()["detail"] == "Email ou senha invalidos."


CASOS = (
    [t[0] for t in CASOS_NL] + [t[0] for t in CASOS_NL_INV] + [t[0] for t in CASOS_AU]
    + [t[0] for t in CASOS_PG] + [t[0] for t in CASOS_SUM] + [t[0] for t in CASOS_CFG]
    + [CASO_CFG_503] + [t[0] for t in CASOS_AUT]
)
