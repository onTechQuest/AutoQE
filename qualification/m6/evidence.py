"""Join a sanitized actual-artifact projection to separately retained labels."""

from pathlib import Path
from uuid import UUID

from pydantic import Field

from autoqe_integration.contracts import (
    ArtifactIdentity, Classification, ExpectationProvenance, ExternalEvaluationRequest,
    Identifier, IntegrationModel, Lineage, canonical_json, read_json,
)


class ExpectedLabel(IntegrationModel):
    expected_value: Classification
    provenance: ExpectationProvenance


class Expectations(IntegrationModel):
    schema_version: str
    project_id: Identifier
    labels: list[ExpectedLabel]


class CapturedCase(IntegrationModel):
    evaluation_case_id: UUID
    label_id: UUID
    actual_value: Classification
    source_artifacts: list[ArtifactIdentity]
    lineage: Lineage
    source_kind: str
    qualification_only: bool = False


class CapturedEvidence(IntegrationModel):
    schema_version: str
    project_id: Identifier
    window_id: Identifier
    cases: list[CapturedCase] = Field(min_length=1)


def load_requests(evidence_path: Path, expectations_path: Path) -> list[ExternalEvaluationRequest]:
    try:
        evidence = CapturedEvidence.model_validate_json(canonical_json(read_json(evidence_path.read_bytes())))
        expectations = Expectations.model_validate_json(canonical_json(read_json(expectations_path.read_bytes())))
        if evidence.schema_version != "1.0" or expectations.schema_version != "1.0":
            raise ValueError("unsupported evidence version")
        if evidence.project_id != expectations.project_id:
            raise ValueError("mixed project")
        labels = {item.provenance.label_id: item for item in expectations.labels}
        if len(labels) != len(expectations.labels):
            raise ValueError("duplicate expectation")
        ids = [item.evaluation_case_id for item in evidence.cases]
        references = [item.label_id for item in evidence.cases]
        if len(set(ids)) != len(ids) or len(set(references)) != len(references) or set(references) != set(labels):
            raise ValueError("duplicate request or missing/unused expectation")
        requests = []
        for case in evidence.cases:
            label = labels[case.label_id]
            requests.append(ExternalEvaluationRequest(
                evaluation_case_id=case.evaluation_case_id, project_id=evidence.project_id, window_id=evidence.window_id,
                actual_value=case.actual_value, expected_value=label.expected_value, expectation_provenance=label.provenance,
                source_artifacts=case.source_artifacts, lineage=case.lineage, source_kind=case.source_kind,
                qualification_only=case.qualification_only,
            ))
        return requests
    except (OSError, ValueError):
        raise ValueError("invalid sanitized evidence or independent expectations") from None
