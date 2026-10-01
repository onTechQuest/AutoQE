"""Generic/provider tests require neither an AgentGuard checkout nor runtime reports."""

import ast
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from autoqe_integration.contracts import (
    ExternalEvaluationRequest, ExternalEvaluationResult, ExternalEvaluationWindow,
    PlannedEvaluation, canonical_json, read_json,
)
from autoqe_integration.providers.agentguard.provider import AgentGuardEvaluationProvider, QUALIFIED_REVISION
from autoqe_integration.transport.local_process import LocalProcessTransport, TransportError
from qualification.m6.evidence import load_requests
from autoqe.metrics import MetricsEvidenceError, calculate_metrics, load_evidence

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "qualification/m6/fixtures"


@pytest.fixture
def requests():
    return load_requests(FIXTURES / "evidence.json", FIXTURES / "expectations.json")


def validate_request(raw):
    return ExternalEvaluationRequest.model_validate_json(canonical_json(raw))


def native(request, passed=None):
    passed = request.actual_value == request.expected_value if passed is None else passed
    return dict(scenario_id=str(request.evaluation_case_id), functional_pass=passed,
                tool_pass=True, argument_pass=True, overall_pass=passed,
                failures=[] if passed else ["Independent expected classification did not match"],
                factual_grounding_pass=None)


def make_result(request, status=None):
    passed = request.actual_value == request.expected_value
    status = status or ("COMPLETED_PASS" if passed else "COMPLETED_FAIL")
    complete = status.startswith("COMPLETED_")
    return ExternalEvaluationResult(
        request=request, request_sha256=request.sha256, provider_id="agentguard", provider_revision=QUALIFIED_REVISION,
        provider_version="1.0.0", status=status, attempted=status != "INCOMPLETE",
        passed=passed if complete else None, native_result=native(request) if complete else None,
        evaluated_dimensions=[request.evaluation_dimension] if complete else [], not_applicable=["tool_arguments"],
        errors=[] if complete else ["EVALUATOR_ERROR" if status == "ERROR" else "ENVIRONMENT_UNAVAILABLE"],
        limitations=["CLASSIFICATION_ONLY"],
    )


def metric(tmp_path, requests, results):
    window = ExternalEvaluationWindow(
        project_id=requests[0].project_id, window_id=requests[0].window_id, provider_id="agentguard",
        provider_revision=QUALIFIED_REVISION, evaluation_dimension=requests[0].evaluation_dimension,
        planned=[PlannedEvaluation(evaluation_case_id=r.evaluation_case_id, request_sha256=r.sha256,
                                   qualification_only=r.qualification_only) for r in requests],
    )
    manifest = dict(project_id=window.project_id, window_id=window.window_id, artifacts={},
                    external_evaluation_window=window.model_dump(mode="json"))
    for index, result in enumerate(results):
        filename = f"result-{index}.json"
        (tmp_path / filename).write_text(result.stable_json())
        manifest["artifacts"][f"result-{index}"] = dict(kind="external_evaluation", path=filename)
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest))
    report = calculate_metrics(load_evidence(path))
    return next(item for item in report.metrics if item.metric_id == "agentguard_pass_rate")


def test_neutral_schemas_and_stable_roundtrip(requests):
    for model, value in [(ExternalEvaluationRequest, requests[0]), (ExternalEvaluationResult, make_result(requests[0]))]:
        assert "agentguard" not in json.dumps(model.model_json_schema()).lower()
        assert model.model_validate_json(value.stable_json()).stable_json() == value.stable_json()
        raw = value.model_dump(mode="json")
        raw["schema_version"] = "999"
        with pytest.raises(ValidationError):
            model.model_validate_json(canonical_json(raw))


@pytest.mark.parametrize("field", ["actual_value", "expected_value"])
@pytest.mark.parametrize("value", ["", " PRODUCT_DEFECT", "PRODUCT_DEFECT ", "Product_defect", "It is PRODUCT_DEFECT",
                                  "PRODUCT_DEFECT DATA_FAILURE", "OTHER", None, 1, "UNKNOWN\n"])
def test_exact_classification_anti_vacuous_validation(requests, field, value):
    raw = requests[0].model_dump(mode="json")
    raw[field] = value
    with pytest.raises(ValidationError):
        validate_request(raw)


@pytest.mark.parametrize("field", ["expectation_provenance", "project_id", "evaluation_case_id"])
def test_required_independent_identity(requests, field):
    raw = requests[0].model_dump(mode="json")
    raw.pop(field)
    with pytest.raises(ValidationError):
        validate_request(raw)


@pytest.mark.parametrize("field", ["fault_profile_id", "patch_description", "password", "headers", "environment", "raw_payload"])
def test_export_allowlist_rejects_private_and_unknown_fields(requests, field):
    raw = requests[0].model_dump(mode="json")
    raw[field] = "not exported"
    with pytest.raises(ValidationError):
        validate_request(raw)


def test_lineage_is_preserved_without_whole_source_artifacts(requests):
    request = requests[0]
    result = make_result(request)
    assert result.request == request and result.request_sha256 == request.sha256
    assert {item.kind for item in request.source_artifacts} == {"contract", "spec", "execution", "triage"}
    assert request.lineage.requirement_ids and request.lineage.source_fingerprints
    text = request.stable_json()
    assert "reports/" not in text and "worktree" not in text and "environment_identity" not in text


def test_duplicate_json_fields_rejected():
    with pytest.raises(ValueError, match="duplicate"):
        read_json('{"field":1,"field":2}')


def test_duplicate_requests_rejected(tmp_path):
    raw = json.loads((FIXTURES / "evidence.json").read_text())
    raw["cases"].append(deepcopy(raw["cases"][0]))
    path = tmp_path / "evidence.json"
    path.write_text(json.dumps(raw))
    with pytest.raises(ValueError, match="invalid sanitized evidence"):
        load_requests(path, FIXTURES / "expectations.json")


def test_expectation_is_not_derived_from_actual(tmp_path):
    raw = json.loads((FIXTURES / "evidence.json").read_text())
    raw["cases"][0]["actual_value"] = "DATA_FAILURE"
    path = tmp_path / "evidence.json"
    path.write_text(json.dumps(raw))
    request = load_requests(path, FIXTURES / "expectations.json")[0]
    assert request.expected_value == "PRODUCT_DEFECT" and request.actual_value == "DATA_FAILURE"


@pytest.fixture
def provider(tmp_path, monkeypatch):
    executable = tmp_path / "separate-python.exe"
    executable.write_text("not executed")
    provider = AgentGuardEvaluationProvider(evaluator_root=tmp_path, python_executable=executable)
    monkeypatch.setattr(provider, "_revision", lambda: (QUALIFIED_REVISION, ""))
    return provider


def inject_response(provider, request, native_result=None):
    response = dict(request_sha256=request.sha256, revision=QUALIFIED_REVISION,
                    native_result=native_result if native_result is not None else native(request),
                    network_attempts=0, live_model_calls=0)
    captured = []

    class FakeTransport:
        def invoke(self, executable, worker, root, payload):
            captured.append((executable, worker, root, payload))
            return canonical_json(response).encode()

    provider.transport = FakeTransport()
    return captured


@pytest.mark.parametrize("actual,status", [("PRODUCT_DEFECT", "COMPLETED_PASS"), ("DATA_FAILURE", "COMPLETED_FAIL")])
def test_provider_controls_preserve_native_score(provider, requests, actual, status):
    request = next(r for r in requests if r.qualification_only and r.actual_value == actual)
    score = native(request)
    calls = inject_response(provider, request, score)
    result = provider.evaluate(request)
    assert result.status == status and result.native_result == score
    assert result.request == request and result.provider_revision == QUALIFIED_REVISION
    assert calls[0][3] == request.stable_json()
    assert "tool_arguments" in result.not_applicable


def test_revision_mismatch_is_unattempted_incomplete(provider, monkeypatch, requests):
    monkeypatch.setattr(provider, "_revision", lambda: ("b" * 40, ""))
    result = provider.evaluate(requests[0])
    assert result.status == "INCOMPLETE" and result.passed is None and not result.attempted
    assert result.provider_revision == "b" * 40 and result.errors == ["REVISION_MISMATCH"]


def test_dirty_evaluator_not_used(provider, monkeypatch, requests):
    monkeypatch.setattr(provider, "_revision", lambda: (QUALIFIED_REVISION, " M source.py"))
    assert provider.evaluate(requests[0]).errors == ["DIRTY_EVALUATOR"]


def test_missing_environment_is_incomplete(tmp_path, requests):
    provider = AgentGuardEvaluationProvider(evaluator_root=tmp_path, python_executable=tmp_path / "missing")
    assert provider.evaluate(requests[0]).status == "INCOMPLETE"


def test_same_python_environment_rejected(tmp_path, requests):
    provider = AgentGuardEvaluationProvider(evaluator_root=tmp_path, python_executable=Path(sys.executable))
    assert provider.evaluate(requests[0]).errors == ["ENVIRONMENT_UNAVAILABLE"]


@pytest.mark.parametrize("code", ["TIMEOUT", "EVALUATOR_ERROR", "INVALID_RESPONSE"])
def test_transport_failure_is_error_not_failed_classification(provider, requests, code):
    class FailedTransport:
        def invoke(self, *args):
            raise TransportError(code)
    provider.transport = FailedTransport()
    result = provider.evaluate(requests[0])
    assert result.status == "ERROR" and result.passed is None and result.native_result is None
    assert result.errors == [code] and result.attempted


def test_invalid_native_result_rejected(provider, requests):
    score = native(requests[0])
    score["scenario_id"] = "wrong"
    inject_response(provider, requests[0], score)
    assert provider.evaluate(requests[0]).errors == ["INVALID_RESPONSE"]


def test_shell_free_transport_and_clean_environment(monkeypatch, tmp_path):
    captured = {}
    monkeypatch.setenv("RWA_TEST_PASSWORD", "unit-test-sensitive-value")
    monkeypatch.setenv("OPENAI_API_KEY", "unit-test-sensitive-value")
    monkeypatch.setenv("PYTHONPATH", "injected-module-path")

    def run(command, **kwargs):
        captured.update(command=command, **kwargs)
        return SimpleNamespace(returncode=0, stdout=b"{}", stderr=b"")

    monkeypatch.setattr(subprocess, "run", run)
    LocalProcessTransport().invoke(tmp_path / "python.exe", tmp_path / "worker.py", tmp_path, "{}")
    assert captured["shell"] is False and isinstance(captured["command"], list)
    assert "-I" in captured["command"] and "-B" in captured["command"]
    assert captured["timeout"] <= 60
    assert not {"RWA_TEST_PASSWORD", "OPENAI_API_KEY", "PYTHONPATH"} & captured["env"].keys()


def test_transport_timeout(monkeypatch, tmp_path):
    def run(*args, **kwargs):
        raise subprocess.TimeoutExpired("worker", 1)
    monkeypatch.setattr(subprocess, "run", run)
    with pytest.raises(TransportError, match="TIMEOUT"):
        LocalProcessTransport(timeout_seconds=1).invoke(tmp_path / "python", tmp_path / "worker", tmp_path, "{}")


@pytest.mark.parametrize("code,stdout,stderr", [(2, b"", b"private evaluator message"), (0, b"x" * 100, b""), (0, b"{}", b"unexpected")])
def test_transport_does_not_forward_worker_diagnostics(monkeypatch, tmp_path, code, stdout, stderr):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=code, stdout=stdout, stderr=stderr))
    with pytest.raises(TransportError) as error:
        LocalProcessTransport(max_bytes=50).invoke(tmp_path / "python", tmp_path / "worker", tmp_path, "{}")
    assert "private evaluator message" not in str(error.value)


def test_complete_real_window_and_control_exclusion(tmp_path, requests):
    results = [make_result(r) for r in requests]
    report = metric(tmp_path, requests, results)
    real = [r for r in requests if not r.qualification_only]
    assert report.availability == "AVAILABLE" and report.value == 1
    assert report.numerator == report.denominator == len(real)
    assert report.details["excluded_controls"] == len(requests) - len(real)
    assert report.details["attempted"] == len(real)


def test_real_failure_in_denominator(tmp_path, requests):
    raw = requests[0].model_dump(mode="json")
    raw["actual_value"] = "DATA_FAILURE"
    requests[0] = validate_request(raw)
    report = metric(tmp_path, requests, [make_result(r) for r in requests])
    assert report.availability == "AVAILABLE" and report.details["failed"] == 1
    assert report.numerator == report.denominator - 1


@pytest.mark.parametrize("status", ["ERROR", "INCOMPLETE", "MISSING"])
def test_incomplete_window_is_unavailable(tmp_path, requests, status):
    results = [make_result(r) for r in requests[1:]]
    if status != "MISSING":
        results.append(make_result(requests[0], status))
    report = metric(tmp_path, requests, results)
    assert report.availability == "UNAVAILABLE" and report.value is None
    assert report.details["completed"] == report.details["planned"] - 1


def test_duplicate_results_rejected(tmp_path, requests):
    results = [make_result(r) for r in requests]
    with pytest.raises(MetricsEvidenceError, match="duplicate external"):
        metric(tmp_path, requests, results + [results[0]])


def test_mismatched_result_request_hash_rejected(requests):
    raw = make_result(requests[0]).model_dump(mode="json")
    raw["request_sha256"] = "f" * 64
    with pytest.raises(ValidationError):
        ExternalEvaluationResult.model_validate_json(canonical_json(raw))


def test_metrics_import_contracts_only_and_no_runtime_feedback():
    for path in (ROOT / "src/autoqe").rglob("*.py"):
        tree = ast.parse(path.read_text())
        imports = [node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
        imports += [alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names]
        assert not any(name.startswith(("src.agentguard", "autoqe_integration.providers", "autoqe_integration.transport")) for name in imports)
        if "metrics" not in path.parts:
            assert not any(name.startswith(("autoqe.metrics", "autoqe_integration")) for name in imports)


def test_worker_has_no_live_or_autoe_runtime_imports():
    path = ROOT / "autoqe_integration/providers/agentguard/worker.py"
    tree = ast.parse(path.read_text())
    imports = [node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
    assert "src.agentguard.scoring" in imports
    assert not any(name == "autoqe" or name.startswith(("autoqe.", "src.agentguard.semantic_evaluator", "src.agentguard.evaluation_record", "agents", "deepeval")) for name in imports)
    text = path.read_text()
    assert "OfflineImports" in text and "deny_network" in text


def test_fixtures_do_not_export_m4_profile_identity():
    profiles = json.loads((ROOT / "qualification/m4/profiles.json").read_text())["profiles"]
    exported = (FIXTURES / "evidence.json").read_text() + (FIXTURES / "expectations.json").read_text()
    for item in profiles:
        assert item["id"] not in exported and item["file"] not in exported
    assert "RWA_TEST_PASSWORD" not in exported


def test_control_artifact_fingerprints(requests):
    for request in requests:
        if request.qualification_only:
            name = "positive" if request.actual_value == "PRODUCT_DEFECT" else "negative"
            content = (FIXTURES / f"{name}-control-triage.json").read_bytes()
            assert hashlib.sha256(content).hexdigest() == request.source_artifacts[0].sha256


def test_provider_neutral_revision_does_not_require_git(requests):
    raw = make_result(requests[0]).model_dump(mode="json")
    raw.update(provider_id="enterprise-evaluator", provider_revision="deployment-2026.10")
    result = ExternalEvaluationResult.model_validate_json(canonical_json(raw))
    assert result.provider_revision == "deployment-2026.10"


def test_missing_referenced_result_file_keeps_window_unavailable(tmp_path, requests):
    metric(tmp_path, requests, [make_result(r) for r in requests])
    (tmp_path / "result-0.json").unlink()
    report = calculate_metrics(load_evidence(tmp_path / "manifest.json"))
    metric_result = next(item for item in report.metrics if item.metric_id == "agentguard_pass_rate")
    assert metric_result.availability == "UNAVAILABLE" and metric_result.details["missing"] == 1


def test_duplicate_plan_rejected(requests):
    request = requests[0]
    planned = PlannedEvaluation(evaluation_case_id=request.evaluation_case_id, request_sha256=request.sha256, qualification_only=False)
    with pytest.raises(ValidationError):
        ExternalEvaluationWindow(project_id=request.project_id, window_id=request.window_id, provider_id="example",
                                 provider_revision="release-1", evaluation_dimension=request.evaluation_dimension,
                                 planned=[planned, planned])


@pytest.mark.parametrize("field,value", [("passed", False), ("attempted", False), ("native_result", None), ("provider_revision", None)])
def test_completed_result_cannot_claim_missing_or_contradictory_evidence(requests, field, value):
    raw = make_result(requests[0]).model_dump(mode="json")
    raw[field] = value
    with pytest.raises(ValidationError):
        ExternalEvaluationResult.model_validate_json(canonical_json(raw))


def test_empty_real_population_is_unavailable(tmp_path, requests):
    controls = [r for r in requests if r.qualification_only]
    report = metric(tmp_path, controls, [make_result(r) for r in controls])
    assert report.availability == "UNAVAILABLE" and report.denominator == 0


def test_control_errors_do_not_pollute_real_metric(tmp_path, requests):
    results = [make_result(r, "ERROR") if r.qualification_only else make_result(r) for r in requests]
    report = metric(tmp_path, requests, results)
    assert report.availability == "AVAILABLE" and report.value == 1
    assert report.details["error"] == 0


def test_no_hidden_fault_id_in_provider_serialization(provider, requests):
    request = requests[0]
    calls = inject_response(provider, request)
    provider.evaluate(request)
    payload = calls[0][3]
    profiles = json.loads((ROOT / "qualification/m4/profiles.json").read_text())["profiles"]
    assert all(profile["id"] not in payload and profile["after"] not in payload for profile in profiles)


def test_dependency_and_runtime_boundaries_are_explicit():
    import tomllib
    config = tomllib.loads((ROOT / "pyproject.toml").read_text())
    assert all("agentguard" not in dependency.lower() for dependency in config["project"]["dependencies"])
    assert not any("autoqe" in str(node.module) for node in ast.walk(ast.parse(
        (ROOT / "autoqe_integration/contracts/__init__.py").read_text())) if isinstance(node, ast.ImportFrom))


def test_native_score_error_messages_are_not_invented_by_provider(provider, requests):
    request = next(r for r in requests if r.qualification_only and r.actual_value == "DATA_FAILURE")
    score = native(request)
    score["failures"] = ["Missing expected output 'PRODUCT_DEFECT'; actual: 'DATA_FAILURE'"]
    inject_response(provider, request, score)
    assert provider.evaluate(request).native_result == score


def test_generic_classification_values_match_frozen_contract():
    from typing import get_args
    from autoqe_integration.contracts import Classification
    from autoqe.contracts.triage_record import TriageClassification
    assert set(get_args(Classification)) == {item.value for item in TriageClassification}


def test_secure_api_is_documentation_only():
    documentation = (ROOT / "docs/M6_EXTERNAL_EVALUATION.md").read_text()
    assert "NOT IMPLEMENTED" in documentation and "OAuth2/OIDC" in documentation
    assert "autoqe.evaluations.submit" in documentation
    for path in (ROOT / "autoqe_integration").rglob("*.py"):
        tree = ast.parse(path.read_text())
        imports = [node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
        imports += [alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names]
        assert not any(name.startswith(("fastapi", "flask", "uvicorn", "http.server")) for name in imports)


def test_control_expectations_have_reproducible_source_hashes(requests):
    sha = hashlib.sha256((FIXTURES / "control-expectation.json").read_bytes()).hexdigest()
    assert all(request.expectation_provenance.source_sha256 == sha for request in requests if request.qualification_only)
