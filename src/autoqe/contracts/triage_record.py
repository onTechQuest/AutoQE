from enum import StrEnum

from pydantic import Field

from autoqe.contracts.common import EvidenceReference, Identifier, ProvenanceModel


class TriageClassification(StrEnum):
    PRODUCT_DEFECT = "PRODUCT_DEFECT"
    TEST_DEFECT = "TEST_DEFECT"
    ENVIRONMENT_FAILURE = "ENVIRONMENT_FAILURE"
    DATA_FAILURE = "DATA_FAILURE"
    UNSUPPORTED_BEHAVIOR = "UNSUPPORTED_BEHAVIOR"
    UNKNOWN = "UNKNOWN"


class TriageRecord(ProvenanceModel):
    triage_id: Identifier
    execution_id: Identifier
    test_id: Identifier
    classification: TriageClassification
    summary: str
    expected_behavior_reference: Identifier | None = None
    observed_behavior_reference: Identifier | None = None
    supporting_evidence_refs: list[EvidenceReference] = Field(default_factory=list)
    suspected_component: str | None = None
    recommended_next_action: str