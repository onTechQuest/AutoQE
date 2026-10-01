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
    ResultStatus,
    StepResult,
)
from autoqe.contracts.project_profile import ProjectProfile
from autoqe.contracts.test_spec import TestSpec


def validate_completeness(test_spec: TestSpec, record: ExecutionRecord) -> ExecutionRecord:
    """Account for each expected outcome, retaining all supplied provider evidence.

    Completeness can downgrade a result, never upgrade a provider's non-pass.
    This is execution validation, not root-cause triage.
    """
    result = record.model_copy(deep=True)
    issues: list[str] = []
    expected_ids = [outcome.outcome_id for outcome in test_spec.expected_outcomes]
    if len(set(expected_ids)) != len(expected_ids):
        issues.append("Expected outcome IDs are not unique.")
    for outcome in test_spec.expected_outcomes:
        matches = [item for item in result.assertion_results if item.assertion_id == outcome.outcome_id]
        if not matches:
            result.assertion_results.append(AssertionResult(
                assertion_id=outcome.outcome_id,
                status=ResultStatus.UNKNOWN,
                expected=outcome.description,
                observed="No executed, supported assertion was reported for this expected outcome.",
            ))
            issues.append(f"Missing assertion: {outcome.outcome_id}.")
        elif len(matches) != 1 or matches[0].expected != outcome.description:
            issues.append(f"Ambiguous or mismatched assertion: {outcome.outcome_id}.")
        if any(item.status in {ResultStatus.UNKNOWN, ResultStatus.SKIPPED} for item in matches):
            issues.append(f"Unresolved assertion: {outcome.outcome_id}.")
    if any(item.assertion_id not in expected_ids for item in result.assertion_results):
        issues.append("Provider reported an assertion outside the expected outcomes.")
    step_ids = [step.step_id for step in test_spec.steps]
    if len(set(step_ids)) != len(step_ids):
        issues.append("Semantic step IDs are not unique.")
    for step_id in step_ids:
        matches = [item for item in result.step_results if item.step_id == step_id]
        if len(matches) != 1 or matches[0].status != ResultStatus.PASSED:
            issues.append(f"Step did not complete successfully: {step_id}.")
    if (result.test_id, result.project_id) != (test_spec.test_id, test_spec.project_id):
        issues.append("Execution identity does not match the TestSpec.")
    statuses = {item.status for item in result.assertion_results + result.step_results}
    if ResultStatus.ERROR in statuses and result.status != ExecutionStatus.ERROR:
        result.status = ExecutionStatus.ERROR
        result.failure_category = FailureCategory.PROVIDER_ERROR
    elif ResultStatus.FAILED in statuses and result.status not in {ExecutionStatus.ERROR, ExecutionStatus.FAILED}:
        result.status = ExecutionStatus.FAILED
        result.failure_category = FailureCategory.ASSERTION_FAILURE
    elif issues and result.status == ExecutionStatus.PASSED:
        result.status = ExecutionStatus.INCOMPLETE
    result.limitations = list(dict.fromkeys(result.limitations + issues))
    return ExecutionRecord.model_validate(result.model_dump(mode="python"))


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
    record = ExecutionRecord(
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
    return validate_completeness(test_spec, record)


def evidence_uri(path: Path, repository_root: Path) -> str:
    return path.resolve().relative_to(repository_root.resolve()).as_posix()
