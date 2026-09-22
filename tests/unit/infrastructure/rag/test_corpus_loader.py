"""Fase 6 — CorpusLoader. Ver .cursor/specs/fase6.spec.md, secao 2.2.

Puro, sem banco nem rede — usa tmp_path para os casos de erro e o corpus
REAL em knowledge/ (nao fixtures) para a prova de que o corpus inicial nao
esta vazio.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from auditor.domain.ports.knowledge_retriever_port import KnowledgeCategory
from auditor.infrastructure.rag.corpus_loader import (
    CorpusLoader,
    CorpusValidationError,
    KNOWLEDGE_DIR,
)


def _write_minimal_corpus(
    corpus_dir: Path,
    *,
    conventions: str = "- id: convention-a\n  statement: texto a\n",
    annotated_cases: str = (
        "- id: case-a\n"
        "  incorrect_example: '{}'\n"
        "  explanation: motivo\n"
        "  correction: '{}'\n"
    ),
    synonyms: str = "- id: synonym-a\n  canonical: attr\n  seen_as: [a]\n",
    recommendation_style: str = (
        "- id: style-a\n  example_rationale: motivo\n  example_patch: '{}'\n"
    ),
) -> None:
    (corpus_dir / "conventions.yaml").write_text(conventions, encoding="utf-8")
    (corpus_dir / "annotated_cases.yaml").write_text(annotated_cases, encoding="utf-8")
    (corpus_dir / "synonyms.yaml").write_text(synonyms, encoding="utf-8")
    (corpus_dir / "recommendation_style.yaml").write_text(
        recommendation_style, encoding="utf-8"
    )


class TestRealCorpus:
    def test_load_all_returns_at_least_one_entry_per_category(self):
        entries = CorpusLoader().load_all(KNOWLEDGE_DIR)

        categories_present = {entry.category for entry in entries}

        assert categories_present == set(KnowledgeCategory)

    def test_real_corpus_has_no_validation_errors(self):
        # so' o fato de nao levantar CorpusValidationError ja e' a asserção
        CorpusLoader().load_all(KNOWLEDGE_DIR)


class TestValidation:
    def test_duplicate_id_across_files_raises_corpus_validation_error(self, tmp_path):
        _write_minimal_corpus(
            tmp_path,
            conventions="- id: dup-id\n  statement: texto a\n",
            synonyms="- id: dup-id\n  canonical: attr\n  seen_as: [a]\n",
        )

        with pytest.raises(CorpusValidationError, match="dup-id"):
            CorpusLoader().load_all(tmp_path)

    def test_annotated_case_missing_correction_raises_corpus_validation_error(
        self, tmp_path
    ):
        _write_minimal_corpus(
            tmp_path,
            annotated_cases=(
                "- id: case-missing-correction\n"
                "  incorrect_example: '{}'\n"
                "  explanation: motivo\n"
            ),
        )

        with pytest.raises(CorpusValidationError, match="case-missing-correction"):
            CorpusLoader().load_all(tmp_path)

    def test_id_not_following_naming_convention_still_loads(self, tmp_path):
        _write_minimal_corpus(
            tmp_path, conventions="- id: totally_unconventional_ID_123\n  statement: texto a\n"
        )

        entries = CorpusLoader().load_all(tmp_path)

        loaded_ids = {entry.chunk_id for entry in entries}
        assert "totally_unconventional_ID_123" in loaded_ids
