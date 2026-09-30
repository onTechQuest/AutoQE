from pydantic import Field

from autoqe.contracts.common import Identifier, ProvenanceModel, RiskLevel, StrictModel


class BehaviorExpectation(StrictModel):
    behavior_id: Identifier
    description: str


class StateTransition(StrictModel):
    from_state: str
    event: str
    to_state: str


class BehavioralContract(ProvenanceModel):
    contract_id: Identifier
    project_id: Identifier
    requirement_ids: list[Identifier] = Field(min_length=1)
    title: str
    intent: str
    risk_level: RiskLevel
    preconditions: list[str] = Field(default_factory=list)
    business_conditions: list[str] = Field(default_factory=list)
    expected_behaviors: list[BehaviorExpectation] = Field(min_length=1)
    forbidden_behaviors: list[BehaviorExpectation] = Field(default_factory=list)
    state_transitions: list[StateTransition] = Field(default_factory=list)
    authorization_constraints: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    unknowns: list[str] = Field(default_factory=list)