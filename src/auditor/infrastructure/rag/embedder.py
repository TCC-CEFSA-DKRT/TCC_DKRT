"""Embedder — ver .cursor/specs/fase6.spec.md, secao 4.

Vive em infrastructure/rag/, nunca em domain/ports/ (plano geral, secao
2.2): so' KnowledgeRetrieverPort e' visivel para a Aplicacao; embutir texto
e' detalhe de implementacao do PgVectorRetriever e da ingestao, nunca algo
que a Fase 7 chama diretamente. Ainda assim definido atras de um Protocol
(mesmo motivo do plano geral, secao 3.5: a troca dev<->producao e' certa e
barata de prever agora, cara de retrofitar depois) — uma futura troca por
um servico de embeddings gerenciado (ex.: Bedrock) nao deve exigir mudar
PgVectorRetriever nem a migration.

Decisao de modelo: corpus pequeno e estavel (reindexacao e' evento raro) e
o AWS Academy Learner Lab nao comporta GPU ligada continuamente (plano
geral, secao 1.1) -> modelo local, CPU-only, sem custo de API nem
dependencia de rede em producao:
`sentence-transformers/all-MiniLM-L6-v2` (384 dimensoes, ~80MB, bem
estabelecido para similaridade semantica em textos curtos).
"""

from __future__ import annotations

import asyncio
from typing import Protocol

EMBEDDING_DIMENSIONS = 384


class Embedder(Protocol):
    async def embed(self, texts: list[str]) -> list[list[float]]: ...


class SentenceTransformersEmbedder:
    """Roda o modelo localmente, CPU-only. `embed()` despacha para
    `asyncio.to_thread` — a biblioteca `sentence-transformers` e' sincrona.
    O modelo e' carregado de forma preguicosa (na primeira chamada a
    `embed()`), nao no `__init__`, para nao pagar o custo de carregar pesos
    em processos que nunca chamam `embed()` (ex.: testes unitarios que so'
    exercitam outras partes do container)."""

    def __init__(self, model_name: str = "all-MiniLM-L6-v2") -> None:
        self._model_name = model_name
        self._model = None
        self._load_lock = asyncio.Lock()

    async def _get_model(self):
        if self._model is None:
            async with self._load_lock:
                if self._model is None:
                    self._model = await asyncio.to_thread(self._load_model)
        return self._model

    def _load_model(self):
        # Import adiado: sentence-transformers/torch sao pesados e nao
        # devem ser custo de import de todo mundo que importa este modulo
        # (ex.: so' para usar o Protocol Embedder em type hints).
        from sentence_transformers import SentenceTransformer

        return SentenceTransformer(self._model_name)

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        model = await self._get_model()
        vectors = await asyncio.to_thread(
            model.encode, texts, convert_to_numpy=True, normalize_embeddings=False
        )
        return [vector.tolist() for vector in vectors]
