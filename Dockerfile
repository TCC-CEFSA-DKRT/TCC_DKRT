# ADR-0017: imagem de conteiner unica para os tres Lambdas de producao
# (API, Worker, Worker-DLQ) — `modules/lambda_compute` (Terraform) aponta os
# tres `aws_lambda_function` para a MESMA imagem no ECR, trocando so' o
# `image_config.command` de cada um (ver `environments/production`). Ver
# tambem `docs/design/implantacao-aws.html`, card "Compute".
#
# Por que imagem de conteiner em vez do pacote .zip nativo do Lambda: o
# Nivel 2 (Fase 7) carrega `sentence-transformers`/`torch` em tempo de
# execucao (`infrastructure/rag/embedder.py`, `SentenceTransformersEmbedder`,
# usado por `PgVectorRetriever.retrieve()` a cada chamada de
# `RunAuditUseCase._build_report()`) — essas duas dependencias sozinhas
# excedem o limite de 250 MB (descomprimido) de um pacote .zip de Lambda.
# Imagem de conteiner sobe esse limite para 10 GB, unico jeito viavel de
# levar o MESMO codigo/dependencias da API/Worker para o Lambda sem trocar
# o embedder por um servico gerenciado (decisao explicita do usuario:
# manter fidelidade ao diagrama e a arquitetura ja' testada nas Fases 6/7,
# nao migrar para embeddings gerenciados so' por causa do empacotamento).
FROM public.ecr.aws/lambda/python:3.11

# Dependencias primeiro (cache de camada Docker) -- so' muda quando
# requirements.txt muda, nao a cada alteracao de codigo em src/.
COPY requirements.txt ${LAMBDA_TASK_ROOT}/requirements.txt
# --only-binary: a base do Lambda (Python 3.11) é Amazon Linux 2 (glibc 2.26) e não tem
# compilador; sem isso o pip pega o código-fonte do numpy mais novo (sem wheel
# compatível) e falha. Com ele, recua para a última versão com wheel compatível.
RUN pip install --no-cache-dir --only-binary=:all: -r ${LAMBDA_TASK_ROOT}/requirements.txt && \
    rm ${LAMBDA_TASK_ROOT}/requirements.txt

# Codigo da aplicacao -- copiado por dentro de src/ (nao src/ inteiro) para
# que `auditor` fique diretamente em ${LAMBDA_TASK_ROOT}, importavel como
# `auditor.interfaces.aws_lambda.api_handler.handler` (o "module.function"
# que o runtime base do Lambda para Python resolve por padrao).
COPY src/auditor ${LAMBDA_TASK_ROOT}/auditor
COPY alembic.ini ${LAMBDA_TASK_ROOT}/alembic.ini
COPY migrations ${LAMBDA_TASK_ROOT}/migrations

# Default: handler da API (Mangum). O Worker e o Worker-DLQ (mesma imagem)
# sobrescrevem isto via `image_config.command` no `aws_lambda_function`
# correspondente (`modules/lambda_compute`) -- nao precisam de outra
# imagem, so' de outro entrypoint dentro da mesma.
CMD ["auditor.interfaces.aws_lambda.api_handler.handler"]
