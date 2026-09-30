from enum import StrEnum

from pydantic import Field

from autoqe.contracts.common import Availability, Identifier, ProvenanceModel, RiskLevel, StrictModel


class TestLayer(StrEnum):
    UI = "UI"
    API = "API"
    BOTH = "BOTH"


class ScenarioType(StrEnum):
    POSITIVE = "POSITIVE"
    NEGATIVE = "NEGATIVE"
    BOUNDARY = "BOUNDARY"
    AUTHORIZATION = "AUTHORIZATION"
    STATE_TRANSITION = "STATE_TRANSITION"


class SemanticAction(StrEnum):
    NAVIGATE = "NAVIGATE"
    AUTHENTICATE = "AUTHENTICATE"
    SELECT_ENTITY = "SELECT_ENTITY"
    ENTER_VALUE = "ENTER_VALUE"
    SUBMIT = "SUBMIT"
    ASSERT = "ASSERT"
    RESET = "RESET"
    WAIT_FOR_STATE = "WAIT_FOR_STATE"


class SemanticStep(StrictModel):
    step_id: Identifier
    action: SemanticAction
    target: str
    value: str | None = None
    data_ref: str | None = None


class ExpectedOutcome(StrictModel):
    outcome_id: Identifier
    description: str


class EvidenceRequirement(StrictModel):
    evidence_type: str
    description: str
    availability: Availability


class TestSpec(ProvenanceModel):
    test_id: Identifier
    project_id: Identifier
    contract_id: Identifier
    requirement_ids: list[Identifier] = Field(min_length=1)
    title: str
    intent: str
    risk_level: RiskLevel
    priority: int = Field(ge=1, le=5)
    test_layer: TestLayer
    scenario_type: ScenarioType
    preconditions: list[str] = Field(default_factory=list)
    test_data_requirements: list[str] = Field(default_factory=list)
    steps: list[SemanticStep] = Field(min_length=1)
    expected_outcomes: list[ExpectedOutcome] = Field(min_length=1)
    evidence_requirements: list[EvidenceRequirement] = Field(default_factory=list)
    cleanup_requirements: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)