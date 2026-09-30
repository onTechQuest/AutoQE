from datetime import datetime
from enum import StrEnum

from pydantic import Field, field_validator, model_validator

from autoqe.contracts.common import EvidenceReference, Identifier, ProvenanceModel, StrictModel


class ExecutionStatus(StrEnum):
    PASSED = "PASSED"
    FAILED = "FAILED"
    ERROR = "ERROR"
    SKIPPED = "SKIPPED"
    INCOMPLETE = "INCOMPLETE"


class ResultStatus(StrEnum):
    PASSED = "PASSED"
    FAILED = "FAILED"
    ERROR = "ERROR"
    SKIPPED = "SKIPPED"
    UNKNOWN = "UNKNOWN"


class FailureCategory(StrEnum):
    ASSERTION_FAILURE = "ASSERTION_FAILURE"
    PROVIDER_ERROR = "PROVIDER_ERROR"
    ENVIRONMENT_FAILURE = "ENVIRONMENT_FAILURE"
    DATA_FAILURE = "DATA_FAILURE"
    UNSUPPORTED_BEHAVIOR = "UNSUPPORTED_BEHAVIOR"
    UNKNOWN = "UNKNOWN"


class StepResult(StrictModel):
    step_id: Identifier
    status: ResultStatus
    observed: str | None = None
    evidence_refs: list[EvidenceReference] = Field(default_factory=list)


class AssertionResult(StrictModel):
    assertion_id: Identifier
    status: ResultStatus
    expected: str
    observed: str | None = None
    evidence_refs: list[EvidenceReference] = Field(default_factory=list)


class ExecutionRecord(ProvenanceModel):
    execution_id: Identifier
    test_id: Identifier
    project_id: Identifier
    provider: str
    provider_version: str
    status: ExecutionStatus
    started_at: datetime
    completed_at: datetime | None = None
    duration_ms: float | None = Field(default=None, ge=0)
    step_results: list[StepResult] = Field(default_factory=list)
    assertion_results: list[AssertionResult] = Field(default_factory=list)
    observed_outcomes: list[str] = Field(default_factory=list)
    evidence_refs: list[EvidenceReference] = Field(default_factory=list)
    failure_category: FailureCategory | None = None
    environment_identity: dict[str, str] = Field(default_factory=dict)
    test_data_reset_identity: str | None = None

    @field_validator("started_at", "completed_at")
    @classmethod
    def require_timezone(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("execution timestamps must include a timezone")
        return value

    @model_validator(mode="after")
    def validate_execution_interval(self) -> "ExecutionRecord":
        if self.completed_at is not None and self.completed_at < self.started_at:
            raise ValueError("completed_at must not precede started_at")
        if self.status in {ExecutionStatus.FAILED, ExecutionStatus.ERROR} and not self.failure_category:
            raise ValueError("failed or errored executions require a failure_category")
        return self