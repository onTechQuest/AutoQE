import ast
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest
from pydantic import ValidationError

from autoqe.metrics import MetricsEvidenceError, calculate_metrics, load_evidence
from autoqe.metrics.models import Metric, QualityMetricsReport

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def evidence(tmp_path):
    shutil.copytree(ROOT / "examples/metrics", tmp_path / "evidence")
    return tmp_path / "evidence/manifest.json"


def edit(path, change):
    value = json.loads(path.read_text())
    change(value)
    path.write_text(json.dumps(value), encoding="utf-8")


def result(path, key):
    return next(item for item in calculate_metrics(load_evidence(path)).metrics if item.metric_id == key)


def test_traceability_and_uncovered_ids(evidence):
    metric = result(evidence, "requirement_traceability")
    assert (metric.numerator, metric.denominator, metric.value) == (1, 2, 0.5)
    assert metric.details["uncovered_requirement_ids"] == ["REQ-DELETE"]


@pytest.mark.parametrize("raw", ["{", '{}', '[]', '{"password":"private fixture value"}'])
def test_invalid_specs_remain_visible_without_raw_values(evidence, raw):
    (evidence.parent / "bad.json").write_text(raw)
    edit(evidence, lambda m: m["artifacts"].update(bad={"kind": "spec", "path": "bad.json"}))
    metric = result(evidence, "testspec_schema_validity")
    assert (metric.numerator, metric.denominator) == (1, 2)
    assert "bad" in metric.details["invalid_inputs"]
    assert "private fixture value" not in calculate_metrics(load_evidence(evidence)).stable_json()


@pytest.mark.parametrize("status", ["PASSED", "FAILED"])
def test_passed_and_assertion_failed_are_executable(evidence, status):
    def update(record):
        record["status"] = status
        record["assertion_results"][0]["status"] = status
        record["failure_category"] = "ASSERTION_FAILURE" if status == "FAILED" else None
    edit(evidence.parent / "execution.json", update)
    assert result(evidence, "test_executability").value == 1


@pytest.mark.parametrize("status,category,assertion", [
    ("ERROR", "PROVIDER_ERROR", "ERROR"), ("INCOMPLETE", None, "UNKNOWN"),
    ("SKIPPED", "UNSUPPORTED_BEHAVIOR", "SKIPPED"), ("PASSED", None, "UNKNOWN"),
])
def test_nonexecutability_exclusions(evidence, status, category, assertion):
    def update(record):
        record.update(status=status, failure_category=category)
        record["assertion_results"][0]["status"] = assertion
    edit(evidence.parent / "execution.json", update)
    metric = result(evidence, "test_executability")
    assert metric.value == 0 and metric.details["exclusions"]


def healthy(path):
    edit(path, lambda m: m["cases"][0].update(target_state="HEALTHY", expected_classification="UNKNOWN"))


def test_healthy_false_positive(evidence):
    healthy(evidence)
    assert result(evidence, "healthy_false_positive_rate").value == 1


def test_environment_failure_excluded_from_healthy_rate(evidence):
    healthy(evidence)
    edit(evidence.parent / "execution.json", lambda r: r.update(status="ERROR", failure_category="ENVIRONMENT_FAILURE"))
    metric = result(evidence, "healthy_false_positive_rate")
    assert metric.denominator == 0 and metric.value is None
    assert metric.details["exclusions"]


def test_detected_controlled_fault(evidence):
    metric = result(evidence, "controlled_defect_detection")
    assert (metric.numerator, metric.denominator) == (1, 1)
    assert metric.details["missed_faults"] == []


def test_detection_and_assertion_completeness_are_distinct(evidence):
    edit(evidence.parent / "spec.json", lambda r: r["expected_outcomes"].append({"outcome_id": "second", "description": "Another outcome"}))
    assert result(evidence, "test_executability").value == 0
    assert result(evidence, "controlled_defect_detection").value == 1


@pytest.mark.parametrize("change", ["passed", "environment", "unreferenced", "unobserved"])
def test_missed_faults_not_detected_from_labels_alone(evidence, change):
    def update(record):
        if change == "passed":
            record.update(status="PASSED", failure_category=None)
            record["assertion_results"][0]["status"] = "PASSED"
        elif change == "environment":
            record.update(status="ERROR", failure_category="ENVIRONMENT_FAILURE")
        elif change == "unreferenced":
            record["assertion_results"][0]["evidence_refs"] = []
        else:
            record["assertion_results"][0]["observed"] = None
    edit(evidence.parent / "execution.json", update)
    metric = result(evidence, "controlled_defect_detection")
    assert metric.value == 0 and metric.details["missed_faults"] == ["save-fault"]


@pytest.mark.parametrize("classification,expected", [("PRODUCT_DEFECT", 1), ("UNKNOWN", 0)])
def test_triage_accuracy_support_and_confusion(evidence, classification, expected):
    edit(evidence.parent / "triage.json", lambda r: r.update(classification=classification))
    metric = result(evidence, "triage_accuracy")
    assert metric.value == expected
    assert metric.details["per_class_support"] == {"PRODUCT_DEFECT": 1}
    assert metric.details["confusion_counts"] == {"PRODUCT_DEFECT": {classification: 1}}
    assert metric.details["incorrect"] == 1 - expected


def test_failed_product_task_is_complete(evidence):
    assert result(evidence, "task_completion").value == 1


def test_missing_stage_is_incomplete_but_missing_file_is_error(evidence):
    edit(evidence, lambda m: m["cases"][0].update(triage=None))
    metric = result(evidence, "task_completion")
    assert metric.value == 0 and metric.details["stage_incomplete_counts"] == {"triage": 1}
    assert result(evidence, "triage_accuracy").value == 0
    edit(evidence, lambda m: m["artifacts"]["triage"].update(path="missing.json"))
    with pytest.raises(MetricsEvidenceError, match="missing referenced artifact"):
        load_evidence(evidence)


def test_zero_usage_and_missing_telemetry_are_distinct(evidence):
    assert result(evidence, "ai_token_usage").value == 0
    edit(evidence, lambda m: m["artifacts"].pop("usage"))
    metric = result(evidence, "ai_token_usage")
    assert metric.value is None and metric.availability == "UNAVAILABLE"


def test_actual_usage_telemetry(evidence):
    edit(evidence.parent / "usage.json", lambda r: r.update(mode="TELEMETRY", live_model_calls=2, live_model_tokens=123, replay_or_deterministic_only=False))
    edit(evidence.parent / "qualification.json", lambda r: r.update(live_model_calls=2, live_model_tokens=123))
    edit(evidence, lambda m: m.update(checks=[]))
    metric = result(evidence, "ai_token_usage")
    assert metric.value == 123 and metric.sample_size == 2


def test_agentguard_without_external_evidence_is_unavailable(evidence):
    metric = result(evidence, "agentguard_pass_rate")
    assert metric.availability == "UNAVAILABLE" and metric.value is None
    assert "M6" in metric.limitations[0]


def test_empty_window_zero_denominators(evidence):
    evidence.write_text('{"project_id":"empty","window_id":"empty"}')
    metrics = calculate_metrics(load_evidence(evidence)).metrics
    assert all(item.value is None for item in metrics)
    assert all(item.limitations for item in metrics)


def test_duplicate_cases_rejected(evidence):
    edit(evidence, lambda m: m["cases"].append(m["cases"][0]))
    with pytest.raises(MetricsEvidenceError, match="duplicate qualification"):
        load_evidence(evidence)


@pytest.mark.parametrize("filename", ["contract.json", "spec.json", "execution.json", "usage.json"])
def test_mixed_projects_rejected_even_invalid_specs(evidence, filename):
    edit(evidence.parent / filename, lambda m: m.update(project_id="another-project"))
    with pytest.raises(MetricsEvidenceError, match="mixed project"):
        load_evidence(evidence)


@pytest.mark.parametrize("filename", ["contract.json", "execution.json", "triage.json", "usage.json"])
def test_other_invalid_schemas_fail_closed(evidence, filename):
    edit(evidence.parent / filename, lambda m: m.update(unexpected="field"))
    with pytest.raises(MetricsEvidenceError, match="invalid artifact schema"):
        load_evidence(evidence)


def test_report_is_deterministic_across_loads(evidence):
    first = calculate_metrics(load_evidence(evidence)).stable_json()
    second = calculate_metrics(load_evidence(evidence)).stable_json()
    assert first == second
    assert QualityMetricsReport.model_validate_json(first).stable_json() == first


def test_unsupported_versions_rejected(evidence):
    report = calculate_metrics(load_evidence(evidence)).model_dump()
    report["schema_version"] = "999"
    with pytest.raises(ValidationError):
        QualityMetricsReport.model_validate(report)
    edit(evidence, lambda m: m.update(schema_version="999"))
    with pytest.raises(MetricsEvidenceError):
        load_evidence(evidence)


def test_inconsistent_ratio_rejected():
    with pytest.raises(ValidationError):
        Metric(metric_id="bad", definition="bad", numerator=2, denominator=1, value=2, sample_size=1, availability="AVAILABLE")


def test_contradictory_qualification_labels_rejected(evidence):
    edit(evidence, lambda m: m["cases"][0].update(target_state="HEALTHY"))
    with pytest.raises(MetricsEvidenceError):
        load_evidence(evidence)


def test_explicit_external_evidence_checks(evidence):
    edit(evidence, lambda m: m["checks"][0].update(expected=1))
    with pytest.raises(MetricsEvidenceError, match="contradictory external evidence"):
        load_evidence(evidence)


def test_no_reverse_dependency_or_runtime_invocation():
    for path in (ROOT / "src/autoqe").rglob("*.py"):
        tree = ast.parse(path.read_text())
        imports = [node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
        imports += [alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names]
        if "metrics" not in path.parts:
            assert not any(name.startswith("autoqe.metrics") for name in imports), path
        else:
            assert not any(name.startswith(("autoqe.execution", "autoqe.triage", "autoqe.planning", "autoqe.adapters", "qualification")) for name in imports), path


def test_cli_from_committed_evidence_without_runtime_reports(evidence, tmp_path):
    run = subprocess.run([sys.executable, str(ROOT / "scripts/report_quality_metrics.py"), "--evidence-manifest", str(evidence), "--output", str(tmp_path / "output")], capture_output=True, text=True)
    assert run.returncode == 0, run.stderr
    assert "agentguard_pass_rate: UNAVAILABLE" in run.stdout
    assert (tmp_path / "output/quality-metrics.json").exists()


def test_frozen_m0_tree_matches_pre_m5_checkpoint():
    digest = hashlib.sha256()
    files = sorted(path for folder in ("src/autoqe/contracts", "src/autoqe/interfaces", "schemas")
                   for path in (ROOT / folder).rglob("*") if path.is_file() and "__pycache__" not in path.parts)
    for path in files:
        digest.update(path.relative_to(ROOT).as_posix().encode())
        digest.update(path.read_bytes().replace(b"\r\n", b"\n"))
    assert digest.hexdigest() == "bf3870d2c878328d4c4a5caaecc862e3d5d62a8741c121e09141b643625f81bd"


@pytest.mark.parametrize("change", ["missing", "duplicate", "different", "empty_steps", "setup_contradiction", "unfinished"])
def test_incomplete_execution_cannot_count_as_executable(evidence, change):
    def update(record):
        if change == "missing":
            record["assertion_results"] = []
        elif change == "duplicate":
            record["assertion_results"] *= 2
        elif change == "different":
            record["assertion_results"][0]["expected"] = "Another expectation"
        elif change == "empty_steps":
            record["step_results"] = []
        elif change == "setup_contradiction":
            record["environment_identity"]["reset_status"] = "FAILED"
        else:
            record["completed_at"] = None
    edit(evidence.parent / "execution.json", update)
    assert result(evidence, "test_executability").value == 0


def test_environment_failure_is_terminal_task_but_not_executable(evidence):
    edit(evidence.parent / "execution.json", lambda r: r.update(status="ERROR", failure_category="ENVIRONMENT_FAILURE"))
    assert result(evidence, "task_completion").value == 1
    assert result(evidence, "test_executability").value == 0


def test_incomplete_execution_task_is_not_complete(evidence):
    edit(evidence.parent / "execution.json", lambda r: r.update(status="INCOMPLETE"))
    assert result(evidence, "task_completion").details["stage_incomplete_counts"] == {"execution": 1}


def test_duplicate_runtime_execution_cannot_inflate_denominator(evidence):
    def update(manifest):
        duplicate = dict(manifest["cases"][0], case_id="duplicate")
        manifest["cases"].append(duplicate)
    edit(evidence, update)
    with pytest.raises(MetricsEvidenceError, match="duplicate runtime execution"):
        load_evidence(evidence)


@pytest.mark.parametrize("stage,field", [("spec", "contract_id"), ("execution", "test_id"), ("triage", "execution_id")])
def test_contradictory_artifact_linkage(evidence, stage, field):
    edit(evidence.parent / f"{stage}.json", lambda r: r.update({field: "another"}))
    with pytest.raises(MetricsEvidenceError, match="contradictory"):
        load_evidence(evidence)


def test_usage_requires_matching_source_telemetry(evidence):
    edit(evidence.parent / "usage.json", lambda r: r.update(mode="TELEMETRY", live_model_calls=1, live_model_tokens=123))
    with pytest.raises(MetricsEvidenceError, match="usage call count"):
        load_evidence(evidence)


def test_cli_error_does_not_echo_invalid_sensitive_input(evidence, tmp_path):
    edit(evidence.parent / "execution.json", lambda r: r.update(password="private fixture value"))
    run = subprocess.run([sys.executable, str(ROOT / "scripts/report_quality_metrics.py"), "--evidence-manifest", str(evidence), "--output", str(tmp_path / "output")], capture_output=True, text=True)
    assert run.returncode == 2
    assert "private fixture value" not in run.stderr
    assert not (tmp_path / "output").exists()
