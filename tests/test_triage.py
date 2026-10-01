import inspect
import json
from pathlib import Path
import subprocess
import sys

import httpx
import pytest

from autoqe.adapters.rwa import RwaProjectAdapter
from autoqe.contracts import ExecutionRecord, TestSpec as Spec, TriageRecord
from autoqe.contracts.common import EvidenceReference
from autoqe.contracts.execution_record import ExecutionStatus, FailureCategory, ResultStatus
from autoqe.execution.api_provider import ApiExecutionProvider
from autoqe.execution.runtime import ExecutionSetupError
from autoqe.execution.service import execute_test_spec, _combine_records
from autoqe.triage import triage_execution
from test_execution import ROOT, load_profile, make_record


def spec():
    return Spec.model_validate_json((ROOT / "examples/rwa/execution/invalid-payment.json").read_text())


def observed_failure():
    test = spec()
    record = make_record(test, "httpx", ExecutionStatus.FAILED)
    record.environment_identity.update({key: "PASSED" for key in (
        "capability_status", "readiness_status", "reset_status", "fixture_status", "setup_status"
    )})
    record.assertion_results[0].status = ResultStatus.FAILED
    record.assertion_results[0].observed = "Expected no created transaction; observed two matching records after submission."
    record.assertion_results[0].evidence_refs = [EvidenceReference(kind="API_RESULT_METADATA", uri="reports/evidence/opaque.json", sha256="a" * 64)]
    return test, record


def test_product_defect_requires_supported_target_observation_and_evidence():
    test, record = observed_failure()
    triage = triage_execution(load_profile(), test, record)
    assert triage.classification == "PRODUCT_DEFECT"
    assert triage.expected_behavior_reference == test.expected_outcomes[0].outcome_id
    assert triage.supporting_evidence_refs
    assert "observed two" in triage.summary
    assert TriageRecord.model_validate_json(triage.model_dump_json()) == triage


@pytest.mark.parametrize("missing", ["capability_status", "readiness_status", "reset_status", "fixture_status", "setup_status", "observation", "reference", "hash", "submit"])
def test_insufficient_product_evidence_falls_back_to_unknown(missing):
    test, record = observed_failure()
    if missing in record.environment_identity:
        del record.environment_identity[missing]
    elif missing == "observation":
        record.assertion_results[0].observed = None
    elif missing == "reference":
        record.assertion_results[0].evidence_refs = []
    elif missing == "hash":
        record.assertion_results[0].evidence_refs[0].sha256 = None
    else:
        record.step_results = []
    assert triage_execution(load_profile(), test, record).classification == "UNKNOWN"


@pytest.mark.parametrize("category,stage,classification", [
    (FailureCategory.ENVIRONMENT_FAILURE, "readiness_status", "ENVIRONMENT_FAILURE"),
    (FailureCategory.DATA_FAILURE, "reset_status", "DATA_FAILURE"),
    (FailureCategory.DATA_FAILURE, "fixture_status", "DATA_FAILURE"),
])
def test_setup_failure_evidence_takes_precedence_over_assertion_failure(category, stage, classification):
    test, record = observed_failure()
    record.status = ExecutionStatus.ERROR
    record.failure_category = category
    record.environment_identity.update(setup_stage=stage, **{stage: "FAILED"})
    assert triage_execution(load_profile(), test, record).classification == classification


def test_category_label_alone_does_not_establish_environment_or_data_failure():
    test, record = observed_failure()
    for category in (FailureCategory.ENVIRONMENT_FAILURE, FailureCategory.DATA_FAILURE):
        record.status = ExecutionStatus.ERROR
        record.failure_category = category
        record.environment_identity = {}
        assert triage_execution(load_profile(), test, record).classification == "UNKNOWN"


def test_unsupported_semantics_are_qualified_without_accessing_target():
    test = spec()
    test.steps[-1].target = "unregistered behavior"
    record = execute_test_spec(test, load_profile(), RwaProjectAdapter(), ApiExecutionProvider(RwaProjectAdapter()))
    assert triage_execution(load_profile(), test, record).classification == "UNSUPPORTED_BEHAVIOR"


@pytest.mark.parametrize("inconsistency", ["identity", "expected", "duplicate", "false-pass", "missing-pass"])
def test_only_concrete_test_artifact_inconsistency_establishes_test_defect(inconsistency):
    test, record = observed_failure()
    if inconsistency == "identity":
        record.test_id = "different-test"
    elif inconsistency == "expected":
        record.assertion_results[0].expected = "Different expected behavior."
    elif inconsistency == "duplicate":
        record.assertion_results.append(record.assertion_results[0].model_copy())
    elif inconsistency == "false-pass":
        record.status = ExecutionStatus.PASSED
    else:
        record.status = ExecutionStatus.PASSED
        record.assertion_results = []
    assert triage_execution(load_profile(), test, record).classification == "TEST_DEFECT"


def test_locator_or_opaque_provider_error_is_not_inferred_as_test_defect():
    test, record = observed_failure()
    record.status = ExecutionStatus.ERROR
    record.failure_category = FailureCategory.PROVIDER_ERROR
    record.observed_outcomes = ["Browser locator timed out."]
    assert triage_execution(load_profile(), test, record).classification == "UNKNOWN"


def test_healthy_record_does_not_receive_a_product_defect_classification():
    test = spec()
    record = make_record(test, "httpx", ExecutionStatus.PASSED)
    result = triage_execution(load_profile(), test, record)
    assert result.classification == "UNKNOWN"
    assert "No behavioral failure" in result.summary


def test_both_product_evidence_requires_setup_for_every_provider():
    test, record = observed_failure()
    other = record.model_copy(deep=True)
    other.provider = "other"
    combined = _combine_records(test, load_profile(), [record, other], "seed")
    assert triage_execution(load_profile(), test, combined).classification == "PRODUCT_DEFECT"
    del combined.environment_identity["provider-2.reset_status"]
    assert triage_execution(load_profile(), test, combined).classification == "UNKNOWN"


@pytest.mark.parametrize("failure,expected", [(httpx.ConnectError("private diagnostic"), "ENVIRONMENT_FAILURE"), (RuntimeError("private diagnostic"), "DATA_FAILURE")])
def test_setup_normalizes_stage_and_never_persists_raw_exception(monkeypatch, failure, expected):
    adapter = RwaProjectAdapter()
    monkeypatch.setattr(adapter, "verify_reference_checkout", lambda _: {})
    monkeypatch.setattr(adapter, "verify_ready", lambda _: {})
    monkeypatch.setattr(adapter, "authenticate_if_needed", lambda _: {})
    def fail(_):
        raise failure
    monkeypatch.setattr(adapter, "reset_environment", fail)
    record = execute_test_spec(spec(), load_profile(), adapter, ApiExecutionProvider(adapter))
    assert record.environment_identity["reset_status"] == "FAILED"
    assert record.failure_category == expected
    assert "private diagnostic" not in record.model_dump_json()
    assert triage_execution(load_profile(), spec(), record).classification == expected


def test_reference_source_verification_does_not_inspect_deployed_source(monkeypatch, tmp_path):
    reference, runtime = tmp_path / "reference", tmp_path / "deployment"
    adapter = RwaProjectAdapter(runtime, reference_root=reference)
    calls = []
    def run(command, **kwargs):
        calls.append(command)
        return type("Result", (), {"stdout": "9dfcb9869533ce8a8963c556facc0d80457f9d39" if "rev-parse" in command else ""})()
    monkeypatch.setattr("autoqe.adapters.rwa.subprocess.run", run)
    adapter.verify_reference_checkout(load_profile())
    assert all(str(reference.resolve()) in command for command in calls)
    assert all(str(runtime.resolve()) not in command for command in calls)


def test_triage_boundary_is_artifacts_only_and_has_no_controller_imports(tmp_path):
    assert set(inspect.signature(triage_execution).parameters) == {"profile", "spec", "execution"}
    for path in (ROOT / "src").rglob("*.py"):
        content = path.read_text().lower()
        assert "from qualification" not in content and "import qualification" not in content
    completed = subprocess.run([sys.executable, str(ROOT / "scripts/triage_execution.py"), "--help"], capture_output=True, text=True)
    assert completed.returncode == 0
    for option in ("--fault-profile", "--known-defect", "--expected-classification"):
        assert option not in completed.stdout
    test, record = observed_failure()
    test_path, record_path, output = tmp_path / "test.json", tmp_path / "execution.json", tmp_path / "triage.json"
    test_path.write_text(test.model_dump_json())
    record_path.write_text(record.model_dump_json())
    result = subprocess.run([sys.executable, str(ROOT / "scripts/triage_execution.py"),
                             "--project-profile", str(ROOT / "examples/rwa/project-profile.json"),
                             "--test-spec", str(test_path), "--execution-record", str(record_path), "--output", str(output)], capture_output=True)
    assert result.returncode == 0
    assert TriageRecord.model_validate_json(output.read_text()).classification == "PRODUCT_DEFECT"


def test_frozen_m0_contracts_and_schemas_are_unchanged():
    result = subprocess.run(["git", "-c", f"safe.directory={ROOT.as_posix()}", "diff", "29eadfa", "--",
                             "src/autoqe/contracts", "src/autoqe/interfaces", "schemas"], cwd=ROOT, capture_output=True)
    assert result.returncode == 0 and result.stdout == b""
