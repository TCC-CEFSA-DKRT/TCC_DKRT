"""Fase 6 — to_chunk_text. Ver .cursor/specs/fase6.spec.md, secao 3.1.

Puro, sem banco nem rede."""

from __future__ import annotations

from auditor.domain.ports.knowledge_retriever_port import KnowledgeCategory
from auditor.infrastructure.rag.chunking import to_chunk_text
from auditor.infrastructure.rag.corpus_loader import RawCorpusEntry


def _entry(category: KnowledgeCategory, fields: dict, tags: tuple[str, ...] = ()) -> RawCorpusEntry:
    return RawCorpusEntry(chunk_id="x", category=category, tags=tags, fields=fields)


class TestAnnotatedCase:
    def test_chunk_text_contains_example_explanation_and_correction_in_order(self):
        entry = _entry(
            KnowledgeCategory.ANNOTATED_CASE,
            {
                "incorrect_example": '{"lum": 1}',
                "explanation": "abreviacao informal",
                "correction": '{"illuminanceLevel": 1}',
            },
        )

        text = to_chunk_text(entry)

        idx_incorrect = text.index('{"lum": 1}')
        idx_explanation = text.index("abreviacao informal")
        idx_correction = text.index('{"illuminanceLevel": 1}')
        assert idx_incorrect < idx_explanation < idx_correction


class TestSynonymGlossary:
    def test_chunk_text_contains_all_synonyms(self):
        entry = _entry(
            KnowledgeCategory.SYNONYM_GLOSSARY,
            {"canonical": "temperature", "seen_as": ["temp", "tempC", "temperatura"]},
        )

        text = to_chunk_text(entry)

        assert "temp" in text
        assert "tempC" in text
        assert "temperatura" in text
        assert "temperature" in text


class TestConvention:
    def test_chunk_text_is_exactly_the_statement(self):
        entry = _entry(
            KnowledgeCategory.CONVENTION, {"statement": "lowerCamelCase sempre."}
        )

        text = to_chunk_text(entry)

        assert text == "lowerCamelCase sempre."


class TestDeterminism:
    def test_same_entry_produces_byte_identical_text_twice(self):
        entry = _entry(
            KnowledgeCategory.RECOMMENDATION_STYLE,
            {"example_rationale": "motivo", "example_patch": '{"a": 1}'},
        )

        assert to_chunk_text(entry) == to_chunk_text(entry)
