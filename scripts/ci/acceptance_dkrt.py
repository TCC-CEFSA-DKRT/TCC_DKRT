#!/usr/bin/env python3
"""Aceitação da homologação: os 3 cenários DKRT (um conforme, um com erro
heurístico, um com erro semântico), o mesmo conjunto de entidades que o
conector do dataspace-demo grava com POST /seed-dkrt (modelo Streetlight).

O script grava as 3 entidades no Orion, dispara uma auditoria pela API do
ambiente, espera terminar e confere:
  - cenário 1 (correto): status "conformant";
  - cenário 2 (erro heurístico) e cenário 3 (erro semântico): status diferente
    de "conformant". O alvo é que o auditor os acuse, não um status específico.

Variáveis de ambiente:
  API_URL                URL da API do ambiente (obrigatória)
  ORION_URL              URL do Orion que o ambiente audita (obrigatória)
  FIWARE_SERVICE         tenant (header Fiware-Service), opcional
  FIWARE_SERVICE_PATH    caminho do tenant, opcional (padrão "/")
  ACCEPTANCE_EMAIL / ACCEPTANCE_PASSWORD  login, só no modo SaaS
  ACCEPTANCE_TIMEOUT     segundos de espera pela auditoria (padrão 900)

Só usa a biblioteca padrão, para rodar no runner sem instalar dependências.
"""

from __future__ import annotations

import http.cookiejar
import json
import os
import sys
import time
import urllib.error
import urllib.request

API_URL = os.environ["API_URL"].rstrip("/")
ORION_URL = os.environ["ORION_URL"].rstrip("/")
SERVICE = os.environ.get("FIWARE_SERVICE", "")
SERVICE_PATH = os.environ.get("FIWARE_SERVICE_PATH", "/")
TIMEOUT = int(os.environ.get("ACCEPTANCE_TIMEOUT", "900"))

BASE = {
    "type": "Streetlight",
    "domain": {"value": "Iluminacao Publica", "type": "Text"},
    "location": {"value": {"type": "Point", "coordinates": [-46.6333, -23.5505]}, "type": "geo:json"},
    "status": {"value": "ok", "type": "Text"},
}

SCENARIOS = {
    1: {
        "powerState": {"value": "on", "type": "Text"},
        "powerConsumption": {"value": 120.5, "type": "Number"},
        "illuminanceLevel": {"value": 50.0, "type": "Number"},
        "lanternHeight": {"value": 8.5, "type": "Number"},
        "circuitId": {"value": "C-34", "type": "Text"},
    },
    # Lâmpada desligada consumindo 450 W, e poste com altura negativa.
    2: {
        "powerState": {"value": "off", "type": "Text"},
        "powerConsumption": {"value": 450.0, "type": "Number"},
        "illuminanceLevel": {"value": 0.0, "type": "Number"},
        "lanternHeight": {"value": -2.0, "type": "Number"},
        "circuitId": {"value": "C-34", "type": "Text"},
    },
    # Nomes de campo traduzidos: JSON válido, mas fora do modelo oficial.
    3: {
        "estadoEnergia": {"value": "on", "type": "Text"},
        "consumoEletrico": {"value": 120.5, "type": "Number"},
        "nivelIluminacao": {"value": 50.0, "type": "Number"},
        "alturaPoste": {"value": 8.5, "type": "Number"},
        "circuito": {"value": "C-34", "type": "Text"},
    },
}

_cookies = http.cookiejar.CookieJar()
_opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(_cookies))


def call(method: str, url: str, body: dict | None = None, headers: dict | None = None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    for key, value in (headers or {}).items():
        req.add_header(key, value)
    try:
        with _opener.open(req, timeout=60) as resp:
            raw = resp.read()
            return resp.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode(errors="replace")


def orion_headers() -> dict:
    headers = {}
    if SERVICE:
        headers["Fiware-Service"] = SERVICE
        headers["Fiware-ServicePath"] = SERVICE_PATH
    return headers


def seed() -> dict[int, str]:
    ids = {}
    for number, fields in SCENARIOS.items():
        entity = {"id": f"urn:ngsi-ld:Streetlight:dkrt-test-00{number}", **BASE, **fields}
        ids[number] = entity["id"]
        # Recria a entidade para o teste ser repetível (422 = já existe).
        call("DELETE", f"{ORION_URL}/v2/entities/{entity['id']}", headers=orion_headers())
        status, body = call("POST", f"{ORION_URL}/v2/entities", entity, orion_headers())
        if status not in (201, 204):
            sys.exit(f"Orion recusou o cenário {number}: {status} {body}")
    return ids


def login() -> None:
    email, password = os.environ.get("ACCEPTANCE_EMAIL"), os.environ.get("ACCEPTANCE_PASSWORD")
    if not email:
        return
    status, body = call("POST", f"{API_URL}/auth/login", {"email": email, "password": password})
    if status != 200:
        sys.exit(f"Login falhou: {status} {body}")


def main() -> int:
    ids = seed()
    login()

    status, body = call("POST", f"{API_URL}/audits", {"entity_type": "Streetlight"})
    if status != 202:
        sys.exit(f"POST /audits retornou {status}: {body}")
    run_id = body["run_id"]
    print(f"Auditoria {run_id} iniciada")

    deadline = time.time() + TIMEOUT
    run = None
    while time.time() < deadline:
        status, run = call("GET", f"{API_URL}/audits/{run_id}")
        if status == 200 and run["status"] in ("completed", "failed", "partial", "no_entities_found"):
            break
        time.sleep(10)
    else:
        sys.exit(f"A auditoria não terminou em {TIMEOUT}s")

    if run["status"] != "completed":
        sys.exit(f"Auditoria terminou com status {run['status']}")

    by_id = {report["entity_id"]: report["status"] for report in run["reports"]}
    failures = []
    for number, entity_id in ids.items():
        got = by_id.get(entity_id)
        ok = got == "conformant" if number == 1 else got not in (None, "conformant")
        print(f"cenário {number}: {entity_id} -> {got} {'OK' if ok else 'FALHOU'}")
        if not ok:
            failures.append(number)

    if failures:
        print(f"Cenários reprovados: {failures}", file=sys.stderr)
        return 1
    print("3 cenários DKRT classificados como esperado")
    return 0


if __name__ == "__main__":
    sys.exit(main())
