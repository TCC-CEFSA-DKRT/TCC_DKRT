"""Fase 10, secao 5 — script reprodutivel do experimento. Ver
.cursor/specs/fase10.spec.md, secoes 1 (dataset), 2 (execucao), 3
(metricas) e 5 (este arquivo).

Vive em `auditor.experiment` (nao em `application`/`interfaces`) pelo mesmo
motivo de `experiment/metrics.py`: ferramental de medicao do TCC, nunca
importado pelo sistema que atende trafego real. O executavel de fato e'
`scripts/run_experiment.py` (wrapper fino que so' chama `main()` daqui) —
a logica mora aqui para poder ser testada com `pythonpath=src` como
qualquer outro modulo do projeto (`tests/unit/experiment/
test_run_experiment.py`), sem precisar de um mecanismo de import especial
para arquivos soltos em `scripts/`.

Fluxo (secao 2/5): carrega o dataset (secao 1) -> escreve as entidades no
Orion real (upsert direto via NGSI-v2, nunca via `ContextBrokerPort`, que so'
le' — Fase 4, secao 1) -> dispara UM `POST /audits` por tipo NGSI presente
no dataset (fila -> worker -> Nivel 1 -> Nivel 2, Fase 5/7) -> aguarda cada
run terminar via polling em `GET /audits/{id}/progress` (Fase 5) -> busca o
relatorio completo via `GET /audits/{id}` -> casa cada `EntityReport` de
volta ao caso do dataset pelo `entity_id` -> calcula as cinco metricas
(`auditor.experiment.metrics`) -> grava `results/experiment-<data>.json` +
`results/experiment-<data>.md`.

**Nunca mockado** (secao 2): tudo aqui fala HTTP de verdade com um Orion e
uma API REST rodando (mesmo `docker-compose` das Fases 4/5) — e' isso que
torna o resultado uma medida do sistema real, nao de um fake.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

import httpx

from auditor.domain.entities.entity_report import InferenceBackend
from auditor.domain.entities.recommendation import Recommendation, RecommendationAction
from auditor.domain.entities.violation import (
    DetectionSource,
    Violation,
    ViolationSeverity,
)
from auditor.domain.services.structural_validator import StructuralValidator
from auditor.domain.value_objects.entity_type import EntityType
from auditor.domain.value_objects.tenant import Tenant
from auditor.experiment.metrics import (
    EntityTiming,
    ExpectedViolation,
    HallucinationCheck,
    HallucinationRate,
    InferenceCost,
    PrecisionRecallF1,
    Rate,
    TimeDistribution,
    aggregate_precision_recall_f1,
    check_hallucination,
    exclusive_slm_detection_rate,
    hallucination_rate,
    inference_cost_bedrock,
    inference_cost_ollama,
    time_distribution_by_level,
)

_TERMINAL_STATUSES = {"completed", "failed", "partial"}


# ---------------------------------------------------------------------------
# Dataset (fase10.spec.md, secao 1) — ver dataset/experiment/README.md
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DatasetCase:
    """Um caso do dataset controlado — um subdiretorio de
    `dataset/experiment/<model_name>/<case_id>/`."""

    model_name: str
    case_id: str
    entity: dict[str, Any]
    expected_violations: tuple[ExpectedViolation, ...]

    @property
    def entity_id(self) -> str:
        return self.entity["id"]

    @property
    def entity_type(self) -> str:
        return self.entity["type"]


def _parse_expected_violation(raw: dict[str, Any]) -> ExpectedViolation:
    return ExpectedViolation(
        rule=raw["rule"],
        attribute_path=raw["attribute_path"],
        severity=ViolationSeverity(raw["severity"]),
        detected_by=DetectionSource(raw["detected_by"]),
        proposed_patch=raw.get("proposed_patch"),
    )


def load_dataset(dataset_dir: Path) -> list[DatasetCase]:
    """Formato (ver dataset/experiment/README.md, escrito junto desta
    fase): `dataset_dir/<model_name>/<case_id>/entity.json` (entidade
    NGSI-v2 completa) + `.../ground_truth.json`
    (`{"expected_violations": [...]}`, um item por `ExpectedViolation`).

    Nunca gera/imagina dados de dataset — so' le' o que ja' foi rotulado
    por humano (regra nao-negociavel da secao 1) e falha alto e claro se o
    diretorio nao existir ou estiver incompleto, em vez de silenciosamente
    rodar um experimento vazio ou parcial."""
    if not dataset_dir.is_dir():
        raise FileNotFoundError(
            f"Dataset nao encontrado em {dataset_dir} — ver "
            "dataset/experiment/README.md para o formato esperado e a regra "
            "de curadoria humana (.cursor/specs/fase10.spec.md, secao 1)."
        )
    cases: list[DatasetCase] = []
    for model_dir in sorted(p for p in dataset_dir.iterdir() if p.is_dir()):
        for case_dir in sorted(p for p in model_dir.iterdir() if p.is_dir()):
            entity_path = case_dir / "entity.json"
            ground_truth_path = case_dir / "ground_truth.json"
            if not entity_path.is_file() or not ground_truth_path.is_file():
                raise FileNotFoundError(
                    f"Caso incompleto em {case_dir} — esperado entity.json "
                    "e ground_truth.json (dataset/experiment/README.md)."
                )
            entity = json.loads(entity_path.read_text(encoding="utf-8"))
            ground_truth = json.loads(ground_truth_path.read_text(encoding="utf-8"))
            expected = tuple(
                _parse_expected_violation(v)
                for v in ground_truth.get("expected_violations", [])
            )
            cases.append(
                DatasetCase(
                    model_name=model_dir.name,
                    case_id=case_dir.name,
                    entity=entity,
                    expected_violations=expected,
                )
            )
    if not cases:
        raise ValueError(
            f"Dataset em {dataset_dir} nao tem nenhum caso — nada para "
            "experimentar (fase10.spec.md, secao 8: dataset precisa cobrir "
            "mais de um Smart Data Model)."
        )
    return cases


# ---------------------------------------------------------------------------
# Carga no Orion + disparo/polling via API REST (fase10.spec.md, secao 2)
# ---------------------------------------------------------------------------


def _tenant_headers(tenant: Tenant) -> dict[str, str]:
    return {
        "Fiware-Service": tenant.fiware_service,
        "Fiware-ServicePath": tenant.fiware_service_path,
    }


async def load_entities_into_orion(
    cases: list[DatasetCase],
    *,
    broker_url: str,
    tenant: Tenant,
    client: httpx.AsyncClient,
) -> None:
    """Upsert direto no Orion (`?options=upsert`) — nunca via
    `ContextBrokerPort` (Fase 4: so' `fetch_entities`, de proposito
    read-only). So' o experimento precisa ESCREVER dados de teste no
    broker; idempotente por `id`, entao rodar o script duas vezes contra o
    mesmo dataset so' sobrescreve as mesmas entidades (reprodutibilidade,
    secao 5)."""
    headers = _tenant_headers(tenant)
    for case in cases:
        response = await client.post(
            f"{broker_url.rstrip('/')}/v2/entities",
            params={"options": "upsert"},
            json=case.entity,
            headers=headers,
            timeout=30.0,
        )
        response.raise_for_status()


async def verify_api_tenant(
    *, api_base_url: str, tenant: Tenant, client: httpx.AsyncClient
) -> None:
    response = await client.get(f"{api_base_url.rstrip('/')}/session", timeout=30.0)
    response.raise_for_status()
    session_tenant = response.json().get("tenant")
    if session_tenant != {
        "fiware_service": tenant.fiware_service,
        "fiware_service_path": tenant.fiware_service_path,
    }:
        raise RuntimeError(
            f"A API em {api_base_url} nao esta configurada para o tenant do "
            f"experimento ({tenant.fiware_service!r}/{tenant.fiware_service_path!r}) "
            f"-- GET /session devolveu tenant={session_tenant!r}. Configure "
            "FIWARE_SERVICE/FIWARE_SERVICE_PATH da API (ou /config, no "
            "self-hosted) antes de rodar o experimento, para nao misturar "
            "dados de teste com um tenant real."
        )


async def trigger_audit(
    *, api_base_url: str, tenant: Tenant, entity_type: str, client: httpx.AsyncClient
) -> UUID:
    """`POST /audits` (fase10.spec.md secao 2) — um run por tipo NGSI, nao
    por entidade: audita TODAS as entidades daquele tipo no tenant do
    experimento de uma vez, mesmo contrato que a API expoe para uso real
    (Fase 4/5)."""
    response = await client.post(
        f"{api_base_url.rstrip('/')}/audits",
        json={"entity_type": entity_type, "entity_id": None},
        headers=_tenant_headers(tenant),
        timeout=30.0,
    )
    response.raise_for_status()
    return UUID(response.json()["run_id"])


async def wait_for_completion(
    *,
    api_base_url: str,
    tenant: Tenant,
    run_id: UUID,
    client: httpx.AsyncClient,
    poll_interval_seconds: float,
    timeout_seconds: float,
    sleep: Any = asyncio.sleep,
    clock: Any = time.monotonic,
) -> None:
    """Polling em `GET /audits/{id}/progress` (Fase 5) ate' um status
    terminal — `sleep`/`clock` injetaveis so' para os testes conseguirem
    simular o passar do tempo sem esperar de verdade."""
    headers = _tenant_headers(tenant)
    deadline = clock() + timeout_seconds
    while True:
        response = await client.get(
            f"{api_base_url.rstrip('/')}/audits/{run_id}/progress",
            headers=headers,
            timeout=30.0,
        )
        response.raise_for_status()
        body = response.json()
        if body["status"] in _TERMINAL_STATUSES:
            return
        if clock() >= deadline:
            raise TimeoutError(
                f"Run {run_id} nao chegou a um status terminal em "
                f"{timeout_seconds}s (ultimo status visto: {body['status']!r})."
            )
        await sleep(poll_interval_seconds)


async def fetch_audit_run(
    *, api_base_url: str, tenant: Tenant, run_id: UUID, client: httpx.AsyncClient
) -> dict[str, Any]:
    """`GET /audits/{id}` — o `AuditRunResponse` completo, com
    `processing_duration_seconds`/`semantic_analysis_usage` por entidade
    (instrumentacao adicionada nesta mesma fase) alem de
    violations/recommendations."""
    response = await client.get(
        f"{api_base_url.rstrip('/')}/audits/{run_id}",
        headers=_tenant_headers(tenant),
        timeout=30.0,
    )
    response.raise_for_status()
    return response.json()


# ---------------------------------------------------------------------------
# JSON (EntityReportResponse) -> tipos de dominio
# ---------------------------------------------------------------------------


def parse_violation(raw: dict[str, Any]) -> Violation:
    return Violation(
        attribute_path=raw["attribute_path"],
        severity=ViolationSeverity(raw["severity"]),
        rule=raw["rule"],
        expected=raw.get("expected"),
        found=raw.get("found"),
        message=raw["message"],
        detected_by=DetectionSource(raw["detected_by"]),
    )


def parse_recommendation(raw: dict[str, Any]) -> Recommendation:
    return Recommendation(
        attribute_path=raw["attribute_path"],
        action=RecommendationAction(raw["action"]),
        proposed_patch=raw["proposed_patch"],
        rationale=raw["rationale"],
        confidence=raw["confidence"],
    )


@dataclass(frozen=True)
class EntityResult:
    """Um `EntityReport` (ja' convertido para dominio) casado de volta ao
    caso do dataset que o originou."""

    case: DatasetCase
    violations: tuple[Violation, ...]
    recommendations: tuple[Recommendation, ...]
    processing_duration_seconds: float | None
    semantic_analysis_usage: dict[str, Any] | None
    semantic_analysis_skipped: bool


def parse_entity_result(raw: dict[str, Any], case: DatasetCase) -> EntityResult:
    return EntityResult(
        case=case,
        violations=tuple(parse_violation(v) for v in raw["violations"]),
        recommendations=tuple(parse_recommendation(r) for r in raw["recommendations"]),
        processing_duration_seconds=raw.get("processing_duration_seconds"),
        semantic_analysis_usage=raw.get("semantic_analysis_usage"),
        semantic_analysis_skipped=raw["semantic_analysis_skipped"],
    )


# ---------------------------------------------------------------------------
# Orquestracao ponta a ponta (fase10.spec.md, secao 2/5)
# ---------------------------------------------------------------------------


async def collect_results(
    cases: list[DatasetCase],
    *,
    api_base_url: str,
    tenant: Tenant,
    client: httpx.AsyncClient,
    poll_interval_seconds: float,
    timeout_seconds: float,
) -> list[EntityResult]:
    """Dispara um `POST /audits` por tipo NGSI presente no dataset,
    aguarda cada um terminar e casa os `EntityReport`s de volta aos casos
    — nunca por `POST /audits` por entidade individual: auditar por tipo e'
    o que o sistema real faz quando roda contra um tenant inteiro."""
    cases_by_type: dict[str, list[DatasetCase]] = {}
    for case in cases:
        cases_by_type.setdefault(case.entity_type, []).append(case)

    results: list[EntityResult] = []
    for entity_type, type_cases in cases_by_type.items():
        run_id = await trigger_audit(
            api_base_url=api_base_url, tenant=tenant, entity_type=entity_type, client=client
        )
        await wait_for_completion(
            api_base_url=api_base_url,
            tenant=tenant,
            run_id=run_id,
            client=client,
            poll_interval_seconds=poll_interval_seconds,
            timeout_seconds=timeout_seconds,
        )
        run_body = await fetch_audit_run(
            api_base_url=api_base_url, tenant=tenant, run_id=run_id, client=client
        )
        cases_by_id = {c.entity_id: c for c in type_cases}
        for report in run_body["reports"]:
            matching_case = cases_by_id.get(report["entity_id"])
            if matching_case is None:
                # Entidade pre-existente no tenant/tipo, de fora do dataset
                # deste run — nunca deveria entrar na medicao (o tenant do
                # experimento e' dedicado, mas um tenant reutilizado entre
                # execucoes pode acumular lixo de rodadas anteriores com
                # outro dataset).
                continue
            results.append(parse_entity_result(report, matching_case))

    missing = {c.entity_id for c in cases} - {r.case.entity_id for r in results}
    if missing:
        raise RuntimeError(
            f"{len(missing)} entidade(s) do dataset nao apareceram em nenhum "
            f"EntityReport: {sorted(missing)} — auditoria incompleta, "
            "relatorio nao seria confiavel."
        )
    return results


def _find_targeted_violation(
    recommendation: Recommendation, result: EntityResult
) -> Violation | None:
    """A `Violation` (do proprio `EntityReport`, nao do ground_truth) que
    esta `Recommendation` alega corrigir — pareamento por `attribute_path`,
    conforme `check_hallucination` (metrics.py) pede de quem chama."""
    for violation in result.violations:
        if violation.attribute_path == recommendation.attribute_path:
            return violation
    return None


def _compute_inference_cost(
    results: list[EntityResult], *, price_per_1k_tokens: float | None
) -> InferenceCost | None:
    """fase10.spec.md secao 3.4 — nunca mistura Ollama (segundos) e
    Bedrock (USD) num unico numero; `None` quando nenhuma entidade passou
    pelo Nivel 2 (sem dados, nao zero)."""
    backends = {
        r.semantic_analysis_usage["backend"]
        for r in results
        if r.semantic_analysis_usage is not None
    }
    if not backends:
        return None
    if len(backends) > 1:
        raise ValueError(
            f"Experimento misturou backends de inferencia ({sorted(backends)}) "
            "num unico run — fase10.spec.md secao 3.4 exige uma unidade de "
            "custo por relatorio, nunca comparar Ollama e Bedrock juntos."
        )
    backend = backends.pop()
    if backend == InferenceBackend.OLLAMA.value:
        compute_seconds = [
            r.semantic_analysis_usage["compute_seconds"]
            for r in results
            if r.semantic_analysis_usage is not None
            and r.semantic_analysis_usage.get("compute_seconds") is not None
        ]
        return inference_cost_ollama(compute_seconds)

    if price_per_1k_tokens is None:
        raise ValueError(
            "Backend Bedrock detectado nos resultados, mas "
            "--price-per-1k-tokens nao foi informado — fase10.spec.md secao "
            "3.4 exige o preco para converter tokens consumidos em custo."
        )
    token_counts = [
        (r.semantic_analysis_usage.get("prompt_tokens") or 0)
        + (r.semantic_analysis_usage.get("completion_tokens") or 0)
        for r in results
        if r.semantic_analysis_usage is not None
    ]
    return inference_cost_bedrock(token_counts, price_per_1k_tokens=price_per_1k_tokens)


@dataclass(frozen=True)
class ExperimentReport:
    generated_at: str
    dataset_case_count: int
    accuracy_structural: PrecisionRecallF1
    accuracy_semantic: PrecisionRecallF1
    exclusive_slm_detection: Rate
    time_distribution: dict[str, TimeDistribution]
    inference_cost: InferenceCost | None
    hallucination: HallucinationRate
    hallucination_unscored_recommendations: int


def compute_metrics(
    results: list[EntityResult],
    *,
    schema_by_type: dict[str, dict[str, Any]],
    price_per_1k_tokens: float | None,
) -> ExperimentReport:
    """As cinco metricas da secao 3, todas calculadas a partir do mesmo
    `results` — nenhuma chamada de rede aqui (`schema_by_type` ja' vem
    resolvido por quem chama), por isso e' testavel com fixtures
    sinteticas (mesmo espirito de metrics.py, secao 6)."""
    per_entity = [(r.violations, r.case.expected_violations) for r in results]

    accuracy_structural = aggregate_precision_recall_f1(
        per_entity, level=DetectionSource.STRUCTURAL
    )
    accuracy_semantic = aggregate_precision_recall_f1(per_entity, level=DetectionSource.SEMANTIC)
    exclusive_slm = exclusive_slm_detection_rate(per_entity)

    timings = [
        EntityTiming(
            entity_id=r.case.entity_id,
            duration_seconds=r.processing_duration_seconds,
            reached_level2=not r.semantic_analysis_skipped,
        )
        for r in results
        if r.processing_duration_seconds is not None
    ]
    time_dist = time_distribution_by_level(timings)

    inference_cost = _compute_inference_cost(results, price_per_1k_tokens=price_per_1k_tokens)

    validator = StructuralValidator()
    checks: list[HallucinationCheck] = []
    unscored = 0
    for result in results:
        schema = schema_by_type.get(result.case.entity_type)
        for recommendation in result.recommendations:
            targeted = _find_targeted_violation(recommendation, result)
            if targeted is None or not schema:
                # Sem violacao correspondente (ou sem schema resolvido para
                # o tipo) para avaliar as condicoes 2/3 — nao classificada,
                # nunca contada como "nao alucinada" por omissao.
                unscored += 1
                continue
            checks.append(
                check_hallucination(
                    recommendation,
                    targeted_violation=targeted,
                    entity=result.case.entity,
                    schema=schema,
                    validator=validator,
                )
            )

    return ExperimentReport(
        generated_at=datetime.now(timezone.utc).isoformat(),
        dataset_case_count=len(results),
        accuracy_structural=accuracy_structural,
        accuracy_semantic=accuracy_semantic,
        exclusive_slm_detection=exclusive_slm,
        time_distribution=time_dist,
        inference_cost=inference_cost,
        hallucination=hallucination_rate(checks),
        hallucination_unscored_recommendations=unscored,
    )


async def run_experiment(
    *,
    dataset_dir: Path,
    broker_url: str,
    api_base_url: str,
    tenant: Tenant,
    poll_interval_seconds: float,
    timeout_seconds: float,
    price_per_1k_tokens: float | None,
) -> ExperimentReport:
    # Import local: `container.py` monta o composition root inteiro
    # (engine de banco, embedder etc.) so' para reusar
    # `get_schema_catalog()` — atrasar o import evita pagar esse custo em
    # quem so' quer importar tipos deste modulo (ex.: os testes de
    # compute_metrics, que nunca chamam run_experiment).
    from auditor.infrastructure.config.container import get_schema_catalog

    cases = load_dataset(dataset_dir)

    async with httpx.AsyncClient() as client:
        await verify_api_tenant(api_base_url=api_base_url, tenant=tenant, client=client)
        await load_entities_into_orion(cases, broker_url=broker_url, tenant=tenant, client=client)
        results = await collect_results(
            cases,
            api_base_url=api_base_url,
            tenant=tenant,
            client=client,
            poll_interval_seconds=poll_interval_seconds,
            timeout_seconds=timeout_seconds,
        )

    schema_catalog = get_schema_catalog()
    schema_by_type: dict[str, dict[str, Any]] = {}
    for entity_type in {r.case.entity_type for r in results}:
        data_model = await schema_catalog.resolve_data_model(EntityType(entity_type))
        schema_by_type[entity_type] = (
            (await schema_catalog.fetch_schema(data_model)).content if data_model else {}
        )

    return compute_metrics(
        results, schema_by_type=schema_by_type, price_per_1k_tokens=price_per_1k_tokens
    )


# ---------------------------------------------------------------------------
# Relatorio reprodutivel (fase10.spec.md, secao 5)
# ---------------------------------------------------------------------------


def _pr_f1_to_dict(m: PrecisionRecallF1) -> dict[str, Any]:
    return {
        "precision": m.precision,
        "recall": m.recall,
        "f1": m.f1,
        "true_positives": m.true_positives,
        "false_positives": m.false_positives,
        "false_negatives": m.false_negatives,
    }


def _rate_to_dict(r: Rate) -> dict[str, Any]:
    return {"value": r.value, "covered": r.covered, "total": r.total}


def _time_dist_to_dict(d: TimeDistribution) -> dict[str, Any]:
    return {"p50": d.p50, "p95": d.p95, "maximum": d.maximum, "count": d.count}


def _inference_cost_to_dict(c: InferenceCost | None) -> dict[str, Any] | None:
    if c is None:
        return None
    return {"unit": c.unit, "total": c.total, "per_entity_average": c.per_entity_average}


def _hallucination_to_dict(h: HallucinationRate) -> dict[str, Any]:
    return {
        "value": h.value,
        "hallucinated": h.hallucinated,
        "total": h.total,
        "by_reason": {reason.value: count for reason, count in h.by_reason.items()},
    }


def report_to_json(report: ExperimentReport) -> dict[str, Any]:
    return {
        "generated_at": report.generated_at,
        "dataset_case_count": report.dataset_case_count,
        "metrics": {
            "accuracy_structural": _pr_f1_to_dict(report.accuracy_structural),
            "accuracy_semantic": _pr_f1_to_dict(report.accuracy_semantic),
            "exclusive_slm_detection_rate": _rate_to_dict(report.exclusive_slm_detection),
            "time_distribution_seconds": {
                level: _time_dist_to_dict(dist) for level, dist in report.time_distribution.items()
            },
            "inference_cost": _inference_cost_to_dict(report.inference_cost),
            "hallucination_rate": _hallucination_to_dict(report.hallucination),
        },
        "hallucination_unscored_recommendations": report.hallucination_unscored_recommendations,
    }


def _fmt(value: float | None, digits: int = 3) -> str:
    return "N/A" if value is None else f"{value:.{digits}f}"


def report_to_markdown(report: ExperimentReport) -> str:
    acc_s = report.accuracy_structural
    acc_sem = report.accuracy_semantic
    lines = [
        f"# Resultado do experimento — {report.generated_at}",
        "",
        f"Dataset: {report.dataset_case_count} entidades processadas.",
        "",
        "## 3.1 — Acuracia por nivel",
        "",
        "| Nivel | Precision | Recall | F1 | TP | FP | FN |",
        "|---|---|---|---|---|---|---|",
        (
            f"| Estrutural | {_fmt(acc_s.precision)} | {_fmt(acc_s.recall)} | "
            f"{_fmt(acc_s.f1)} | {acc_s.true_positives} | {acc_s.false_positives} | "
            f"{acc_s.false_negatives} |"
        ),
        (
            f"| Semantico | {_fmt(acc_sem.precision)} | {_fmt(acc_sem.recall)} | "
            f"{_fmt(acc_sem.f1)} | {acc_sem.true_positives} | {acc_sem.false_positives} | "
            f"{acc_sem.false_negatives} |"
        ),
        "",
        "## 3.2 — Violacoes exclusivas do SLM",
        "",
        (
            f"Taxa: {_fmt(report.exclusive_slm_detection.value)} "
            f"({report.exclusive_slm_detection.covered}/"
            f"{report.exclusive_slm_detection.total})"
        ),
        "",
        "## 3.3 — Tempo por entidade (segundos)",
        "",
        "| Serie | p50 | p95 | Maximo | N |",
        "|---|---|---|---|---|",
    ]
    for level_key, label in (
        ("level1_only", "So Nivel 1"),
        ("level1_and_level2", "Nivel 1 + Nivel 2"),
    ):
        dist = report.time_distribution.get(level_key)
        if dist is None:
            continue
        lines.append(
            f"| {label} | {_fmt(dist.p50)} | {_fmt(dist.p95)} | {_fmt(dist.maximum)} | "
            f"{dist.count} |"
        )
    lines += ["", "## 3.4 — Custo de inferencia", ""]
    if report.inference_cost is None:
        lines.append("Sem dados (nenhuma entidade passou pelo Nivel 2).")
    else:
        unit_label = "USD" if report.inference_cost.unit == "usd" else "segundos de CPU/GPU"
        lines.append(
            f"Total: {report.inference_cost.total:.4f} {unit_label} — media por "
            f"entidade: {_fmt(report.inference_cost.per_entity_average, 4)} {unit_label}"
        )
    lines += [
        "",
        "## 3.5 — Taxa de alucinacao nas recomendacoes",
        "",
        (
            f"Taxa: {_fmt(report.hallucination.value)} "
            f"({report.hallucination.hallucinated}/{report.hallucination.total})"
        ),
        "",
        "| Motivo | Ocorrencias |",
        "|---|---|",
    ]
    for reason, count in report.hallucination.by_reason.items():
        lines.append(f"| {reason.value} | {count} |")
    if report.hallucination_unscored_recommendations:
        lines.append(
            f"\n_{report.hallucination_unscored_recommendations} recomendacao(oes) sem "
            "violacao correspondente no relatorio — nao entraram no calculo "
            "(nao classificadas, nunca contadas como 'nao alucinadas')._"
        )
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Fase 10 — roda o experimento completo contra o sistema real "
            "(Orion + API + worker + SLM) e grava o relatorio reprodutivel."
        )
    )
    parser.add_argument(
        "--dataset-dir", type=Path, default=Path("dataset/experiment"),
        help="Diretorio do dataset controlado (ver dataset/experiment/README.md).",
    )
    parser.add_argument("--results-dir", type=Path, default=Path("results"))
    parser.add_argument(
        "--broker-url", default="http://localhost:1026", help="URL do Orion (NGSI-v2)."
    )
    parser.add_argument(
        "--api-base-url", default="http://localhost:8000",
        help="URL base da API REST do auditor.",
    )
    parser.add_argument(
        "--tenant", default="experiment",
        help="Fiware-Service dedicado ao experimento — nunca reusar um tenant com dados reais.",
    )
    parser.add_argument("--service-path", default="/")
    parser.add_argument("--poll-interval-seconds", type=float, default=1.0)
    parser.add_argument("--timeout-seconds", type=float, default=1800.0)
    parser.add_argument(
        "--price-per-1k-tokens", type=float, default=None,
        help="Obrigatorio se o backend de inferencia configurado for Bedrock (secao 3.4).",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    args = _build_arg_parser().parse_args(argv)
    tenant = Tenant(fiware_service=args.tenant, fiware_service_path=args.service_path)

    report = asyncio.run(
        run_experiment(
            dataset_dir=args.dataset_dir,
            broker_url=args.broker_url,
            api_base_url=args.api_base_url,
            tenant=tenant,
            poll_interval_seconds=args.poll_interval_seconds,
            timeout_seconds=args.timeout_seconds,
            price_per_1k_tokens=args.price_per_1k_tokens,
        )
    )

    args.results_dir.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    json_path = args.results_dir / f"experiment-{date_str}.json"
    md_path = args.results_dir / f"experiment-{date_str}.md"
    json_path.write_text(
        json.dumps(report_to_json(report), indent=2, ensure_ascii=False), encoding="utf-8"
    )
    md_path.write_text(report_to_markdown(report), encoding="utf-8")
    print(f"Relatorio gravado em {json_path} e {md_path}.")


if __name__ == "__main__":
    main()
