# NGSI-v2 — Orion Context Broker

## Query entities

Listar entidades no Orion Context Broker (FIWARE):

```http
GET /v2/entities?type=Sensor&limit=20 HTTP/1.1
Host: localhost:1026
Fiware-Service: openiot
Fiware-ServicePath: /
Accept: application/json
```

Resposta: array JSON de entidades com `id`, `type` e atributos.

## Get entity

```http
GET /v2/entities/Sensor:001 HTTP/1.1
Host: localhost:1026
Fiware-Service: openiot
```

## Create entity

```http
POST /v2/entities HTTP/1.1
Content-Type: application/json

{
  "id": "Sensor:001",
  "type": "Sensor",
  "temperature": { "type": "Float", "value": 22.5 }
}
```

## Update attributes

```http
PATCH /v2/entities/Sensor:001/attrs HTTP/1.1
Content-Type: application/json

{
  "temperature": { "type": "Float", "value": 24.0 }
}
```

## Subscriptions

```http
POST /v2/subscriptions HTTP/1.1
Content-Type: application/json

{
  "description": "Temperatura alta",
  "subject": { "entities": [{ "idPattern": ".*", "type": "Sensor" }] },
  "notification": { "http": { "url": "http://localhost:5050/notify" } }
}
```
