import re

from autoqe.contracts.behavioral_contract import BehavioralContract
from autoqe.contracts.common import Availability, RiskLevel
from autoqe.contracts.project_profile import ProjectProfile
from autoqe.contracts.test_spec import ScenarioType, SemanticAction, TestLayer, TestSpec
from autoqe.planning.models import PlanValidationReport, PlannerConfig, ScenarioCandidate
from autoqe.planning.coverage import _BOUNDARY

_EXECUTABLE_MARKERS = re.compile(
    r"(?i)(?:\b(playwright|cypress|pytest|httpx|requests|curl|javascript|python)\b|"
    r"\[data-test|\bpage\.|\bcy\.|xpath|css selector|https?://|\.click\s*\(|"
    r"defect[- ]profile|fault[- ]injection|mutation[- ]profile)"
)


def _layer_supported(layer: TestLayer, profile: ProjectProfile) -> bool:
    ui_available = profile.execution_capabilities.ui == Availability.AVAILABLE
    api_available = profile.execution_capabilities.api == Availability.AVAILABLE
    return {
        TestLayer.UI: ui_available,
        TestLayer.API: api_available,
        TestLayer.BOTH: ui_available and api_available,
    }[layer]


def _source_lineage_valid(contract: BehavioralContract) -> bool:
    if not contract.source_ids or set(contract.source_fingerprints) != set(contract.source_ids):
        return False
    return all(re.fullmatch(r"[0-9a-f]{64}", digest) for digest in contract.source_fingerprints.values())


def validate_test_specs(
    project_profile: ProjectProfile,
    contract: BehavioralContract,
    candidates: tuple[ScenarioCandidate, ...],
    test_specs: tuple[TestSpec, ...],
    config: PlannerConfig,
) -> PlanValidationReport:
    errors: list[str] = []
    unsupported_layers = sum(
        1 for spec in test_specs if not _layer_supported(spec.test_layer, project_profile)
    )
    if project_profile.project_id != contract.project_id:
        errors.append("ProjectProfile and BehavioralContract project IDs do not match")
    if not _source_lineage_valid(contract):
        errors.append("BehavioralContract source provenance is missing or invalid")
    if len(test_specs) > config.max_tests:
        errors.append("planned TestSpec count exceeds configured maximum")

    candidate_by_id = {candidate.scenario_id: candidate for candidate in candidates}
    seen_scenarios: set[ScenarioType] = set()
    seen_test_ids: set[str] = set()
    for spec in test_specs:
        candidate = candidate_by_id.get(spec.test_id)
        if candidate is None:
            errors.append("TestSpec does not resolve to a selected planning scenario")
            continue
        if spec.test_id in seen_test_ids or spec.scenario_type in seen_scenarios:
            errors.append("duplicate or redundant planning scenario")
        seen_test_ids.add(spec.test_id)
        seen_scenarios.add(spec.scenario_type)

        if spec.contract_id != contract.contract_id:
            errors.append("TestSpec contract_id does not match its BehavioralContract")
        if spec.project_id != contract.project_id:
            errors.append("TestSpec project_id does not match its BehavioralContract")
        if spec.requirement_ids != contract.requirement_ids:
            errors.append("TestSpec requirement IDs must match its BehavioralContract")
        if spec.source_ids != contract.source_ids or spec.source_fingerprints != contract.source_fingerprints:
            errors.append("TestSpec source provenance does not match its BehavioralContract")
        if spec.risk_level != contract.risk_level or spec.priority != candidate.priority:
            errors.append("TestSpec risk or priority does not match deterministic planning")
        if spec.scenario_type != candidate.scenario_type:
            errors.append("TestSpec scenario type does not match its selected planning candidate")
        if spec.test_layer != candidate.test_layer:
            errors.append("TestSpec test layer does not match deterministic layer selection")
        if not _layer_supported(spec.test_layer, project_profile):
            errors.append("TestSpec selects a layer unavailable in ProjectProfile")
        if spec.expected_outcomes != candidate.expected_outcomes:
            errors.append("TestSpec expected outcomes are not exactly contract-grounded")
        if spec.preconditions != contract.preconditions:
            errors.append("TestSpec preconditions must preserve the parent contract")
        if spec.scenario_type == ScenarioType.AUTHORIZATION and not contract.authorization_constraints:
            errors.append("authorization scenario requires contract authorization evidence")
        if spec.scenario_type == ScenarioType.STATE_TRANSITION and not contract.state_transitions:
            errors.append("state-transition scenario requires contract state-transition evidence")
        if spec.scenario_type == ScenarioType.BOUNDARY and not any(
            _BOUNDARY.search(condition) for condition in contract.business_conditions
        ):
            errors.append("boundary scenario requires an explicit contract boundary")
        if not any(step.action == SemanticAction.ASSERT for step in spec.steps):
            errors.append("each TestSpec requires a semantic assertion step")
        if spec.scenario_type in {ScenarioType.NEGATIVE, ScenarioType.BOUNDARY} and not any(
            step.action == SemanticAction.SUBMIT for step in spec.steps
        ):
            errors.append("negative and boundary scenarios require a semantic submit step")
        if spec.scenario_type == ScenarioType.AUTHORIZATION and not any(
            step.action == SemanticAction.AUTHENTICATE for step in spec.steps
        ):
            errors.append("authorization scenarios require a semantic authentication step")
        if any(
            f"Unresolved contract unknown: {unknown}" not in spec.limitations
            for unknown in contract.unknowns
        ):
            errors.append("TestSpec limitations must preserve every contract unknown")
        for step in spec.steps:
            if _EXECUTABLE_MARKERS.search(" ".join(filter(None, (step.target, step.value, step.data_ref)))):
                errors.append("semantic step contains provider-specific or executable details")
        if any(_EXECUTABLE_MARKERS.search(tag) for tag in spec.tags):
            errors.append("TestSpec tags contain provider-specific or executable details")

    if unsupported_layers:
        errors.append("one or more TestSpecs selected unsupported execution layers")
    return PlanValidationReport(
        planning_validation_pass=not errors,
        unsupported_layer_selections=unsupported_layers,
        errors=errors,
    )