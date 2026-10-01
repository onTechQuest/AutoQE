"""Non-core, versioned observational reporting models; no runtime contracts."""

import json
from typing import Any, Literal

from pydantic import Field, model_validator

from autoqe.contracts.common import Identifier, PrivacySafeModel
from autoqe.contracts.triage_record import TriageClassification

Stage = Literal["contract", "spec", "execution", "triage"]


class ArtifactInput(PrivacySafeModel):
    kind: Literal["contract", "spec", "execution", "triage", "qualification", "usage"]
    path: str = Field(min_length=1)


class CaseInput(PrivacySafeModel):
    case_id: Identifier
    contract: Identifier | None = None
    spec: Identifier | None = None
    execution: Identifier | None = None
    triage: Identifier | None = None
    required_stages: list[Stage] = Field(default_factory=lambda: ["contract", "spec", "execution", "triage"], min_length=1)
    execution_attempted: bool = True
    kind: Literal["RUNTIME", "SYNTHETIC"] = "RUNTIME"
    target_state: Literal["HEALTHY", "CONTROLLED_FAULT"] | None = None
    expected_classification: TriageClassification | None = None
    label_source: Identifier | None = None

    @model_validator(mode="after")
    def coherent_labels(self):
        if len(set(self.required_stages)) != len(self.required_stages):
            raise ValueError("duplicate required stages")
        if (self.target_state or self.expected_classification) and not self.label_source:
            raise ValueError("external labels require a qualification source")
        if self.target_state and (self.kind != "RUNTIME" or not self.execution_attempted):
            raise ValueError("target qualification requires an attempted runtime execution")
        if self.target_state == "CONTROLLED_FAULT" and self.expected_classification != "PRODUCT_DEFECT":
            raise ValueError("controlled product fault requires PRODUCT_DEFECT expected label")
        if self.target_state == "HEALTHY" and self.expected_classification not in (None, "UNKNOWN"):
            raise ValueError("healthy target label contradicts expected failure classification")
        if self.kind == "SYNTHETIC" and self.execution_attempted:
            raise ValueError("synthetic evidence is not a runtime execution attempt")
        return self


class EvidenceCheck(PrivacySafeModel):
    """Explicit JSON-pointer corroboration of externally authored labels/counts."""

    source: Identifier
    pointer: str
    expected: Any


class MetricsManifest(PrivacySafeModel):
    schema_version: Literal["1.0"] = "1.0"
    project_id: Identifier
    window_id: Identifier
    artifacts: dict[Identifier, ArtifactInput] = Field(default_factory=dict)
    cases: list[CaseInput] = Field(default_factory=list)
    checks: list[EvidenceCheck] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class ModelUsage(PrivacySafeModel):
    project_id: Identifier
    window_id: Identifier
    mode: Literal["TELEMETRY", "NO_LIVE_PROCESSING"]
    live_model_calls: int = Field(ge=0, strict=True)
    live_model_tokens: int | None = Field(default=None, ge=0, strict=True)
    replay_or_deterministic_only: bool = False
    source: Identifier

    @model_validator(mode="after")
    def observed_usage(self):
        if self.mode == "NO_LIVE_PROCESSING":
            if self.live_model_calls != 0 or not self.replay_or_deterministic_only or self.live_model_tokens not in (None, 0):
                raise ValueError("no-live usage requires explicit zero calls and replay/deterministic-only evidence")
        elif self.live_model_tokens is None:
            raise ValueError("telemetry requires observed token count")
        if self.live_model_calls == 0 and self.live_model_tokens not in (None, 0):
            raise ValueError("tokens contradict zero live calls")
        return self


class Metric(PrivacySafeModel):
    metric_id: Identifier
    definition: str
    numerator: int | None = Field(default=None, ge=0)
    denominator: int | None = Field(default=None, ge=0)
    value: float | int | None = None
    unit: Literal["ratio", "tokens"] = "ratio"
    sample_size: int = Field(ge=0)
    availability: Literal["AVAILABLE", "UNAVAILABLE", "NOT_APPLICABLE"]
    source_refs: list[str] = Field(default_factory=list)
    details: dict[str, Any] = Field(default_factory=dict)
    limitations: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def consistent_arithmetic(self):
        if self.availability != "AVAILABLE":
            if self.value is not None or not self.limitations:
                raise ValueError("unavailable metric requires null value and explicit reason")
        elif self.unit == "ratio":
            if self.numerator is None or not self.denominator or self.numerator > self.denominator:
                raise ValueError("inconsistent numerator/denominator")
            if self.value != self.numerator / self.denominator or self.sample_size != self.denominator:
                raise ValueError("inconsistent value/sample size")
        elif self.value is None or self.value < 0:
            raise ValueError("available usage requires a nonnegative observed value")
        return self


class QualityMetricsReport(PrivacySafeModel):
    schema_version: Literal["1.0"] = "1.0"
    project_id: Identifier
    window_id: Identifier
    metrics: list[Metric]
    sources: dict[str, str]  # Artifact identifier -> SHA-256, including invalid specs.
    limitations: list[str]

    def stable_json(self) -> str:
        return json.dumps(self.model_dump(mode="json"), indent=2, sort_keys=True, ensure_ascii=True) + "\n"
