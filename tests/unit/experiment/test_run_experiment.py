"""Fase 10, secao 5/6 — script reprodutivel do experimento. Ver
.cursor/specs/fase10.spec.md.

So' exercita logica pura (parsing, orquestracao de metricas, renderizacao
do relatorio) e as chamadas HTTP com `httpx.MockTransport` (mesmo padrao de
tests/unit/infrastructure/llm/test_ollama_analyzer.py) — nunca um Orion/API
real, consistente com a seção 6 do spec (o CÓDIGO DE MEDIÇÃO e' testado com
fixtures conhecidas; rodar contra o sistema real de verdade e' o proprio
`scripts/run_experiment.py` em uso, fora do escopo de um teste automatizado).
"""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import httpx
import pytest

from auditor.domain.entities.recommendation import Recommendation, RecommendationAction
from auditor.domain.entities.violation import (
    DetectionSource,
    Violation,
    ViolationSeverity,
)
from auditor.domain.value_objects.tenant import Tenant
from auditor.experiment.metrics import ExpectedViolation, HallucinationReason
from auditor.experiment.run_experiment import (
    DatasetCase,
    EntityResult,
    _compute_inference_cost,
    _find_targeted_violation,
    compute_metrics,
    fetch_audit_run,
    load_dataset,
    load_entities_into_orion,
    parse_entity_result,
    parse_recommendation,
    parse_violation,
    report_to_json,
    report_to_markdown,
    trigger_audit,
    wait_for_completion,
)

_TENANT = Tenant(fiware_service="experiment", fiware_service_path="/")


# ---------------------------------------------------------------------------
# load_dataset
# ---------------------------------------------------------------------------


def _write_case(
    base: Path,
    model_name: str,
    case_id: str,
    *,
    entity: dict,
    expected_violations: list[dict],
) -> None:
    case_dir = base / model_name / case_id
    case_dir.mkdir(parents=True)
    (case_dir / "entity.json").write_text(json.dumps(entity), encoding="utf-8")
    (case_dir / "ground_truth.json").write_text(
        json.dumps({"expected_violations": expected_violations}), encoding="utf-8"
    )


class TestLoadDataset:
    def test_loads_cases_across_multiple_models(self, tmp_path: Path):
        _write_case(
            tmp_path,
            "Streetlight",
            "conformant-001",
            entity={"id": "urn:1", "type": "Streetlight"},
            expected_violations=[],
        )
        _write_case(
            tmp_path,
            "WeatherObserved",
            "semantic-001",
            entity={"id": "urn:2", "type": "WeatherObserved"},
            expected_violations=[
                {
                    "rule": "attribute_name_synonym",
                    "attribute_path": "temperature",
                    "severity": "error",
                    "detected_by": "semantic",
                    "proposed_patch": {"from": "temp", "to": "temperature"},
                }
            ],
        )

        cases = load_dataset(tmp_path)

        assert len(cases) == 2
        by_model = {c.model_name: c for c in cases}
        assert by_model["Streetlight"].entity_id == "urn:1"
        assert by_model["Streetlight"].entity_type == "Streetlight"
        assert by_model["Streetlight"].expected_violations == ()
        semantic_case = by_model["WeatherObserved"]
        assert len(semantic_case.expected_violations) == 1
        expected = semantic_case.expected_violations[0]
        assert expected.detected_by == DetectionSource.SEMANTIC
        assert expected.severity == ViolationSeverity.ERROR
        assert expected.proposed_patch == {"from": "temp", "to": "temperature"}

    def test_missing_dataset_directory_raises(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            load_dataset(tmp_path / "does-not-exist")

    def test_case_missing_ground_truth_raises(self, tmp_path: Path):
        case_dir = tmp_path / "Streetlight" / "case-1"
        case_dir.mkdir(parents=True)
        (case_dir / "entity.json").write_text("{}", encoding="utf-8")

        with pytest.raises(FileNotFoundError):
            load_dataset(tmp_path)

    def test_empty_dataset_directory_raises(self, tmp_path: Path):
        with pytest.raises(ValueError):
            load_dataset(tmp_path)


# ---------------------------------------------------------------------------
# parse_violation / parse_recommendation / parse_entity_result
# ---------------------------------------------------------------------------


class TestParsing:
    def test_parse_violation_round_trips_domain_fields(self):
        raw = {
            "attribute_path": "temp",
            "severity": "warning",
            "rule": "unexpected_property",
            "expected": None,
            "found": "temp",
            "message": "Atributo fora do schema.",
            "detected_by": "structural",
        }
        violation = parse_violation(raw)
        assert violation == Violation(
            attribute_path="temp",
            severity=ViolationSeverity.WARNING,
            rule="unexpected_property",
            expected=None,
            found="temp",
            message="Atributo fora do schema.",
            detected_by=DetectionSource.STRUCTURAL,
        )

    def test_parse_recommendation_round_trips_domain_fields(self):
        raw = {
            "attribute_path": "temp",
            "action": "rename_attribute",
            "proposed_patch": {"from": "temp", "to": "temperature"},
            "rationale": "sinonimo conhecido",
            "confidence": 0.9,
        }
        recommendation = parse_recommendation(raw)
        assert recommendation.action == RecommendationAction.RENAME_ATTRIBUTE
        assert recommendation.proposed_patch == {"from": "temp", "to": "temperature"}

    def test_parse_entity_result_carries_measurement_fields(self):
        case = DatasetCase(
            model_name="Streetlight", case_id="c1", entity={"id": "urn:1", "type": "Streetlight"},
            expected_violations=(),
        )
        raw = {
            "entity_id": "urn:1",
            "entity_type": "Streetlight",
            "status": "conformant",
            "violations": [],
            "recommendations": [],
            "semantic_analysis_skipped": False,
            "processing_duration_seconds": 1.5,
            "semantic_analysis_usage": {
                "backend": "ollama", "compute_seconds": 0.4,
                "prompt_tokens": None, "completion_tokens": None,
            },
        }
        result = parse_entity_result(raw, case)
        assert result.processing_duration_seconds == 1.5
        assert result.semantic_analysis_usage["backend"] == "ollama"
        assert result.semantic_analysis_skipped is False


# ---------------------------------------------------------------------------
# _find_targeted_violation
# ---------------------------------------------------------------------------


class TestFindTargetedViolation:
    def test_matches_by_attribute_path(self):
        violation = Violation(
            attribute_path="temp", severity=ViolationSeverity.ERROR, rule="attribute_name_synonym",
            expected="temperature", found="temp", message="msg", detected_by=DetectionSource.SEMANTIC,
        )
        case = DatasetCase(model_name="m", case_id="c", entity={"id": "urn:1", "type": "T"}, expected_violations=())
        result = EntityResult(
            case=case, violations=(violation,), recommendations=(), processing_duration_seconds=None,
            semantic_analysis_usage=None, semantic_analysis_skipped=False,
        )
        recommendation = Recommendation(
            attribute_path="temp", action=RecommendationAction.RENAME_ATTRIBUTE,
            proposed_patch={"from": "temp", "to": "temperature"}, rationale="r", confidence=0.9,
        )
        assert _find_targeted_violation(recommendation, result) is violation

    def test_no_match_returns_none(self):
        case = DatasetCase(model_name="m", case_id="c", entity={"id": "urn:1", "type": "T"}, expected_violations=())
        result = EntityResult(
            case=case, violations=(), recommendations=(), processing_duration_seconds=None,
            semantic_analysis_usage=None, semantic_analysis_skipped=False,
        )
        recommendation = Recommendation(
            attribute_path="temp", action=RecommendationAction.RENAME_ATTRIBUTE,
            proposed_patch={"from": "temp", "to": "temperature"}, rationale="r", confidence=0.9,
        )
        assert _find_targeted_violation(recommendation, result) is None


# ---------------------------------------------------------------------------
# _compute_inference_cost
# ---------------------------------------------------------------------------


def _result_with_usage(usage: dict | None) -> EntityResult:
    case = DatasetCase(model_name="m", case_id="c", entity={"id": "urn:1", "type": "T"}, expected_violations=())
    return EntityResult(
        case=case, violations=(), recommendations=(), processing_duration_seconds=None,
        semantic_analysis_usage=usage, semantic_analysis_skipped=False,
    )


class TestComputeInferenceCost:
    def test_no_usage_anywhere_yields_none(self):
        results = [_result_with_usage(None), _result_with_usage(None)]
        assert _compute_inference_cost(results, price_per_1k_tokens=None) is None

    def test_ollama_usage_uses_compute_seconds(self):
        results = [
            _result_with_usage({"backend": "ollama", "compute_seconds": 1.0, "prompt_tokens": None, "completion_tokens": None}),
            _result_with_usage({"backend": "ollama", "compute_seconds": 3.0, "prompt_tokens": None, "completion_tokens": None}),
        ]
        cost = _compute_inference_cost(results, price_per_1k_tokens=None)
        assert cost.unit == "cpu_gpu_seconds"
        assert cost.total == pytest.approx(4.0)
        assert cost.per_entity_average == pytest.approx(2.0)

    def test_bedrock_usage_requires_price(self):
        results = [
            _result_with_usage({"backend": "bedrock", "compute_seconds": None, "prompt_tokens": 100, "completion_tokens": 20}),
        ]
        with pytest.raises(ValueError):
            _compute_inference_cost(results, price_per_1k_tokens=None)

    def test_bedrock_usage_with_price_computes_usd(self):
        results = [
            _result_with_usage({"backend": "bedrock", "compute_seconds": None, "prompt_tokens": 500, "completion_tokens": 500}),
        ]
        cost = _compute_inference_cost(results, price_per_1k_tokens=2.0)
        assert cost.unit == "usd"
        assert cost.total == pytest.approx(2.0)  # 1000 tokens / 1000 * 2.0

    def test_mixed_backends_raises(self):
        results = [
            _result_with_usage({"backend": "ollama", "compute_seconds": 1.0, "prompt_tokens": None, "completion_tokens": None}),
            _result_with_usage({"backend": "bedrock", "compute_seconds": None, "prompt_tokens": 10, "completion_tokens": 5}),
        ]
        with pytest.raises(ValueError):
            _compute_inference_cost(results, price_per_1k_tokens=1.0)


# ---------------------------------------------------------------------------
# compute_metrics — orquestracao ponta a ponta com fixtures sinteticas
# ---------------------------------------------------------------------------


_SCHEMA = {
    "required": ["id", "type", "temperature"],
    "additionalProperties": True,
    "properties": {
        "id": {"type": "string"},
        "type": {"type": "string"},
        "temperature": {"type": "number"},
    },
}


class TestComputeMetrics:
    def test_end_to_end_with_synthetic_results(self):
        # Caso 1: violacao semantica esperada e detectada — cobre 3.1
        # (semantico), 3.2 (exclusiva do SLM), e uma Recommendation que
        # nao e' alucinada (patch resolve de verdade).
        semantic_violation = Violation(
            attribute_path="temperature", severity=ViolationSeverity.ERROR,
            rule="attribute_name_synonym", expected="temperature", found="temp",
            message="msg", detected_by=DetectionSource.SEMANTIC,
        )
        semantic_recommendation = Recommendation(
            attribute_path="temperature", action=RecommendationAction.RENAME_ATTRIBUTE,
            proposed_patch={"from": "temp", "to": "temperature"}, rationale="r", confidence=0.9,
        )
        case1 = DatasetCase(
            model_name="Streetlight", case_id="semantic-1",
            entity={"id": "urn:1", "type": "Streetlight", "temp": 21.5},
            expected_violations=(
                ExpectedViolation(
                    rule="attribute_name_synonym", attribute_path="temperature",
                    severity=ViolationSeverity.ERROR, detected_by=DetectionSource.SEMANTIC,
                ),
            ),
        )
        result1 = EntityResult(
            case=case1, violations=(semantic_violation,), recommendations=(semantic_recommendation,),
            processing_duration_seconds=2.0, semantic_analysis_usage={
                "backend": "ollama", "compute_seconds": 0.5, "prompt_tokens": None, "completion_tokens": None,
            },
            semantic_analysis_skipped=False,
        )

        # Caso 2: entidade conformante, so' Nivel 1 rodou de fato (nesse
        # exemplo simplificado nao passou pelo Nivel 2) — cobre a serie
        # "level1_only" de 3.3 e nao adiciona nenhuma recomendacao.
        case2 = DatasetCase(
            model_name="Streetlight", case_id="conformant-1",
            entity={"id": "urn:2", "type": "Streetlight", "temperature": 20.0},
            expected_violations=(),
        )
        result2 = EntityResult(
            case=case2, violations=(), recommendations=(), processing_duration_seconds=0.3,
            semantic_analysis_usage=None, semantic_analysis_skipped=True,
        )

        report = compute_metrics(
            [result1, result2],
            schema_by_type={"Streetlight": _SCHEMA},
            price_per_1k_tokens=None,
        )

        assert report.dataset_case_count == 2
        assert report.accuracy_semantic.true_positives == 1
        assert report.accuracy_semantic.false_negatives == 0
        assert report.accuracy_structural.true_positives == 0
        assert report.exclusive_slm_detection.value == pytest.approx(1.0)
        assert report.time_distribution["level1_only"].count == 1
        assert report.time_distribution["level1_and_level2"].count == 1
        assert report.inference_cost.unit == "cpu_gpu_seconds"
        assert report.hallucination.total == 1
        assert report.hallucination.hallucinated == 0
        assert report.hallucination_unscored_recommendations == 0

    def test_recommendation_without_matching_violation_is_unscored_not_penalized(self):
        orphan_recommendation = Recommendation(
            attribute_path="nonexistent", action=RecommendationAction.FIX_TYPE,
            proposed_patch={"value": 1}, rationale="r", confidence=0.5,
        )
        case = DatasetCase(
            model_name="Streetlight", case_id="c1",
            entity={"id": "urn:1", "type": "Streetlight"}, expected_violations=(),
        )
        result = EntityResult(
            case=case, violations=(), recommendations=(orphan_recommendation,),
            processing_duration_seconds=None, semantic_analysis_usage=None,
            semantic_analysis_skipped=False,
        )

        report = compute_metrics([result], schema_by_type={"Streetlight": _SCHEMA}, price_per_1k_tokens=None)

        assert report.hallucination.total == 0
        assert report.hallucination_unscored_recommendations == 1

    def test_hallucinated_recommendation_is_counted_with_reason(self):
        violation = Violation(
            attribute_path="temperature", severity=ViolationSeverity.ERROR,
            rule="required_property_missing", expected="temperature", found=None,
            message="msg", detected_by=DetectionSource.STRUCTURAL,
        )
        # patch que nao resolve nada (renomeia um atributo que nao existe)
        bad_recommendation = Recommendation(
            attribute_path="temperature", action=RecommendationAction.RENAME_ATTRIBUTE,
            proposed_patch={"from": "nonexistent_field", "to": "temperature"}, rationale="r", confidence=0.5,
        )
        case = DatasetCase(
            model_name="Streetlight", case_id="c1",
            entity={"id": "urn:1", "type": "Streetlight"}, expected_violations=(),
        )
        result = EntityResult(
            case=case, violations=(violation,), recommendations=(bad_recommendation,),
            processing_duration_seconds=None, semantic_analysis_usage=None,
            semantic_analysis_skipped=False,
        )

        report = compute_metrics([result], schema_by_type={"Streetlight": _SCHEMA}, price_per_1k_tokens=None)

        assert report.hallucination.total == 1
        assert report.hallucination.hallucinated == 1
        assert report.hallucination.by_reason[HallucinationReason.PATCH_DOES_NOT_RESOLVE] == 1


# ---------------------------------------------------------------------------
# Renderizacao do relatorio
# ---------------------------------------------------------------------------


class TestReportRendering:
    def test_json_report_has_expected_shape(self):
        report = compute_metrics([], schema_by_type={}, price_per_1k_tokens=None)
        payload = report_to_json(report)
        assert payload["dataset_case_count"] == 0
        assert payload["metrics"]["accuracy_structural"]["precision"] is None
        assert payload["metrics"]["inference_cost"] is None
        assert "by_reason" in payload["metrics"]["hallucination_rate"]

    def test_markdown_report_renders_na_for_missing_data(self):
        report = compute_metrics([], schema_by_type={}, price_per_1k_tokens=None)
        markdown = report_to_markdown(report)
        assert "N/A" in markdown
        assert "## 3.1 — Acuracia por nivel" in markdown
        assert "Sem dados (nenhuma entidade passou pelo Nivel 2)." in markdown


# ---------------------------------------------------------------------------
# Chamadas HTTP (Orion / API REST) — httpx.MockTransport, sem rede real
# ---------------------------------------------------------------------------


def _client_with_handler(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


class TestLoadEntitiesIntoOrion:
    @pytest.mark.asyncio
    async def test_posts_each_entity_with_upsert_and_tenant_headers(self):
        captured = []

        def handler(request: httpx.Request) -> httpx.Response:
            captured.append(request)
            return httpx.Response(204)

        cases = [
            DatasetCase(model_name="Streetlight", case_id="c1", entity={"id": "urn:1", "type": "Streetlight"}, expected_violations=()),
            DatasetCase(model_name="Streetlight", case_id="c2", entity={"id": "urn:2", "type": "Streetlight"}, expected_violations=()),
        ]
        client = _client_with_handler(handler)

        await load_entities_into_orion(cases, broker_url="http://orion:1026", tenant=_TENANT, client=client)

        assert len(captured) == 2
        assert all(r.url.path == "/v2/entities" for r in captured)
        assert all(r.url.params["options"] == "upsert" for r in captured)
        assert all(r.headers["fiware-service"] == "experiment" for r in captured)


class TestTriggerAudit:
    @pytest.mark.asyncio
    async def test_returns_run_id_from_response(self):
        expected_run_id = uuid4()

        def handler(request: httpx.Request) -> httpx.Response:
            assert json.loads(request.content) == {"entity_type": "Streetlight", "entity_id": None}
            return httpx.Response(202, json={"run_id": str(expected_run_id), "status": "queued"})

        client = _client_with_handler(handler)
        run_id = await trigger_audit(
            api_base_url="http://api:8000", tenant=_TENANT, entity_type="Streetlight", client=client
        )
        assert run_id == expected_run_id


class TestWaitForCompletion:
    @pytest.mark.asyncio
    async def test_returns_immediately_when_already_terminal(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"status": "completed", "processed": 2, "total": 2})

        client = _client_with_handler(handler)
        await wait_for_completion(
            api_base_url="http://api:8000", tenant=_TENANT, run_id=uuid4(), client=client,
            poll_interval_seconds=0.0, timeout_seconds=5.0,
        )  # nao levanta

    @pytest.mark.asyncio
    async def test_times_out_when_never_terminal(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"status": "running", "processed": 0, "total": 2})

        # clock/sleep fakes: cada "sleep" avanca o relogio fake em 1s, sem
        # esperar de verdade — o teste termina instantaneamente mas ainda
        # exercita o caminho de timeout real.
        fake_time = {"now": 0.0}

        def fake_clock() -> float:
            return fake_time["now"]

        async def fake_sleep(_seconds: float) -> None:
            fake_time["now"] += 1.0

        client = _client_with_handler(handler)
        with pytest.raises(TimeoutError):
            await wait_for_completion(
                api_base_url="http://api:8000", tenant=_TENANT, run_id=uuid4(), client=client,
                poll_interval_seconds=1.0, timeout_seconds=3.0,
                sleep=fake_sleep, clock=fake_clock,
            )


class TestFetchAuditRun:
    @pytest.mark.asyncio
    async def test_returns_parsed_json_body(self):
        run_id = uuid4()
        body = {"id": str(run_id), "status": "completed", "reports": []}

        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == f"/audits/{run_id}"
            return httpx.Response(200, json=body)

        client = _client_with_handler(handler)
        result = await fetch_audit_run(
            api_base_url="http://api:8000", tenant=_TENANT, run_id=run_id, client=client
        )
        assert result == body
