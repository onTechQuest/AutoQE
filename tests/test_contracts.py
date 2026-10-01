import ast
import json
from pathlib import Path
import tomllib

import pytest
from pydantic import ValidationError

from autoqe.contracts import (
    BehavioralContract,
    ExecutionRecord,
    ProjectProfile,
    TestSpec as AutoQETestSpec,
    TriageRecord,
)
from autoqe.contracts.common import Availability, ProvenanceModel
from autoqe.contracts.execution_record import ExecutionStatus, FailureCategory
from autoqe.contracts.project_profile import NetworkScope
from autoqe.contracts.test_spec import ScenarioType as AutoQEScenarioType
from autoqe.contracts.test_spec import TestLayer as AutoQETestLayer
from autoqe.contracts.triage_record import TriageClassification

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "examples" / "rwa"


def load_fixture(name: str) -> dict[str, object]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_rwa_project_profile_is_local_and_pinned() -> None:
    profile = ProjectProfile.model_validate(load_fixture("project-profile.json"))
    assert profile.environment.network_scope == NetworkScope.LOCAL_ONLY
    assert profile.reference_target is not None
    assert profile.reference_target.revision == "9dfcb9869533ce8a8963c556facc0d80457f9d39"
    assert profile.runtime.language_version_qualified == "22.23.3"


def test_local_only_profile_rejects_non_loopback_urls() -> None:
    data = load_fixture("project-profile.json")
    data["application"]["ui_base_url"] = "http://192.168.1.10:3000"
    with pytest.raises(ValidationError, match="LOCAL_ONLY"):
        ProjectProfile.model_validate(data)


def test_profile_rejects_invalid_urls_and_reset_configuration() -> None:
    data = load_fixture("project-profile.json")
    data["application"]["ui_base_url"] = "not a URL"
    with pytest.raises(ValidationError):
        ProjectProfile.model_validate(data)

    data = load_fixture("project-profile.json")
    data["environment"]["reset_adapter"] = None
    with pytest.raises(ValidationError, match="reset_adapter"):
        ProjectProfile.model_validate(data)


def test_all_example_contracts_validate_and_trace() -> None:
    profile = ProjectProfile.model_validate(load_fixture("project-profile.json"))
    behavior = BehavioralContract.model_validate(load_fixture("behavioral-contract.json"))
    test_spec = AutoQETestSpec.model_validate(load_fixture("test-spec.json"))
    execution = ExecutionRecord.model_validate(load_fixture("execution-record.json"))
    triage = TriageRecord.model_validate(load_fixture("triage-record.json"))

    assert behavior.project_id == test_spec.project_id == execution.project_id == profile.project_id
    assert behavior.contract_id == test_spec.contract_id
    assert behavior.requirement_ids == test_spec.requirement_ids
    assert test_spec.test_id == execution.test_id == triage.test_id
    assert execution.execution_id == triage.execution_id
    assert execution.status == ExecutionStatus.FAILED
    assert execution.failure_category == FailureCategory.ASSERTION_FAILURE
    assert triage.classification == TriageClassification.UNKNOWN
    assert all(step.target for step in test_spec.steps)


def test_test_spec_is_vendor_neutral_and_rejects_unknown_enums() -> None:
    data = load_fixture("test-spec.json")
    assert data["test_layer"] == AutoQETestLayer.UI.value
    assert data["scenario_type"] == AutoQEScenarioType.STATE_TRANSITION.value
    data["test_layer"] = "CYPRESS"
    with pytest.raises(ValidationError):
        AutoQETestSpec.model_validate(data)

    data = load_fixture("test-spec.json")
    data["generated_python"] = "print('not allowed')"
    with pytest.raises(ValidationError):
        AutoQETestSpec.model_validate(data)


def test_execution_and_triage_unknown_states_are_preserved() -> None:
    spec_data = load_fixture("test-spec.json")
    spec_data["evidence_requirements"][0]["availability"] = Availability.UNKNOWN.value
    spec = AutoQETestSpec.model_validate(spec_data)
    assert spec.evidence_requirements[0].availability == Availability.UNKNOWN

    triage_data = load_fixture("triage-record.json")
    triage_data["classification"] = "UNKNOWN"
    triage = TriageRecord.model_validate(triage_data)
    assert triage.classification == TriageClassification.UNKNOWN


def test_schema_version_rejects_unsupported_versions() -> None:
    with pytest.raises(ValidationError):
        ProvenanceModel.model_validate({"schema_version": "2.0"})


@pytest.mark.parametrize(
    "sensitive_payload",
    [
        {"api_key": "sentinel-secret"},
        {"nested": {"password": "sentinel-secret"}},
        {"headers": {"Authorization": "sentinel-secret"}},
        {"response_body": "private customer response"},
        {"summary": "credential sk-123456789abcdef"},
    ],
)
def test_sensitive_fields_and_credential_sentinels_are_rejected(
    sensitive_payload: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        TriageRecord.model_validate(
            {
                "triage_id": "triage-secret-test",
                "execution_id": "execution-secret-test",
                "test_id": "test-secret-test",
                "classification": "UNKNOWN",
                "summary": "No root cause assigned.",
                "recommended_next_action": "Collect sanitized evidence.",
                **sensitive_payload,
            }
        )


def test_json_round_trip_and_schema_generation() -> None:
    profile = ProjectProfile.model_validate(load_fixture("project-profile.json"))
    restored = ProjectProfile.model_validate_json(profile.model_dump_json())
    assert restored == profile
    schema = ProjectProfile.model_json_schema(mode="serialization")
    assert schema["properties"]["schema_version"]["default"] == "1.0"
    assert schema["properties"]["project_id"]["pattern"]


def test_checked_in_schemas_are_versioned_and_closed() -> None:
    schema_names = (
        "project-profile",
        "behavioral-contract",
        "test-spec",
        "execution-record",
        "triage-record",
    )
    for name in schema_names:
        schema = json.loads((ROOT / "schemas" / f"{name}.schema.json").read_text(encoding="utf-8"))
        assert schema["properties"]["schema_version"]["const"] == "1.0"
        assert schema["additionalProperties"] is False


def test_agentguard_is_not_imported_as_an_autoe_core_dependency() -> None:
    source_files = list((ROOT / "src").rglob("*.py"))
    assert source_files
    # Reporting an unavailable metric may name the external evaluator. Enforce
    # the dependency boundary, not a ban on descriptive strings and comments.
    for path in source_files:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.append(node.module or "")
            elif isinstance(node, ast.Call) and node.args:
                name = getattr(node.func, "id", getattr(node.func, "attr", ""))
                if name in ("__import__", "import_module") and isinstance(node.args[0], ast.Constant):
                    imports.append(str(node.args[0].value))
        assert not any("agentguard" in name.lower().replace("_", "") for name in imports), path
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    dependencies = project.get("dependencies", [])
    dependencies += [item for group in project.get("optional-dependencies", {}).values() for item in group]
    assert not any("agentguard" in name.lower().replace("-", "").replace("_", "") for name in dependencies)
