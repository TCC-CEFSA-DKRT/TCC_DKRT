# ADR-0019: imagem do modo self-hosted (produtor instala na propria infra).
# Diferente do `Dockerfile` na raiz do repo (ADR-0017): aquele empacota um
# handler Lambda (`public.ecr.aws/lambda/python`, CMD aponta pra funcao,
# nunca serve HTTP direto) — serve so' o modo SaaS/producao. Este roda
# `uvicorn` normal, ligando numa porta, porque o self-hosted nao tem
# ALB/API Gateway na frente. Mesmo codigo/requirements.txt dos dois; so' a
# base image e o entrypoint final mudam. Vive em `selfhosted/` (nao na
# raiz) para nao se confundir com o Dockerfile de producao — ver
# `selfhosted/docker-compose.yml`, que usa `context: ..` para poder copiar
# `src/`/`requirements.txt`/`pyproject.toml` da raiz do repo a partir daqui.
FROM python:3.11-slim

WORKDIR /app

# Dependencias primeiro (cache de camada) -- so' muda quando requirements.txt
# muda, nao a cada alteracao de codigo em src/. ponytail: sem build-essential
# -- as dependencias do projeto (pydantic, asyncpg, etc.) tem wheel prebuilt
# pra linux/amd64 e linux/arm64; se algum ambiente exigir compilar do zero,
# adicionar build-essential aqui.
COPY requirements.txt pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir -e .

COPY alembic.ini ./
COPY migrations ./migrations
COPY knowledge ./knowledge

COPY selfhosted/fernet-keys.sh /usr/local/bin/fernet-keys.sh
ENTRYPOINT ["sh", "/usr/local/bin/fernet-keys.sh"]

EXPOSE 8000
CMD ["uvicorn", "auditor.interfaces.rest.app:app", "--host", "0.0.0.0", "--port", "8000"]
