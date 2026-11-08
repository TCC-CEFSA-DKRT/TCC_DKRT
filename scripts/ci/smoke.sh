#!/usr/bin/env bash
# Teste de fumaça: a API responde /health/ready (conecta no banco) e, se
# informado, o frontend responde 200. Tenta por até ~5 minutos, porque após um
# deploy o Lambda/contêiner pode levar um tempo para aquecer.
# Uso: smoke.sh <url-da-api> [url-do-frontend]
set -euo pipefail

API_URL="${1:?Uso: smoke.sh <url-da-api> [url-do-frontend]}"
API_URL="${API_URL%/}"
FRONTEND_URL="${2:-}"

check() {
  local url="$1" attempt
  for attempt in $(seq 1 30); do
    if curl -fsS --max-time 20 -o /dev/null "$url"; then
      echo "OK  $url"
      return 0
    fi
    echo "aguardando $url (tentativa $attempt/30)"
    sleep 10
  done
  echo "FALHOU $url" >&2
  return 1
}

check "$API_URL/health/live"
check "$API_URL/health/ready"
[ -z "$FRONTEND_URL" ] || check "$FRONTEND_URL/"
