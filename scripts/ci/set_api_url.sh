#!/usr/bin/env bash
# O frontend fixa a URL da API em tempo de build (frontend/src/app/core/
# api-config.ts: DEFAULT_API_CONFIG.baseUrl = http://localhost:8000). Para
# construir uma vez e promover o mesmo build entre ambientes, a URL real é
# trocada no momento do deploy, no build pronto. Falha se o valor padrão não
# for encontrado (a premissa deixou de valer) ou se sobrar alguma ocorrência.
# Uso: set_api_url.sh <diretório-do-build> <url-da-api>
set -euo pipefail

DIST="${1:?Uso: set_api_url.sh <diretório-do-build> <url-da-api>}"
API_URL="${2:?Uso: set_api_url.sh <diretório-do-build> <url-da-api>}"
API_URL="${API_URL%/}"
PLACEHOLDER="http://localhost:8000"

FILES="$(grep -rl --include='*.js' -F "$PLACEHOLDER" "$DIST" || true)"
if [ -z "$FILES" ]; then
  echo "Nenhuma ocorrência de $PLACEHOLDER em $DIST; revise scripts/ci/set_api_url.sh" >&2
  exit 1
fi

# O delimitador | não aparece em URLs; & é escapado para não virar a referência do sed.
ESCAPED="$(printf '%s' "$API_URL" | sed 's/[&|\\]/\\&/g')"
echo "$FILES" | xargs sed -i "s|$PLACEHOLDER|$ESCAPED|g"

if grep -rq --include='*.js' -F "$PLACEHOLDER" "$DIST"; then
  echo "Ainda há ocorrências de $PLACEHOLDER após a troca" >&2
  exit 1
fi
echo "URL da API ajustada para $API_URL em $(echo "$FILES" | wc -l) arquivo(s)"
