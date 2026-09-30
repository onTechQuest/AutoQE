from typing import Literal

from pydantic import Field

from autoqe.contracts.common import Identifier, RiskLevel, StrictModel
from autoqe.contracts.test_spec import (
    EvidenceRequirement,
    ExpectedOutcome,
    ScenarioType,
    SemanticStep,
    TestLayer,
    TestSpec,
)


class PlannerConfig(StrictModel):
    max_tests: int = Field(default=5, ge=1, le=10)


class RiskAssessment(StrictModel):
    declared_risk: RiskLevel
    test_priority: int = Field(ge=1, le=5)
    risk_factors: list[str] = Field(default_factory=list)
    rationale: str


class ScenarioCandidate(StrictModel):
    scenario_id: Identifier
    scenario_type: ScenarioType
    coverage_refs: list[Identifier]
    expected_outcomes: list[ExpectedOutcome] = Field(min_length=1)
    preconditions: list[str] = Field(default_factory=list)
    test_data_requirements: list[str] = Field(default_factory=list)
    priority: int = Field(ge=1, le=5)
    ui_material: bool = False
    title: str
    intent: str
    rationale: str
    test_layer: TestLayer | None = None
    layer_rationale: str = ""


class PlannedScenario(StrictModel):
    scenario_id: Identifier
    steps: list[SemanticStep] = Field(min_length=1)


class PlanningResponse(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    scenarios: list[PlannedScenario] = Field(min_length=1)


class PlanValidationReport(StrictModel):
    planning_validation_pass: bool
    unsupported_layer_selections: int = Field(ge=0)
    errors: list[str] = Field(default_factory=list)


class PlanningSummary(StrictModel):
    contract_id: Identifier
    project_id: Identifier
    declared_risk: RiskLevel
    test_priority: int = Field(ge=1, le=5)
    risk_factors: list[str]
    testspec_count: int = Field(ge=0)
    requirements_covered: int = Field(ge=0)
    covered_requirement_ids: list[Identifier]
    behavior_claims_covered: int = Field(ge=0)
    covered_behavior_refs: list[Identifier]
    authorization_constraints_covered: int = Field(ge=0)
    state_transitions_covered: int = Field(ge=0)
    unknowns_preserved: list[str]
    unsupported_layer_selections: int = Field(ge=0)
    planning_validation_pass: bool
    scenario_rationales: dict[str, str]
    layer_rationales: dict[str, str]
    planning_limitations: list[str] = Field(default_factory=list)


class PlanningResult(StrictModel):
    test_specs: list[TestSpec]
    summary: PlanningSummary


class PlanningContext(StrictModel):
    project_id: Identifier
    contract: dict[str, object]
    execution_capabilities: dict[str, str]
    planner_config: dict[str, int]
    risk_assessment: dict[str, object]
    scenarios: list[dict[str, object]]

    def to_model_context(self) -> dict[str, object]:
        return self.model_dump(mode="json")