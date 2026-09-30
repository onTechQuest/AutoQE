import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from autoqe.contracts import BehavioralContract, ProjectProfile
from autoqe.contracts.common import Availability, RiskLevel
from autoqe.contracts.project_profile import ExecutionCapabilities
from autoqe.contracts.test_spec import (
    ExpectedOutcome,
    ScenarioType,
    SemanticAction,
    SemanticStep,
    TestLayer as AutoQETestLayer,
    TestSpec as AutoQETestSpec,
)
from autoqe.extraction.service import extract_behavioral_contract
from autoqe.extraction.grounding import validate_contract_grounding
from autoqe.planning.coverage import CoveragePlanner
from autoqe.planning.layers import LayerSelector, UnsupportedLayerSelectionError
from autoqe.planning.models import PlannerConfig, RiskAssessment
from autoqe.planning.risk import RiskPlanner
from autoqe.planning.service import PLAN_TESTS_TASK, PlanningError, plan_tests
from autoqe.planning.validation import validate_test_specs
from autoqe.providers.replay import ReplayModelProvider
from autoqe.requirements.markdown import MarkdownRequirementProvider
from autoqe.context import ContextBundle

ROOT = Path(__file__).resolve().parents[1]
REPLAYS = ROOT / "examples/rwa/replays.json"


class DeterministicPlanningProvider:
    def generate_structured(self, task, context, output_schema):
        assert task == PLAN_TESTS_TASK
        assert output_schema["title"] == "PlanningResponse"
        scenarios = []
        for candidate in context["scenarios"]:
            scenario_type = candidate["scenario_type"]
            scenario_id = candidate["scenario_id"]
            actions = []
            if scenario_type in {"POSITIVE", "AUTHORIZATION"}:
                actions.append(SemanticAction.AUTHENTICATE.value)
            if scenario_type in {"POSITIVE", "NEGATIVE", "BOUNDARY", "STATE_TRANSITION"}:
                actions.append(SemanticAction.SUBMIT.value)
            if scenario_type == "STATE_TRANSITION":
                actions.append(SemanticAction.WAIT_FOR_STATE.value)
            actions.append(SemanticAction.ASSERT.value)
            scenarios.append(
                {
                    "scenario_id": scenario_id,
                    "steps": [
                        {
                            "step_id": f"{scenario_id}-step-{index}",
                            "action": action,
                            "target": "contract-backed outcome",
                        }
                        for index, action in enumerate(actions, start=1)
                    ],
                }
            )
        return {"schema_version": "1.0", "scenarios": scenarios}


def load_profile() -> ProjectProfile:
    return ProjectProfile.model_validate_json(
        (ROOT / "examples/rwa/project-profile.json").read_text(encoding="utf-8")
    )


def load_contract(requirement_name: str) -> BehavioralContract:
    profile = load_profile()
    source_provider = MarkdownRequirementProvider(profile, ROOT)
    source_path = ROOT / "examples/rwa/requirements" / requirement_name
    context = ContextBundle(
        project_id=profile.project_id,
        requirement_sources=source_provider.load([source_path]),
    )
    return extract_behavioral_contract(profile, context, ReplayModelProvider(REPLAYS))


def plan(requirement_name: str, config: PlannerConfig | None = None):
    return plan_tests(load_profile(), load_contract(requirement_name), DeterministicPlanningProvider(), config)


def test_risk_priority_preserves_declared_risk_and_records_factors() -> None:
    payment = load_contract("payments.md")
    assessment = RiskPlanner().analyze(payment)
    assert assessment.declared_risk == RiskLevel.HIGH
    assert assessment.test_priority == 2
    assert "financial/business transaction impact" in assessment.risk_factors
    assert "data integrity impact" in assessment.risk_factors
    assert "state-transition impact" in assessment.risk_factors
    assert "ambiguity/unknowns present" in assessment.risk_factors
    assert "without a probability estimate or override" in assessment.rationale


def test_payment_plan_covers_positive_negative_and_transition_with_layers() -> None:
    result = plan("payments.md")
    specs = {spec.scenario_type: spec for spec in result.test_specs}
    assert set(specs) == {
        ScenarioType.POSITIVE,
        ScenarioType.NEGATIVE,
        ScenarioType.STATE_TRANSITION,
    }
    assert specs[ScenarioType.POSITIVE].test_layer == AutoQETestLayer.BOTH
    assert specs[ScenarioType.NEGATIVE].test_layer == AutoQETestLayer.API
    assert specs[ScenarioType.STATE_TRANSITION].test_layer == AutoQETestLayer.BOTH
    assert all(spec.priority == 2 and spec.risk_level == RiskLevel.HIGH for spec in specs.values())
    assert result.summary.planning_validation_pass


def test_authorization_plan_covers_ownership_without_duplicate_scenarios() -> None:
    result = plan("authorization.md")
    assert len(result.test_specs) == len({spec.scenario_type for spec in result.test_specs})
    authorization = next(spec for spec in result.test_specs if spec.scenario_type == ScenarioType.AUTHORIZATION)
    assert authorization.test_layer == AutoQETestLayer.API
    assert any("account owner" in outcome.description for outcome in authorization.expected_outcomes)
    assert result.summary.authorization_constraints_covered == 1


def test_account_setup_preserves_unknowns_and_assumptions() -> None:
    result = plan("account-setup.md")
    assert result.test_specs
    assert result.summary.unknowns_preserved == [
        "Required account fields and account-number validation rules are not specified."
    ]
    assert all(
        "Unresolved contract unknown: Required account fields and account-number validation rules are not specified."
        in spec.limitations
        for spec in result.test_specs
    )
    assert result.summary.planning_limitations


def test_transaction_history_incomplete_requirement_is_not_filled_in() -> None:
    result = plan("transaction-history.md")
    assert result.test_specs[0].test_layer == AutoQETestLayer.UI
    assert result.summary.unknowns_preserved == [
        "Transaction ordering, retention duration, and pagination behavior are not specified."
    ]
    assert not any("ordering" in outcome.description.lower() for spec in result.test_specs for outcome in spec.expected_outcomes)


def test_explicit_boundary_condition_produces_boundary_testspec() -> None:
    contract = load_contract("payments.md")
    data = contract.model_dump(mode="python")
    data["business_conditions"] = ["The payment amount is at least 1 unit."]
    boundary_contract = BehavioralContract.model_validate(data)
    profile = load_profile()
    result = plan_tests(profile, boundary_contract, DeterministicPlanningProvider())
    boundary = next(spec for spec in result.test_specs if spec.scenario_type == ScenarioType.BOUNDARY)
    assert boundary.test_layer == AutoQETestLayer.API
    assert boundary.expected_outcomes == [
        ExpectedOutcome(outcome_id="condition-1", description="The payment amount is at least 1 unit.")
    ]


def test_layer_selector_supports_ui_api_both_and_capability_fallback() -> None:
    profile = load_profile()
    contract = load_contract("payments.md")
    risk = RiskPlanner().analyze(contract)
    candidates = CoveragePlanner().build(contract, risk, PlannerConfig())
    selected = {candidate.scenario_type: LayerSelector().select(profile, candidate, risk) for candidate in candidates}
    assert selected[ScenarioType.POSITIVE].test_layer == AutoQETestLayer.BOTH
    assert selected[ScenarioType.NEGATIVE].test_layer == AutoQETestLayer.API

    ui_only = profile.model_copy(
        update={
            "execution_capabilities": ExecutionCapabilities(ui=Availability.AVAILABLE, api=Availability.UNAVAILABLE)
        }
    )
    fallback = LayerSelector().select(ui_only, selected[ScenarioType.NEGATIVE], risk)
    assert fallback.test_layer == AutoQETestLayer.UI
    assert "API capability is unavailable" in fallback.layer_rationale

    no_layers = profile.model_copy(
        update={
            "execution_capabilities": ExecutionCapabilities(ui=Availability.UNAVAILABLE, api=Availability.UNKNOWN)
        }
    )
    with pytest.raises(UnsupportedLayerSelectionError):
        LayerSelector().select(no_layers, candidates[0], risk)


def test_priority_cap_bounds_specs_and_reports_omissions() -> None:
    result = plan("payments.md", PlannerConfig(max_tests=2))
    assert len(result.test_specs) == 2
    assert result.summary.testspec_count == 2
    assert any("omitted lower-priority" in limitation for limitation in result.summary.planning_limitations)


def test_planner_rejects_no_source_lineage_and_project_mismatch() -> None:
    profile = load_profile()
    contract = load_contract("payments.md")
    no_lineage = BehavioralContract.model_validate(
        {**contract.model_dump(mode="json"), "source_ids": [], "source_fingerprints": {}}
    )
    with pytest.raises(PlanningError, match="source IDs and SHA-256 fingerprints"):
        plan_tests(profile, no_lineage, DeterministicPlanningProvider())

    other_profile = profile.model_copy(update={"project_id": "other-project"})
    with pytest.raises(PlanningError, match="project IDs"):
        plan_tests(other_profile, contract, DeterministicPlanningProvider())


def test_test_spec_outcomes_cannot_be_invented_or_require_unsupported_layers() -> None:
    profile = load_profile()
    contract = load_contract("payments.md")
    result = plan_tests(profile, contract, DeterministicPlanningProvider())
    spec = result.test_specs[0]
    candidate = CoveragePlanner().build(contract, RiskPlanner().analyze(contract), PlannerConfig())
    layered = tuple(LayerSelector().select(profile, item, RiskPlanner().analyze(contract)) for item in candidate)
    invented = spec.model_copy(
        update={"expected_outcomes": [ExpectedOutcome(outcome_id="invented", description="Invented behavior.")]}
    )
    report = validate_test_specs(profile, contract, layered, (invented,), PlannerConfig())
    assert not report.planning_validation_pass
    assert any("not exactly contract-grounded" in error for error in report.errors)

    api_unavailable = profile.model_copy(
        update={
            "execution_capabilities": ExecutionCapabilities(ui=Availability.AVAILABLE, api=Availability.UNAVAILABLE)
        }
    )
    report = validate_test_specs(api_unavailable, contract, layered, (spec,), PlannerConfig())
    assert report.unsupported_layer_selections == 1
    assert not report.planning_validation_pass


def test_frozen_test_spec_json_round_trip_and_traceability() -> None:
    result = plan("payments.md")
    for spec in result.test_specs:
        restored = AutoQETestSpec.model_validate_json(spec.model_dump_json())
        assert restored == spec
        assert restored.contract_id == result.summary.contract_id
        assert restored.requirement_ids == ["REQ-PAY-001"]
        assert restored.source_ids == ["md-examples-rwa-requirements-payments"]


def test_duplicate_replay_scenarios_are_rejected() -> None:
    class DuplicateProvider:
        def generate_structured(self, task, context, output_schema):
            return {
                "schema_version": "1.0",
                "scenarios": [
                    {
                        "scenario_id": context["scenarios"][0]["scenario_id"],
                        "steps": [
                            {"step_id": "step-1", "action": "ASSERT", "target": "contract outcome"}
                        ],
                    },
                    {
                        "scenario_id": context["scenarios"][0]["scenario_id"],
                        "steps": [
                            {"step_id": "step-2", "action": "ASSERT", "target": "contract outcome"}
                        ],
                    },
                ],
            }

    with pytest.raises(PlanningError, match="exactly one entry"):
        plan_tests(load_profile(), load_contract("payments.md"), DuplicateProvider())


def test_executable_or_provider_specific_semantic_steps_are_rejected() -> None:
    class UnsafeProvider:
        def generate_structured(self, task, context, output_schema):
            return {
                "schema_version": "1.0",
                "scenarios": [
                    {
                        "scenario_id": scenario["scenario_id"],
                        "steps": [
                            {"step_id": "step-1", "action": "ASSERT", "target": "page.locator('[data-test=x]')"}
                        ],
                    }
                    for scenario in context["scenarios"]
                ],
            }

    with pytest.raises(Exception, match="provider-specific or executable"):
        plan_tests(load_profile(), load_contract("payments.md"), UnsafeProvider())


def test_invalid_enums_contract_ids_and_requirement_ids_are_rejected() -> None:
    with pytest.raises(ValidationError):
        SemanticStep(step_id="step-1", action="EXECUTE_PYTHON", target="script")
    contract_data = load_contract("payments.md").model_dump(mode="json")
    contract_data["contract_id"] = "not safe!"
    with pytest.raises(ValidationError):
        BehavioralContract.model_validate(contract_data)
    contract_data = load_contract("payments.md").model_dump(mode="json")
    contract_data["requirement_ids"] = ["invalid requirement id"]
    with pytest.raises(ValidationError):
        BehavioralContract.model_validate(contract_data)


def test_planning_context_excludes_raw_requirement_and_benchmark_inputs() -> None:
    seen_context = {}

    class InspectingProvider(DeterministicPlanningProvider):
        def generate_structured(self, task, context, output_schema):
            seen_context.update(context)
            return super().generate_structured(task, context, output_schema)

    plan_tests(load_profile(), load_contract("payments.md"), InspectingProvider())
    assert "requirement_sources" not in seen_context
    assert "cypress/tests" not in json.dumps(seen_context).lower()
    assert "fault-injection" not in json.dumps(seen_context).lower()
    assert "content_fingerprint" not in json.dumps(seen_context).lower()


def test_planner_imports_no_agentguard_or_execution_runtime() -> None:
    planner_files = list((ROOT / "src/autoqe/planning").rglob("*.py"))
    assert planner_files
    contents = [path.read_text(encoding="utf-8").lower() for path in planner_files]
    assert not any("agentguard" in text for text in contents)
    assert not any("import playwright" in text or "import httpx" in text for text in contents)


def test_changed_planning_configuration_has_no_approved_replay() -> None:
    contract = BehavioralContract.model_validate_json(
        (ROOT / "examples/rwa/plans/contracts/payment.json").read_text(encoding="utf-8")
    )
    with pytest.raises(Exception, match="no unique approved replay"):
        plan_tests(load_profile(), contract, ReplayModelProvider(REPLAYS), PlannerConfig(max_tests=2))


def test_planning_cli_writes_testspecs_and_summary(tmp_path) -> None:
    import subprocess
    import sys

    output = tmp_path / "plans"
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/plan_tests.py"),
            "--project-profile",
            "examples/rwa/project-profile.json",
            "--contract",
            "examples/rwa/plans/contracts/payment.json",
            "--provider",
            "replay",
            "--output",
            str(output),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)
    assert {item["test_layer"] for item in result["test_specs"]} == {"API", "BOTH"}
    assert len(result["spec_artifacts"]) == 3
    assert Path(result["summary_artifact"]).is_file()
    assert result["summary"]["planning_validation_pass"] is True


def test_live_planning_cli_fails_closed_without_loading_files(tmp_path) -> None:
    import subprocess
    import sys

    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/plan_tests.py"),
            "--project-profile",
            str(tmp_path / "missing-profile.json"),
            "--contract",
            str(tmp_path / "missing-contract.json"),
            "--provider",
            "live",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 2
    assert "not implemented in M2" in completed.stderr
    assert completed.stdout == ""


@pytest.mark.parametrize(
    ("contract_name", "requirement_name"),
    [
        ("payment.json", "payments.md"),
        ("authorization.json", "authorization.md"),
        ("account-setup.json", "account-setup.md"),
        ("incomplete-history.json", "transaction-history.md"),
    ],
)
def test_committed_planning_contracts_are_m1_grounded(contract_name: str, requirement_name: str) -> None:
    contract = BehavioralContract.model_validate_json(
        (ROOT / "examples/rwa/plans/contracts" / contract_name).read_text(encoding="utf-8")
    )
    profile = load_profile()
    source_provider = MarkdownRequirementProvider(profile, ROOT)
    context = ContextBundle(
        project_id=profile.project_id,
        requirement_sources=source_provider.load([ROOT / "examples/rwa/requirements" / requirement_name]),
    )
    assert validate_contract_grounding(profile, context, contract).grounding_validation_pass


@pytest.mark.parametrize(
    "contract_name",
    ["payment.json", "authorization.json", "account-setup.json", "incomplete-history.json"],
)
def test_approved_planning_replays_generate_valid_testspecs(contract_name: str) -> None:
    profile = load_profile()
    contract = BehavioralContract.model_validate_json(
        (ROOT / "examples/rwa/plans/contracts" / contract_name).read_text(encoding="utf-8")
    )
    result = plan_tests(profile, contract, ReplayModelProvider(REPLAYS))
    assert result.summary.planning_validation_pass
    assert len(result.test_specs) <= PlannerConfig().max_tests
    assert all(spec.contract_id == contract.contract_id for spec in result.test_specs)
    assert all(spec.source_fingerprints == contract.source_fingerprints for spec in result.test_specs)
    if contract_name == "incomplete-history.json":
        assert result.summary.unknowns_preserved == contract.unknowns
        assert not any("ordering" in outcome.description.lower() for spec in result.test_specs for outcome in spec.expected_outcomes)


def test_planning_replay_is_semantically_deterministic() -> None:
    profile = load_profile()
    contract = BehavioralContract.model_validate_json(
        (ROOT / "examples/rwa/plans/contracts/payment.json").read_text(encoding="utf-8")
    )
    first = plan_tests(profile, contract, ReplayModelProvider(REPLAYS))
    second = plan_tests(profile, contract, ReplayModelProvider(REPLAYS))
    assert [spec.record_id for spec in first.test_specs] == [spec.record_id for spec in second.test_specs]
    assert [spec.steps for spec in first.test_specs] == [spec.steps for spec in second.test_specs]
    assert [spec.expected_outcomes for spec in first.test_specs] == [
        spec.expected_outcomes for spec in second.test_specs
    ]


def test_planning_replay_cli_writes_specs_and_summary(tmp_path, monkeypatch) -> None:
    import subprocess
    import sys

    output = tmp_path / "plans"
    command = [
        sys.executable,
        str(ROOT / "scripts/plan_tests.py"),
        "--project-profile",
        "examples/rwa/project-profile.json",
        "--contract",
        "examples/rwa/plans/contracts/payment.json",
        "--provider",
        "replay",
        "--output",
        str(output),
    ]
    completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False)
    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)
    assert len(result["test_specs"]) == 3
    assert Path(result["summary_artifact"]).is_file()
    assert len(result["spec_artifacts"]) == 3