import hashlib
import json
from pathlib import Path
import re
import tomllib

from autoqe import __version__
from autoqe.contracts import BehavioralContract, ExecutionRecord, ProjectProfile, TestSpec as Spec, TriageRecord
from autoqe.metrics.models import QualityMetricsReport
from autoqe.triage import triage_execution
from autoqe_integration.contracts import ExternalEvaluationResult


ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "examples/demo"


def read(name):
    return json.loads((DEMO / name).read_text(encoding="utf-8"))


def test_demo_models_and_linkage():
    profile = ProjectProfile.model_validate(read("02-project-profile.json"))
    contract = BehavioralContract.model_validate(read("03-behavioral-contract.json"))
    specs = [Spec.model_validate(item) for item in read("04-testspecs.json")]
    execution = ExecutionRecord.model_validate(read("05-execution-record.json"))
    triage = TriageRecord.model_validate(read("06-triage-record.json"))
    metrics = QualityMetricsReport.model_validate(read("07-quality-metrics.json"))
    result = ExternalEvaluationResult.model_validate_json((DEMO / "08-external-evaluation.json").read_text())
    spec = next(item for item in specs if item.test_id == execution.test_id)
    assert profile.project_id == contract.project_id == spec.project_id == execution.project_id == metrics.project_id
    assert contract.contract_id == spec.contract_id
    assert triage.execution_id == execution.execution_id
    assert triage.classification == "PRODUCT_DEFECT" and execution.status == "FAILED"
    assert triage_execution(profile, spec, execution).classification == triage.classification
    assert {o.outcome_id for o in spec.expected_outcomes} == {a.assertion_id for a in execution.assertion_results}
    assert result.request.actual_value == triage.classification == result.request.expected_value
    assert result.request_sha256 == result.request.sha256
    assert any(item.artifact_id == execution.execution_id for item in result.request.source_artifacts)
    assert result.status == "COMPLETED_PASS"


def test_demo_provenance_and_evidence_hashes():
    provenance = read("provenance.json")
    for name, item in provenance["artifacts"].items():
        assert hashlib.sha256((DEMO / name).read_bytes()).hexdigest() == item["sha256"]
        assert item["label"] in {"illustrative input", "qualified example", "sanitized projection"}
    for name in ("05-execution-record.json", "06-triage-record.json"):
        data = read(name)
        refs = data.get("evidence_refs", data.get("supporting_evidence_refs"))
        assert refs and all(ref["kind"] != "SCREENSHOT" for ref in refs)
        for ref in refs:
            path = (ROOT / ref["uri"]).resolve()
            assert path.is_relative_to(DEMO.resolve())
            assert hashlib.sha256(path.read_bytes()).hexdigest() == ref["sha256"]


def test_demo_has_no_private_fields_paths_or_fault_identity():
    forbidden = {"password", "cookie", "cookies", "headers", "authorization", "access_token", "secret", "request_body", "response_body"}
    def check(value):
        if isinstance(value, dict):
            assert not forbidden.intersection(key.lower() for key in value)
            for child in value.values():
                check(child)
        elif isinstance(value, list):
            for child in value:
                check(child)
    faults = read_fault_ids()
    for path in DEMO.rglob("*.json"):
        text = path.read_text(encoding="utf-8")
        check(json.loads(text))
        assert not re.search(r"\b[A-Za-z]:[\\/]|/Users/|/home/", text)
        assert not any(fault in text for fault in faults)


def read_fault_ids():
    data = json.loads((ROOT / "qualification/m4/profiles.json").read_text())
    return [item["id"] for item in data["profiles"]]


def test_release_package_version_consistent():
    config = tomllib.loads((ROOT / "pyproject.toml").read_text())
    assert __version__ == config["project"]["version"] == "1.0.0"
