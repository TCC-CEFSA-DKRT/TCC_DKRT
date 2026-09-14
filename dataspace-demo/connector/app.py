"""
Conector didático de data space.

Este serviço simula, de forma simplificada, o papel de um conector de data space
(o FDC / TRUE Connector da FIWARE) na frente de um broker Orion. Não implementa o
protocolo IDS/Dataspace Protocol real -- é uma redução pedagógica feita para deixar
visíveis os 5 conceitos centrais: catálogo, negociação, transferência, recebimento
e aplicação da política de uso (soberania).

O mesmo código roda em 3 papéis diferentes, configurados via variável de ambiente ROLE:
  - producer: expõe /seed, /assets, /catalog, /negotiate, /transfer, /agreements
  - consumer: expõe /receive, /use, /received

O catálogo é dinâmico: cada produtor já nasce com o asset configurado via variável de
ambiente, e novos assets podem ser publicados em tempo de execução via POST /assets
(ex.: depois de criar uma entidade nova direto no Orion).

A "confiança" entre conectores é simulada com um token compartilhado (SHARED_TOKEN),
no lugar de mTLS + DAPS/Gaia-X Clearing House que seriam usados em produção.
"""

import os
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

ROLE = os.getenv("ROLE", "producer")
CONNECTOR_ID = os.getenv("CONNECTOR_ID", "connector-a")
SHARED_TOKEN = os.getenv("SHARED_TOKEN", "dataspace-demo-trust-2026")

DOMAIN_LABEL = os.getenv("DOMAIN_LABEL", "Qualidade do ar")
ORION_URL = os.getenv("ORION_URL", "http://orion-a:1026")
ENTITY_TYPE = os.getenv("ENTITY_TYPE", "AirQualityObserved")
ENTITY_ID = os.getenv("ENTITY_ID", "urn:ngsi-ld:AirQualityObserved:demo-001")
POLICY_PURPOSE = os.getenv("POLICY_PURPOSE", "visualizacao-academica")
POLICY_TTL_MINUTES = int(os.getenv("POLICY_TTL_MINUTES", "5"))
POLICY_ALLOW_REDISTRIBUTION = os.getenv("POLICY_ALLOW_REDISTRIBUTION", "false").lower() == "true"

app = FastAPI(title=f"Conector de data space ({ROLE}) - {CONNECTOR_ID}")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["Authorization", "Content-Type"],
)

AGREEMENTS: dict = {}
RECEIVED: dict = {}
ASSETS: dict = {}


def _default_asset() -> dict:
    return {
        "assetId": ENTITY_TYPE,
        "connectorId": CONNECTOR_ID,
        "domain": DOMAIN_LABEL,
        "description": f"Dados de {DOMAIN_LABEL} publicados por {CONNECTOR_ID}",
        "entityType": ENTITY_TYPE,
        "entityId": ENTITY_ID,
        "policy": {
            "purpose": POLICY_PURPOSE,
            "ttlMinutes": POLICY_TTL_MINUTES,
            "allowRedistribution": POLICY_ALLOW_REDISTRIBUTION,
        },
    }


if ROLE == "producer":
    # o asset configurado via variaveis de ambiente sempre comeca disponivel no catalogo;
    # novos assets podem ser registrados depois via POST /assets
    ASSETS[ENTITY_TYPE] = _default_asset()


def check_token(authorization: Optional[str]):
    if authorization != f"Bearer {SHARED_TOKEN}":
        raise HTTPException(
            status_code=401,
            detail="conector não confiável: token de confiança ausente ou inválido",
        )


def now() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.isoformat()


def ngsi_date(dt: datetime) -> str:
    """Formato estrito que o NGSI-v2 exige para atributos DateTime: milissegundos + 'Z',
    nunca microssegundos nem offset '+00:00' (formato que o Orion rejeita)."""
    return dt.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def require_role(expected: str, endpoint: str):
    if ROLE != expected:
        raise HTTPException(
            status_code=400,
            detail=f"este conector está no papel '{ROLE}'; {endpoint} só existe em conectores '{expected}'",
        )


@app.get("/health")
def health():
    return {"status": "ok", "role": ROLE, "connectorId": CONNECTOR_ID}


# ---------------------------------------------------------------------------
# Lado produtor
# ---------------------------------------------------------------------------

def orion_request(method: str, url: str, **kwargs):
    """Chama o Orion tolerando falhas transitorias (DNS interno do Docker, broker
    ainda subindo etc). Tenta algumas vezes com pequena espera antes de desistir."""
    last_exc = None
    for attempt in range(5):
        try:
            with httpx.Client(timeout=10.0) as client:
                return client.request(method, url, **kwargs)
        except httpx.TransportError as exc:
            last_exc = exc
            time.sleep(1.5)
    raise HTTPException(
        status_code=502,
        detail=f"orion inacessivel apos varias tentativas: {last_exc}",
    )


@app.post("/seed-dkrt")
def seed_dkrt(scenario: int, authorization: Optional[str] = Header(None)):
    check_token(authorization)
    require_role("producer", "/seed-dkrt")
    
    # Base da entidade (comum a todos os cenários)
    entity = {
        "id": f"urn:ngsi-ld:AirQualityObserved:dkrt-test-00{scenario}",
        "type": "AirQualityObserved",
        "domain": {"value": DOMAIN_LABEL, "type": "Text"}
    }
    
    if scenario == 1:
        # Cenário 1: 100% aderente ao Smart Data Model
        entity["NO2"] = {"value": 42.5, "type": "Number"}
        entity["dateObserved"] = {"value": ngsi_date(now()), "type": "DateTime"}
        
    elif scenario == 2:
        # Cenário 2: Erro Heurístico (Física impossível e tipagem fraca)
        # O validador Nível 1 pode deixar passar (se não checar tipos estritos), mas a heurística/SLM pega.
        entity["NO2"] = {"value": "-999.99", "type": "Text"} 
        entity["dateObserved"] = {"value": ngsi_date(now()), "type": "DateTime"}
        
    elif scenario == 3:
        # Cenário 3: Erro Semântico (Quebra de contrato do modelo)
        # Omissão da data obrigatória e atributo traduzido fora do padrão NGSI-v2
        entity["dioxidoNitrogenio"] = {"value": 45.0, "type": "Number"} 
        
    else:
        raise HTTPException(status_code=400, detail="Use scenario 1, 2 ou 3")

    r = orion_request("POST", f"{ORION_URL}/v2/entities", json=entity)
    if r.status_code not in (201, 422):
        raise HTTPException(status_code=502, detail=f"Erro no Orion: {r.status_code} {r.text}")
        
    return {"status": "Seed DKRT aplicado", "cenario": scenario, "entityId": entity["id"]}

class RegisterAssetRequest(BaseModel):
    assetId: str
    entityType: str
    entityId: str
    description: Optional[str] = None
    purpose: str = "visualizacao-academica"
    ttlMinutes: int = 5
    allowRedistribution: bool = False


@app.post("/assets")
def register_asset(body: RegisterAssetRequest, authorization: Optional[str] = Header(None)):
    check_token(authorization)
    require_role("producer", "/assets")
    asset = {
        "assetId": body.assetId,
        "connectorId": CONNECTOR_ID,
        "domain": DOMAIN_LABEL,
        "description": body.description or f"Dados publicados por {CONNECTOR_ID}",
        "entityType": body.entityType,
        "entityId": body.entityId,
        "policy": {
            "purpose": body.purpose,
            "ttlMinutes": body.ttlMinutes,
            "allowRedistribution": body.allowRedistribution,
        },
    }
    ASSETS[body.assetId] = asset
    return asset


@app.get("/catalog")
def catalog(authorization: Optional[str] = Header(None)):
    check_token(authorization)
    require_role("producer", "/catalog")
    return list(ASSETS.values())


class NegotiateRequest(BaseModel):
    assetId: str
    consumerId: str


@app.post("/negotiate")
def negotiate(body: NegotiateRequest, authorization: Optional[str] = Header(None)):
    check_token(authorization)
    require_role("producer", "/negotiate")
    asset = ASSETS.get(body.assetId)
    if not asset:
        raise HTTPException(status_code=404, detail="assetId não encontrado no catálogo deste conector")

    issued = now()
    expires = issued + timedelta(minutes=asset["policy"]["ttlMinutes"])
    agreement_id = str(uuid.uuid4())
    agreement = {
        "agreementId": agreement_id,
        "assetId": body.assetId,
        "producerId": CONNECTOR_ID,
        "consumerId": body.consumerId,
        "entityType": asset["entityType"],
        "entityId": asset["entityId"],
        "policy": {
            "purpose": asset["policy"]["purpose"],
            "allowRedistribution": asset["policy"]["allowRedistribution"],
            "expiresAt": iso(expires),
        },
        "issuedAt": iso(issued),
    }
    AGREEMENTS[agreement_id] = agreement
    return agreement


class TransferRequest(BaseModel):
    agreementId: str


@app.post("/transfer")
def transfer(body: TransferRequest, authorization: Optional[str] = Header(None)):
    check_token(authorization)
    require_role("producer", "/transfer")
    agreement = AGREEMENTS.get(body.agreementId)
    if not agreement:
        raise HTTPException(status_code=404, detail="acordo não encontrado; negocie antes de transferir")
    if now() > datetime.fromisoformat(agreement["policy"]["expiresAt"]):
        raise HTTPException(status_code=403, detail="transferência bloqueada: acordo expirado")

    r = orion_request("GET", f"{ORION_URL}/v2/entities/{agreement['entityId']}")
    if r.status_code != 200:
        raise HTTPException(status_code=502, detail=f"orion não retornou a entidade: {r.status_code}")

    return {"agreement": agreement, "data": r.json()}


@app.get("/agreements")
def list_agreements(authorization: Optional[str] = Header(None)):
    check_token(authorization)
    require_role("producer", "/agreements")
    return list(AGREEMENTS.values())


# ---------------------------------------------------------------------------
# Lado consumidor
# ---------------------------------------------------------------------------

class ReceiveRequest(BaseModel):
    agreementId: str
    assetId: str
    producerId: str
    policy: dict
    data: dict


@app.post("/receive")
def receive(body: ReceiveRequest, authorization: Optional[str] = Header(None)):
    check_token(authorization)
    require_role("consumer", "/receive")
    record = {
        "agreementId": body.agreementId,
        "assetId": body.assetId,
        "producerId": body.producerId,
        "policy": body.policy,
        "data": body.data,
        "receivedAt": iso(now()),
        "usageCount": 0,
    }
    RECEIVED[body.assetId] = record
    return record


class UseRequest(BaseModel):
    assetId: str
    action: str  # "visualizar" | "redistribuir"


@app.post("/use")
def use(body: UseRequest, authorization: Optional[str] = Header(None)):
    check_token(authorization)
    require_role("consumer", "/use")
    record = RECEIVED.get(body.assetId)
    if not record:
        raise HTTPException(status_code=404, detail="nenhum dado recebido para este assetId; chame /receive antes")

    expires_at = datetime.fromisoformat(record["policy"]["expiresAt"])
    if now() > expires_at:
        raise HTTPException(status_code=403, detail="uso bloqueado pela política do data space: acordo expirado")

    if body.action == "redistribuir" and not record["policy"].get("allowRedistribution", False):
        raise HTTPException(
            status_code=403,
            detail="uso bloqueado pela política do data space: redistribuição não permitida",
        )

    record["usageCount"] += 1
    return {
        "status": "uso permitido",
        "assetId": body.assetId,
        "action": body.action,
        "usageCount": record["usageCount"],
    }


@app.get("/received")
def list_received(authorization: Optional[str] = Header(None)):
    check_token(authorization)
    require_role("consumer", "/received")
    return list(RECEIVED.values())
