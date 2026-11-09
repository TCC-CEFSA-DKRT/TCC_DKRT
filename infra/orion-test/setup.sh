#!/bin/bash
# Orion + Mongo de teste na EC2 do ambiente dev (sem docker-compose: o pacote docker.io
# do Ubuntu 22.04 nao traz o plugin). O Orion so' escuta no IP do docker0 (172.17.0.1):
# fica acessivel para o contêiner da API (rede bridge padrao) e para o proprio host,
# nunca para a internet. A imagem do Orion ja liga o multi-servico (-multiservice) no
# entrypoint: repetir a opcao faz o Orion recusar o comando. Uso (na EC2, como root): bash setup.sh
set -euo pipefail

docker network inspect orion-net > /dev/null 2>&1 || docker network create orion-net
docker volume create orion-mongo-data > /dev/null
docker rm -f orion orion-mongo > /dev/null 2>&1 || true

docker run -d --name orion-mongo --network orion-net --restart unless-stopped \
  -v orion-mongo-data:/data/db mongo:4.4 --nojournal

for _ in $(seq 1 30); do
  docker exec orion-mongo mongo --quiet --eval "db.adminCommand('ping').ok" 2> /dev/null | grep -q 1 && break
  sleep 2
done

docker run -d --name orion --network orion-net --restart unless-stopped \
  -p 172.17.0.1:1026:1026 \
  fiware/orion:3.10.1 -dbhost orion-mongo -logLevel INFO

for _ in $(seq 1 30); do
  if curl -fsS http://172.17.0.1:1026/version > /dev/null 2>&1; then
    echo "Orion pronto em http://172.17.0.1:1026"
    curl -s http://172.17.0.1:1026/version
    exit 0
  fi
  sleep 2
done
docker logs --tail 40 orion
echo "Orion nao respondeu em /version" >&2
exit 1
