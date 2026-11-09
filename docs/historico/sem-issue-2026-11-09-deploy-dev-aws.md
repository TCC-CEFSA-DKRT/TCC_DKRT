# Deploy do ambiente dev na AWS (primeira subida manual)

## 2026-11-09 — correções para o dev rodar na AWS (Kauê, com apoio de IA)

**Contexto:** primeira subida do ambiente `dev` (EC2 + RDS + SQS + S3) numa conta AWS nova, feita à mão seguindo `docs/devops/pipeline-e-ambientes.md`. Cada passo manual revelou um problema que o pipeline `deploy-dev` encontraria do mesmo jeito.

**O que mudou:**
- `infra/terraform/modules/compute/user_data/api.sh.tftpl`: `DATABASE_URL` usa `ssl=require`; `AWS_DEFAULT_REGION` entra no `static.env`; o `migrate` do `auditor-deploy` monta `/opt/auditor/secrets`.
- `src/auditor/infrastructure/config/secrets_bootstrap.py::load_database_url_from_rds_managed_secret`: parâmetro `sslmode` virou `ssl` e a URL sai com `?ssl=`.
- `infra/terraform/modules/database/outputs.tf`: exemplo de URL com `ssl=require`.
- `infra/terraform/modules/compute/main.tf` e `variables.tf`: disco raiz da API de 30 GB (`api_root_volume_size`), preservando as tags do volume.
- `infra/terraform/environments/dev/variables.tf`: `api_instance_type` padrão `t3.medium`.
- `infra/terraform/modules/frontend_static_site/main.tf`: bucket do site inclui o ID da conta (`<prefix>-frontend-<account>`).
- `infra/terraform/modules/network/main.tf`: descrição de security group só com ASCII.
- `.github/workflows/deploy-dev.yml` e `infra/terraform/bootstrap/main.tf`: o nome novo do bucket do frontend.
- `infra/terraform/bootstrap/main.tf`: tabela de lock chama `auditor-tf-lock`, o nome criado por `homolog/scripts/bootstrap_backend.sh`.
- `infra/orion-test/`: `setup.sh` e `seed.py` sobem um Orion + Mongo de teste na EC2 e carregam 6 entidades (3 cenários DKRT x 2 modelos).

**Por quê / decisões:**
- Orion de teste na própria EC2, publicado só em `172.17.0.1:1026` (IP do docker0): a API alcança, a internet não. O pacote `docker.io` do Ubuntu 22.04 não traz o plugin compose, por isso `docker run` em vez de `docker-compose`.
- `t3.medium` em vez de `t3.small`: API + Orion + Mongo juntos ficam apertados em 2 GB.
- Alternativa descartada: editar só o `runtime.env` na EC2. O `auditor-deploy` o reescreve a cada execução, então a correção tinha de ir para o script.

**Armadilhas e pontos de atenção:**
- `asyncpg` não aceita `sslmode` (parâmetro do psycopg2): `TypeError: connect() got an unexpected keyword argument 'sslmode'`. O equivalente é `ssl=require`. Vale também para o caminho Lambda (`secrets_bootstrap.py`).
- O boto3 não lê `AWS_REGION`, só `AWS_DEFAULT_REGION`: sem ela a API cai ao iniciar (`NoRegionError` em `container.py::get_job_queue`).
- A AMI Ubuntu traz disco de 8 GB; a imagem (torch, sentence-transformers) tem camada de 3,2 GB comprimida e não cabe no pull.
- `selfhosted/fernet-keys.sh` com final de linha CRLF (checkout no Windows) quebra o entrypoint: `set: Illegal option -`. O Git guarda LF (`.gitattributes`); o problema é a cópia local. Convém `git config core.autocrlf false`.
- A imagem do Orion já liga `-multiservice` no entrypoint; repetir a opção faz o Orion recusar o comando.
- Nomes de bucket S3 são globais; descrição de security group só aceita ASCII.
- Mudar o `user_data` de uma EC2 existente não o reexecuta: as correções foram aplicadas também por dentro da máquina.
- O frontend chama `GET /session` na API ao abrir; redes que bloqueiam a porta 8000 deixam a tela em branco. O `appGuard` (`frontend/src/app/core/app.guard.ts`) abre o painel mesmo se a chamada falhar.
- O site em S3 devolve 404 (com o `index.html`) em rotas internas abertas direto, como `/dashboard`.
- Com o RDS parado, a API responde 500 em `/session` após 1 minuto (`TimeoutError` do asyncpg).
- A tela Auditorias só lista; a criação passa pelo Assistente, que depende do Ollama. Sem Ollama, a auditoria foi disparada por `POST /audits` direto na API.

**Pendências:**
- Ollama (cota de GPU `L-DB2E81BA` está em 0; alternativa: CPU em `t3.xlarge`).
- HTTPS e porta liberada em redes restritas (CloudFront na frente da API e do site).
- Restringir o acesso à API (porta 8000 aberta para `0.0.0.0/0`).
- Bootstrap OIDC, variáveis do GitHub e primeiro `deploy-dev` pelo pipeline.
