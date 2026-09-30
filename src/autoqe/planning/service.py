from collections.abc import Mapping
from datetime import datetime, timezone
from uuid import NAMESPACE_URL, uuid5

from pydantic import ValidationError

from autoqe.contracts.behavioral_contract import BehavioralContract
import re

from autoqe.contracts.common import Availability
from autoqe.contracts.project_profile import ProjectProfile
from autoqe.contracts.test_spec import EvidenceRequirement, TestLayer, TestSpec
from autoqe.interfaces.model_provider import ModelProvider
from autoqe.planning.coverage import CoveragePlanner
from autoqe.planning.layers import LayerSelector, UnsupportedLayerSelectionError
from autoqe.planning.models import (
    PlanValidationReport,
    PlannerConfig,
    PlanningContext,
    PlanningResponse,
    PlanningResult,
    PlanningSummary,
    RiskAssessment,
    ScenarioCandidate,
)
from autoqe.planning.risk import RiskPlanner
from autoqe.planning.validation import validate_test_specs

PLAN_TESTS_TASK = "plan_test_specs"


class PlanningError(ValueError):
    pass


class PlanningValidationError(PlanningError):
    def __init__(self, report: PlanValidationReport) -> None:
        self.report = report
        super().__init__("; ".join(report.errors))


def _evidence_requirements(layer: TestLayer, candidate: ScenarioCandidate) -> list[EvidenceRequirement]:
    evidence: list[EvidenceRequirement] = []
    if layer in {TestLayer.UI, TestLayer.BOTH}:
        evidence.append(
            EvidenceRequirement(
                evidence_type="VISIBLE_UI_STATE",
                description="Capture the user-visible state relevant to the selected contract outcomes.",
                availability=Availability.AVAILABLE,
            )
        )
    if layer in {TestLayer.API, TestLayer.BOTH}:
        evidence.append(
            EvidenceRequirement(
                evidence_type="API_RESULT_METADATA",
                description="Capture sanitized result/status metadata relevant to the selected contract outcomes.",
                availability=Availability.AVAILABLE,
            )
        )
    if candidate.scenario_type.value == "STATE_TRANSITION":
        evidence.append(
            EvidenceRequirement(
                evidence_type="RESULTING_STATE_REFERENCE",
                description="Reference the before/after state evidence for the declared transition.",
                availability=Availability.AVAILABLE,
            )
        )
    return evidence


def _planning_limitations(
    contract: BehavioralContract,
    candidates: tuple[ScenarioCandidate, ...],
    omitted_scenarios: tuple[ScenarioCandidate, ...] = (),
) -> list[str]:
    limitations = list(contract.limitations)
    limitations.extend(f"Unresolved contract unknown: {unknown}" for unknown in contract.unknowns)
    if contract.business_conditions and not any(
        "boundary" == candidate.scenario_type.value.lower() for candidate in candidates
    ):
        limitations.append("No explicit numeric/comparative boundary was specified; no boundary TestSpec was planned.")
    if omitted_scenarios:
        omitted = ", ".join(candidate.scenario_type.value for candidate in omitted_scenarios)
        limitations.append(f"Configured maximum omitted lower-priority scenario(s): {omitted}.")
    if CoveragePlanner.contradictory_unauthenticated_behaviors(contract):
        limitations.append(
            "An unauthenticated forbidden behavior conflicts with an authenticated precondition; "
            "no scenario was generated for that behavior."
        )
    return list(dict.fromkeys(limitations))


def _build_context(
    profile: ProjectProfile,
    contract: BehavioralContract,
    config: PlannerConfig,
    risk: RiskAssessment,
    candidates: tuple[ScenarioCandidate, ...],
) -> PlanningContext:
    return PlanningContext(
        project_id=contract.project_id,
        contract=contract.model_dump(mode="json"),
        execution_capabilities=profile.execution_capabilities.model_dump(mode="json"),
        planner_config=config.model_dump(mode="json"),
        risk_assessment=risk.model_dump(mode="json"),
        scenarios=[candidate.model_dump(mode="json") for candidate in candidates],
    )


def _build_test_specs(
    profile: ProjectProfile,
    contract: BehavioralContract,
    candidates: tuple[ScenarioCandidate, ...],
    response: PlanningResponse,
    omitted_scenarios: tuple[ScenarioCandidate, ...] = (),
) -> tuple[TestSpec, ...]:
    candidate_by_id = {candidate.scenario_id: candidate for candidate in candidates}
    plan_by_id = {scenario.scenario_id: scenario for scenario in response.scenarios}
    if len(plan_by_id) != len(response.scenarios) or set(plan_by_id) != set(candidate_by_id):
        raise PlanningError("replay planning response must contain exactly one entry for each selected scenario")

    limitations = _planning_limitations(contract, candidates, omitted_scenarios)
    test_specs: list[TestSpec] = []
    for candidate in candidates:
        if candidate.test_layer is None:
            raise PlanningError("layer selection must complete before TestSpec generation")
        test_id = candidate.scenario_id
        deterministic_id = uuid5(NAMESPACE_URL, f"autoqe:{contract.record_id}:{test_id}")
        test_specs.append(
            TestSpec(
                record_id=deterministic_id,
                created_at=datetime.now(timezone.utc),
                correlation_id=contract.correlation_id or contract.record_id,
                source_ids=contract.source_ids,
                source_fingerprints=contract.source_fingerprints,
                producer="autoqe-planner",
                producer_version="0.2.0",
                limitations=limitations,
                test_id=test_id,
                project_id=contract.project_id,
                contract_id=contract.contract_id,
                requirement_ids=contract.requirement_ids,
                title=candidate.title,
                intent=candidate.intent,
                risk_level=contract.risk_level,
                priority=candidate.priority,
                test_layer=candidate.test_layer,
                scenario_type=candidate.scenario_type,
                preconditions=candidate.preconditions,
                test_data_requirements=candidate.test_data_requirements,
                steps=plan_by_id[test_id].steps,
                expected_outcomes=candidate.expected_outcomes,
                evidence_requirements=_evidence_requirements(candidate.test_layer, candidate),
                cleanup_requirements=[
                    "Restore or remove test data through the future ProjectAdapter after execution; M2 performs no cleanup."
                ],
                tags=["autoqe-m2", candidate.scenario_type.value.lower()],
            )
        )
    return tuple(test_specs)


def _make_summary(
    contract: BehavioralContract,
    risk: RiskAssessment,
    candidates: tuple[ScenarioCandidate, ...],
    test_specs: tuple[TestSpec, ...],
    validation: PlanValidationReport,
    omitted_scenarios: tuple[ScenarioCandidate, ...] = (),
) -> PlanningSummary:
    covered_refs = list(dict.fromkeys(ref for candidate in candidates for ref in candidate.coverage_refs))
    scenario_rationales = {candidate.scenario_id: candidate.rationale for candidate in candidates}
    layer_rationales = {candidate.scenario_id: candidate.layer_rationale for candidate in candidates}
    auth_count = sum(ref.startswith("authorization-") for ref in covered_refs)
    transition_count = sum(ref.startswith("transition-") for ref in covered_refs)
    return PlanningSummary(
        contract_id=contract.contract_id,
        project_id=contract.project_id,
        declared_risk=risk.declared_risk,
        test_priority=risk.test_priority,
        risk_factors=risk.risk_factors,
        testspec_count=len(test_specs),
        requirements_covered=len({req for spec in test_specs for req in spec.requirement_ids}),
        covered_requirement_ids=list(dict.fromkeys(req for spec in test_specs for req in spec.requirement_ids)),
        behavior_claims_covered=len(covered_refs),
        covered_behavior_refs=covered_refs,
        authorization_constraints_covered=auth_count,
        state_transitions_covered=transition_count,
        unknowns_preserved=list(contract.unknowns),
        unsupported_layer_selections=validation.unsupported_layer_selections,
        planning_validation_pass=validation.planning_validation_pass,
        scenario_rationales=scenario_rationales,
        layer_rationales=layer_rationales,
        planning_limitations=_planning_limitations(contract, candidates, omitted_scenarios),
    )


def plan_tests(
    project_profile: ProjectProfile,
    contract: BehavioralContract,
    model_provider: ModelProvider,
    config: PlannerConfig | None = None,
) -> PlanningResult:
    config = config or PlannerConfig()
    profile = ProjectProfile.model_validate(project_profile.model_dump(mode="python"))
    validated_contract = BehavioralContract.model_validate(contract.model_dump(mode="python"))
    if profile.project_id != validated_contract.project_id:
        raise PlanningError("ProjectProfile and BehavioralContract project IDs must match")
    if (
        not validated_contract.source_ids
        or set(validated_contract.source_fingerprints) != set(validated_contract.source_ids)
        or any(not re.fullmatch(r"[0-9a-f]{64}", value) for value in validated_contract.source_fingerprints.values())
    ):
        raise PlanningError("BehavioralContract must retain valid source IDs and SHA-256 fingerprints")

    risk = RiskPlanner().analyze(validated_contract)
    all_candidates = CoveragePlanner().build(
        validated_contract,
        risk,
        PlannerConfig(max_tests=10),
    )
    candidates = all_candidates[: config.max_tests]
    omitted_scenarios = all_candidates[config.max_tests :]
    if not candidates:
        raise PlanningError("BehavioralContract has no grounded scenario candidates")
    try:
        candidates = tuple(LayerSelector().select(profile, candidate, risk) for candidate in candidates)
    except UnsupportedLayerSelectionError as exc:
        raise PlanningError(str(exc)) from exc

    planning_context = _build_context(profile, validated_contract, config, risk, candidates)
    response_data = model_provider.generate_structured(
        task=PLAN_TESTS_TASK,
        context=planning_context.to_model_context(),
        output_schema=PlanningResponse.model_json_schema(mode="validation"),
    )
    if not isinstance(response_data, Mapping):
        raise TypeError("ModelProvider must return a structured planning object")
    try:
        response = PlanningResponse.model_validate(response_data)
    except ValidationError:
        raise

    test_specs = _build_test_specs(
        profile, validated_contract, candidates, response, omitted_scenarios
    )
    validation = validate_test_specs(profile, validated_contract, candidates, test_specs, config)
    if not validation.planning_validation_pass:
        raise PlanningValidationError(validation)
    summary = _make_summary(
        validated_contract, risk, candidates, test_specs, validation, omitted_scenarios
    )
    return PlanningResult(test_specs=test_specs, summary=summary)