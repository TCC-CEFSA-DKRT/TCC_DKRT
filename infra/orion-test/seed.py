"""Carrega no Orion de teste os 3 cenarios DKRT para os 2 modelos da demo
(mesmos valores de dataspace-demo/connector/app.py, em versao deterministica):
  normal    - 100% conforme o Smart Data Model
  heuristic - valores fisicamente impossiveis (Nivel 1 / estrutural)
  semantic  - nomes de campo em portugues em vez das chaves oficiais (Nivel 2 / SLM)
Uso: python3 seed.py [url-do-orion]   (padrao: http://172.17.0.1:1026)
Sem Fiware-Service: as entidades ficam no servico padrao, caminho "/"."""
import json
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

BROKER = (sys.argv[1] if len(sys.argv) > 1 else "http://172.17.0.1:1026").rstrip("/")
NOW = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def num(v):
    return {"value": v, "type": "Number"}


def text(v):
    return {"value": v, "type": "Text"}


def base(kind, scenario, **extra):
    entity = {
        "id": f"urn:ngsi-ld:{kind}:dkrt-{scenario}",
        "type": kind,
        "domain": text("Teste DKRT"),
        "location": {"value": {"type": "Point", "coordinates": [-46.6333, -23.5505]}, "type": "geo:json"},
    }
    entity.update(extra)
    return entity


ENTITIES = [
    base("WeatherObserved", "normal", temperature=num(24.5), relativeHumidity=num(62.0),
         windSpeed=num(7.2), atmosphericPressure=num(1012.0),
         dateObserved={"value": NOW, "type": "DateTime"}),
    base("WeatherObserved", "heuristic", temperature=num(24.5), relativeHumidity=num(215.0),
         windSpeed=num(-23.0), atmosphericPressure=num(1012.0),
         dateObserved={"value": NOW, "type": "DateTime"}),
    base("WeatherObserved", "semantic", temperatura=num(24.5), umidadeRelativa=num(62.0),
         velocidadeVento=num(7.2), pressaoAtmosferica=num(1012.0)),
    base("Streetlight", "normal", status=text("ok"), powerState=text("on"),
         powerConsumption=num(96.0), illuminanceLevel=num(55.0), lanternHeight=num(8.5),
         circuitId=text("C-34")),
    base("Streetlight", "heuristic", status=text("ok"), powerState=text("off"),
         powerConsumption=num(640.0), illuminanceLevel=num(0.0), lanternHeight=num(-5.0),
         circuitId=text("C-34")),
    base("Streetlight", "semantic", status=text("ok"), estadoEnergia=text("on"),
         consumoEletrico=num(96.0), nivelIluminacao=num(55.0), alturaPoste=num(8.5),
         circuito=text("C-34")),
]

for entity in ENTITIES:
    req = urllib.request.Request(
        f"{BROKER}/v2/entities",
        data=json.dumps(entity).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            print(f"{resp.status} criada   {entity['id']}")
    except urllib.error.HTTPError as err:
        if err.code == 422:
            print(f"422 ja existe {entity['id']}")
        else:
            print(f"{err.code} ERRO    {entity['id']}: {err.read().decode()[:200]}")
            sys.exit(1)
