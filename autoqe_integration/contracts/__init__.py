"""Versioned, transport-neutral external evaluation contracts."""

import hashlib
import json
import re
from typing import Annotated, Any, Literal, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

Identifier = Annotated[str, StringConstraints(strict=True, min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")]
Digest = Annotated[str, StringConstraints(strict=True, pattern=r"^[0-9a-f]{64}$")]
# Provider identities may be a Git revision, a release version or a service
# deployment identifier. The concrete provider validates its own identity format.
Revision = Identifier
Classification = Literal["PRODUCT_DEFECT", "TEST_DEFECT", "ENVIRONMENT_FAILURE", "DATA_FAILURE", "UNSUPPORTED_BEHAVIOR", "UNKNOWN"]
Dimension = Literal["triage_classification_agreement"]
Status = Literal["COMPLETED_PASS", "COMPLETED_FAIL", "ERROR", "INCOMPLETE"]
ErrorCode = Literal["ENVIRONMENT_UNAVAILABLE", "REVISION_MISMATCH", "DIRTY_EVALUATOR", "INVOCATION_FAILED", "TIMEOUT", "INVALID_RESPONSE", "EVALUATOR_ERROR"]


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def read_json(content: str | bytes) -> Any:
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate JSON field")
            result[key] = value
        return result

    def invalid_number(_):
        raise ValueError("nonfinite JSON number")

    return json.loads(content, object_pairs_hook=pairs, parse_constant=invalid_number)


def _privacy(value):
    if isinstance(value, dict):
        for key, item in value.items():
            if re.search(r"password|passwd|secret|cookie|authorization|headers|api_key|access_token|request_body|response_body|fault_profile|patch_description|worktree", key, re.I):
                raise ValueError("forbidden export field")
            _privacy(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _privacy(item)
    elif isinstance(value, str) and re.search(r"\bBearer\s+\S+|\bsk-[\w-]{12,}|\bgh[pousr]_[\w]{12,}|[A-Za-z]:[\\/]|\\\\", value):
        raise ValueError("unsafe export value")


class IntegrationModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    @model_validator(mode="before")
    @classmethod
    def privacy(cls, value):
        _privacy(value)
        return value

    def stable_json(self) -> str:
        return canonical_json(self.model_dump(mode="json")) + "\n"


class ArtifactIdentity(IntegrationModel):
    kind: Literal["contract", "spec", "execution", "triage"]
    artifact_id: Identifier
    sha256: Digest


class ExpectationProvenance(IntegrationModel):
    source_id: UUID
    source_sha256: Digest
    label_id: UUID
    method: Literal["external_qualification", "synthetic_control"]


class Lineage(IntegrationModel):
    requirement_ids: list[Identifier] = Field(default_factory=list)
    source_ids: list[Identifier] = Field(default_factory=list)
    source_fingerprints: dict[Identifier, Digest] = Field(default_factory=dict)
    evidence_hashes: list[Digest] = Field(default_factory=list)


class ExternalEvaluationRequest(IntegrationModel):
    schema_version: Literal["1.0"] = "1.0"
    evaluation_case_id: UUID
    project_id: Identifier
    window_id: Identifier
    evaluation_dimension: Dimension = "triage_classification_agreement"
    actual_value: Classification
    expected_value: Classification
    expectation_provenance: ExpectationProvenance
    source_artifacts: list[ArtifactIdentity] = Field(min_length=1, max_length=4)
    lineage: Lineage
    source_kind: Literal["RUNTIME", "SYNTHETIC"]
    qualification_only: bool = False
    privacy_projection: Literal["classification-only-v1"] = "classification-only-v1"

    @model_validator(mode="after")
    def sources(self):
        kinds = [item.kind for item in self.source_artifacts]
        if len(set(kinds)) != len(kinds) or "triage" not in kinds:
            raise ValueError("unique source roles including triage are required")
        if self.qualification_only != (self.expectation_provenance.method == "synthetic_control"):
            raise ValueError("control and expectation provenance mismatch")
        if self.qualification_only and self.source_kind != "SYNTHETIC":
            raise ValueError("controls must be synthetic")
        return self

    @property
    def sha256(self):
        return digest(self.model_dump(mode="json"))


class ExternalEvaluationResult(IntegrationModel):
    schema_version: Literal["1.0"] = "1.0"
    request: ExternalEvaluationRequest
    request_sha256: Digest
    provider_id: Identifier
    provider_revision: Revision | None
    provider_version: Identifier
    status: Status
    attempted: bool
    passed: bool | None
    native_result: dict[str, Any] | None
    evaluated_dimensions: list[Dimension]
    not_applicable: list[Identifier]
    errors: list[ErrorCode]
    limitations: list[Literal["CLASSIFICATION_ONLY", "NO_RATIONALE_EVALUATION", "EXTERNAL_LINEAGE_ONLY"]]

    @model_validator(mode="after")
    def completion(self):
        if self.request_sha256 != self.request.sha256:
            raise ValueError("request digest mismatch")
        completed = self.status in ("COMPLETED_PASS", "COMPLETED_FAIL")
        if completed:
            if not self.attempted or self.provider_revision is None or not self.native_result or self.errors:
                raise ValueError("completed evaluation requires provider identity and native evidence")
            if self.passed is not (self.status == "COMPLETED_PASS"):
                raise ValueError("status contradicts passed value")
            if self.evaluated_dimensions != [self.request.evaluation_dimension]:
                raise ValueError("completed dimension mismatch")
        elif self.passed is not None or self.native_result is not None or not self.errors or self.evaluated_dimensions:
            raise ValueError("uncompleted result must retain error, not a score")
        if self.status == "ERROR" and not self.attempted:
            raise ValueError("unattempted evaluation is incomplete, not evaluator error")
        canonical_json(self.native_result)
        return self


class PlannedEvaluation(IntegrationModel):
    evaluation_case_id: UUID
    request_sha256: Digest
    qualification_only: bool


class ExternalEvaluationWindow(IntegrationModel):
    schema_version: Literal["1.0"] = "1.0"
    project_id: Identifier
    window_id: Identifier
    provider_id: Identifier
    provider_revision: Revision
    evaluation_dimension: Dimension
    planned: list[PlannedEvaluation]

    @model_validator(mode="after")
    def unique_cases(self):
        if len({case.evaluation_case_id for case in self.planned}) != len(self.planned):
            raise ValueError("duplicate planned evaluation")
        return self


class EvaluationProvider(Protocol):
    def evaluate(self, request: ExternalEvaluationRequest) -> ExternalEvaluationResult: ...
