from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from uuid import uuid4

from autoqe.contracts.common import EvidenceReference
from autoqe.contracts.execution_record import (
    AssertionResult,
    ExecutionRecord,
    ExecutionStatus,
    FailureCategory,
    StepResult,
)
from autoqe.contracts.project_profile import ProjectProfile
from autoqe.contracts.test_spec import TestSpec


def make_execution_record(
    test_spec: TestSpec,
    project_profile: ProjectProfile,
    provider: str,
    provider_version: str,
    status: ExecutionStatus,
    started_at: datetime,
    started_clock: float,
    *,
    step_results: list[StepResult] | None = None,
    assertion_results: list[AssertionResult] | None = None,
    observed_outcomes: list[str] | None = None,
    evidence_refs: list[EvidenceReference] | None = None,
    failure_category: FailureCategory | None = None,
    reset_identity: str | None = None,
    execution_id: str | None = None,
) -> ExecutionRecord:
    completed_at = datetime.now(timezone.utc)
    ui_url = str(project_profile.application.ui_base_url)
    api_url = str(project_profile.application.api_base_url)
    return ExecutionRecord(
        execution_id=execution_id or uuid4().hex,
        test_id=test_spec.test_id,
        project_id=test_spec.project_id,
        provider=provider,
        provider_version=provider_version,
        status=status,
        started_at=started_at,
        completed_at=completed_at,
        duration_ms=max(0.0, (perf_counter() - started_clock) * 1000),
        step_results=step_results or [],
        assertion_results=assertion_results or [],
        observed_outcomes=observed_outcomes or [],
        evidence_refs=evidence_refs or [],
        failure_category=failure_category,
        environment_identity={
            "network_scope": "LOCAL_ONLY",
            "reference_revision": (
                project_profile.reference_target.revision if project_profile.reference_target else "UNKNOWN"
            ),
            "ui_host": ui_url.split("/")[2] if ui_url else "UNKNOWN",
            "api_host": api_url.split("/")[2] if api_url else "UNKNOWN",
        },
        test_data_reset_identity=reset_identity or project_profile.environment.reset_identity,
        source_ids=test_spec.source_ids,
        source_fingerprints=test_spec.source_fingerprints,
        correlation_id=test_spec.correlation_id,
        producer="autoqe-execution",
        producer_version="0.3.0",
        limitations=list(test_spec.limitations),
    )


def evidence_uri(path: Path, repository_root: Path) -> str:
    return path.resolve().relative_to(repository_root.resolve()).as_posix()