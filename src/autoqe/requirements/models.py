from enum import StrEnum

from pydantic import ConfigDict, Field, model_validator

from autoqe.contracts.common import Identifier, PrivacySafeModel, RiskLevel


class RequirementSourceType(StrEnum):
    MARKDOWN = "MARKDOWN"


class RequirementMetadata(PrivacySafeModel):
    model_config = ConfigDict(frozen=True)

    requirement_id: Identifier
    title: str
    business_intent: str
    risk_level: RiskLevel
    explicit_unknowns: tuple[str, ...] = ()
    acceptance_criteria: tuple[str, ...] = ()
    forbidden_behaviors: tuple[str, ...] = ()
    preconditions: tuple[str, ...] = ()
    business_conditions: tuple[str, ...] = ()
    authorization_constraints: tuple[str, ...] = ()
    state_transitions: tuple[str, ...] = ()


class RequirementSource(PrivacySafeModel):
    model_config = ConfigDict(frozen=True, revalidate_instances="always")

    source_id: Identifier
    source_type: RequirementSourceType
    location: str
    content_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    content: str = Field(min_length=1, max_length=32768)
    metadata: RequirementMetadata

    @model_validator(mode="after")
    def validate_content_fingerprint(self) -> "RequirementSource":
        from autoqe.requirements.fingerprints import content_fingerprint

        if content_fingerprint(self.content) != self.content_fingerprint:
            raise ValueError("requirement source content fingerprint mismatch")
        return self