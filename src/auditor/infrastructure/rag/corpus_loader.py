"""CorpusLoader — ver .cursor/specs/fase6.spec.md, secao 2.1.

Carrega os quatro arquivos YAML de `knowledge/` (curadoria do time,
versionada no repositorio — nunca gerada em runtime, nunca scraping de
schema ao vivo) e valida cada entrada de acordo com os campos obrigatorios
da sua categoria. Falha cedo (`CorpusValidationError`) em vez de ingerir
silenciosamente uma entrada ambigua ou incompleta.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from auditor.domain.ports.knowledge_retriever_port import KnowledgeCategory

KNOWLEDGE_DIR = Path(__file__).resolve().parents[4] / "knowledge"

# Nome do arquivo -> categoria + campos obrigatorios por entrada (alem de
# `id`, que e' obrigatorio para todas). `tags` e' opcional em todas (vira
# tupla vazia quando ausente).
_FILE_SPECS: dict[str, tuple[KnowledgeCategory, tuple[str, ...]]] = {
    "conventions.yaml": (KnowledgeCategory.CONVENTION, ("statement",)),
    "annotated_cases.yaml": (
        KnowledgeCategory.ANNOTATED_CASE,
        ("incorrect_example", "explanation", "correction"),
    ),
    "synonyms.yaml": (KnowledgeCategory.SYNONYM_GLOSSARY, ("canonical", "seen_as")),
    "recommendation_style.yaml": (
        KnowledgeCategory.RECOMMENDATION_STYLE,
        ("example_rationale", "example_patch"),
    ),
}


class CorpusValidationError(ValueError):
    """Levantado quando o corpus curado tem um `id` duplicado ou uma
    entrada sem um campo obrigatorio da sua categoria — nunca ingerido
    silenciosamente (fase6.spec.md, secao 2.2)."""


@dataclass(frozen=True)
class RawCorpusEntry:
    chunk_id: str
    category: KnowledgeCategory
    tags: tuple[str, ...]
    fields: dict


class CorpusLoader:
    def load_all(self, corpus_dir: Path = KNOWLEDGE_DIR) -> list[RawCorpusEntry]:
        entries: list[RawCorpusEntry] = []
        seen_ids: set[str] = set()

        for filename, (category, required_fields) in _FILE_SPECS.items():
            path = corpus_dir / filename
            raw_items = yaml.safe_load(path.read_text(encoding="utf-8")) or []

            for item in raw_items:
                chunk_id = item.get("id")
                if not chunk_id:
                    raise CorpusValidationError(f"{filename}: entrada sem campo 'id'")
                if chunk_id in seen_ids:
                    raise CorpusValidationError(
                        f"{filename}: id duplicado no corpus: '{chunk_id}'"
                    )
                seen_ids.add(chunk_id)

                for field_name in required_fields:
                    if item.get(field_name) in (None, ""):
                        raise CorpusValidationError(
                            f"{filename}: entrada '{chunk_id}' sem campo "
                            f"obrigatorio '{field_name}' para categoria "
                            f"{category.value}"
                        )

                tags = tuple(item.get("tags", ()))
                fields = {k: v for k, v in item.items() if k not in ("id", "tags")}
                entries.append(
                    RawCorpusEntry(
                        chunk_id=chunk_id,
                        category=category,
                        tags=tags,
                        fields=fields,
                    )
                )

        return entries
