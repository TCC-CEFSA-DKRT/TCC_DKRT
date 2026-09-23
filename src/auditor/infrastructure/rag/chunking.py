"""to_chunk_text — ver .cursor/specs/fase6.spec.md, secao 3.

Chunking "por caso/regra, nao por tamanho fixo" (plano geral, secao 3.4):
cada `RawCorpusEntry` ja e' um chunk inteiro — este modulo so' renderiza
seus campos estruturados num texto unico e coerente, pronto para ser
embutido (secao 4) e, na Fase 7, mostrado no prompt do SLM. Determinismo
byte a byte e' obrigatorio (mesma entrada -> mesmo texto sempre), condicao
necessaria para o upsert idempotente da secao 7 nao recalcular embedding a
toa.
"""

from __future__ import annotations

from auditor.domain.ports.knowledge_retriever_port import KnowledgeCategory
from auditor.infrastructure.rag.corpus_loader import RawCorpusEntry


def to_chunk_text(entry: RawCorpusEntry) -> str:
    if entry.category is KnowledgeCategory.CONVENTION:
        return entry.fields["statement"].strip()

    if entry.category is KnowledgeCategory.ANNOTATED_CASE:
        return (
            f"Exemplo incorreto: {entry.fields['incorrect_example'].strip()}\n"
            f"Explicacao: {entry.fields['explanation'].strip()}\n"
            f"Correcao: {entry.fields['correction'].strip()}"
        )

    if entry.category is KnowledgeCategory.SYNONYM_GLOSSARY:
        canonical = entry.fields["canonical"]
        seen_as = ", ".join(entry.fields["seen_as"])
        return (
            f"O atributo canonico e' '{canonical}'. Tambem visto como: {seen_as}."
        )

    if entry.category is KnowledgeCategory.RECOMMENDATION_STYLE:
        return (
            f"Rationale: {entry.fields['example_rationale'].strip()}\n"
            f"Patch de exemplo: {entry.fields['example_patch'].strip()}"
        )

    raise AssertionError(f"categoria sem renderizacao de chunk: {entry.category}")
