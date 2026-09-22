"""Fase 6 — SentenceTransformersEmbedder. Ver .cursor/specs/fase6.spec.md,
secao 4.1.

Requer rede na primeira execucao (baixa os pesos de
sentence-transformers/all-MiniLM-L6-v2 do Hugging Face Hub, cacheados
localmente depois) — nao roda no ambiente de sandbox usado para
desenvolver esta fase, onde acesso a huggingface.co e' bloqueado por
politica de rede da organizacao (mesma classe de limitacao que bloqueou
Docker Hub nas Fases 3/5; ver relatorio da Fase 6). Rode localmente com:

    pip install -e ".[dev]"
    pytest -m integration tests/integration/rag/test_embedder.py -v
"""

from __future__ import annotations

import math

import pytest

from auditor.infrastructure.rag.embedder import (
    EMBEDDING_DIMENSIONS,
    SentenceTransformersEmbedder,
)

pytestmark = pytest.mark.integration


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    return dot / (norm_a * norm_b)


@pytest.fixture(scope="module")
def embedder() -> SentenceTransformersEmbedder:
    return SentenceTransformersEmbedder()


class TestDeterminism:
    @pytest.mark.asyncio
    async def test_same_text_embedded_twice_yields_identical_vectors(self, embedder):
        [first] = await embedder.embed(["illuminanceLevel"])
        [second] = await embedder.embed(["illuminanceLevel"])

        assert first == second


class TestSemanticSimilarity:
    @pytest.mark.asyncio
    async def test_semantically_close_texts_are_more_similar_than_unrelated_text(
        self, embedder
    ):
        near_a, near_b, unrelated = await embedder.embed(
            [
                "lum",
                "illuminanceLevel, nivel de iluminancia",
                "politica de retencao de logs",
            ]
        )

        sim_near = _cosine_similarity(near_a, near_b)
        sim_far_1 = _cosine_similarity(near_a, unrelated)
        sim_far_2 = _cosine_similarity(near_b, unrelated)

        assert sim_near > sim_far_1
        assert sim_near > sim_far_2


class TestEmptyInput:
    @pytest.mark.asyncio
    async def test_empty_list_returns_empty_list_without_loading_model(self):
        embedder = SentenceTransformersEmbedder()

        result = await embedder.embed([])

        assert result == []
        assert embedder._model is None


class TestShape:
    @pytest.mark.asyncio
    async def test_n_texts_yield_n_vectors_of_384_dimensions_in_order(self, embedder):
        texts = ["a", "b", "c"]

        vectors = await embedder.embed(texts)

        assert len(vectors) == len(texts)
        for vector in vectors:
            assert len(vector) == EMBEDDING_DIMENSIONS
