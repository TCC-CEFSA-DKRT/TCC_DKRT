# ADR-0019: frontend do self-hosted -- build estatico do Angular (Fase 8)
# servido por nginx. Nao existe um Dockerfile do frontend em lugar nenhum
# do repo ainda (producao usa CloudFront+S3, `infra/terraform/modules/
# frontend_delivery` -- upload do build estatico, nao um container). Este e'
# so' para o self-hosted, onde nao ha' CDN/bucket, so' Docker.
#
# `API_CONFIG.baseUrl` (frontend/src/app/core/api-config.ts) e' fixo em
# tempo de build (`http://localhost:8000`) -- correto aqui: self-hosted e'
# sempre um produtor, um broker, um build; o produtor abre a UI na mesma
# maquina/rede onde a API esta' exposta (porta 8000 do compose), sem
# precisar de tela de login/selecao de tenant (essa tela nao existe hoje em
# nenhum modo -- ver ADR-0019, secao sobre a lacuna de entrada de dados do
# broker).
FROM node:20-slim AS build
WORKDIR /app
COPY frontend/package*.json ./
RUN npm ci
COPY frontend .
RUN npm run build -- --configuration production

FROM nginx:alpine
COPY --from=build /app/dist/frontend/browser /usr/share/nginx/html
# SPA: qualquer rota desconhecida cai em index.html (Angular Router decide
# client-side) -- sem isto, um refresh em /audit-runs/xyz devolveria 404 do
# nginx em vez da tela certa.
RUN printf 'server { listen 80; root /usr/share/nginx/html; location / { try_files $uri $uri/ /index.html; } }' > /etc/nginx/conf.d/default.conf
