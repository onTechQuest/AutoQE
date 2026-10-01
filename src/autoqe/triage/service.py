"""Conservative deterministic triage of normalized execution evidence only."""

from uuid import uuid4

from autoqe.contracts import ExecutionRecord, ProjectProfile, TestSpec, TriageRecord
from autoqe.contracts.execution_record import ExecutionStatus, FailureCategory, ResultStatus
from autoqe.contracts.test_spec import SemanticAction
from autoqe.contracts.triage_record import TriageClassification as Classification


def _setup_groups(record: ExecutionRecord) -> list[dict[str, str]]:
    groups: dict[str, dict[str, str]] = {}
    for key, value in record.environment_identity.items():
        scope, name = key.split(".", 1) if key.startswith("provider-") and "." in key else ("single", key)
        groups.setdefault(scope, {})[name] = value
    return list(groups.values())


def triage_execution(profile: ProjectProfile, spec: TestSpec, execution: ExecutionRecord) -> TriageRecord:
    profile = ProjectProfile.model_validate(profile.model_dump(mode="python"))
    spec = TestSpec.model_validate(spec.model_dump(mode="python"))
    record = ExecutionRecord.model_validate(execution.model_dump(mode="python"))
    expected = {outcome.outcome_id: outcome.description for outcome in spec.expected_outcomes}
    assertions = record.assertion_results
    groups = _setup_groups(record)
    classification = Classification.UNKNOWN
    reason = "Execution evidence is insufficient to establish a failure cause."
    action = "Collect complete setup and expected-versus-observed evidence before assigning a cause."
    failed = [item for item in assertions if item.status == ResultStatus.FAILED]
    mismatch = (
        not (profile.project_id == spec.project_id == record.project_id)
        or record.test_id != spec.test_id
        or len(expected) != len(spec.expected_outcomes)
        or len({item.assertion_id for item in assertions}) != len(assertions)
        or any(item.assertion_id not in expected or item.expected != expected[item.assertion_id] for item in assertions)
        or (record.status == ExecutionStatus.PASSED and any(item.status != ResultStatus.PASSED for item in assertions))
        or (record.status == ExecutionStatus.PASSED and {item.assertion_id for item in assertions} != set(expected))
    )
    if mismatch:
        classification = Classification.TEST_DEFECT
        reason = "The execution artifact contradicts its test identity, expected assertion definitions, or reported pass status. This establishes a test/reporting inconsistency, not product behavior."
        action = "Repair the test/provider artifact inconsistency and rerun before judging the product."
    elif record.status == ExecutionStatus.ERROR and record.failure_category == FailureCategory.ENVIRONMENT_FAILURE and any(
        group.get("setup_stage") in {"reference_status", "readiness_status", "authentication_setup_status", "reset_status", "fixture_status"}
        and group.get(group["setup_stage"]) == "FAILED" for group in groups
    ):
        classification = Classification.ENVIRONMENT_FAILURE
        reason = "Normalized setup evidence establishes an unavailable runtime, reference, connection, or authentication prerequisite before behavioral evaluation."
        action = "Restore the required local runtime prerequisites and repeat the same TestSpec."
    elif record.status == ExecutionStatus.ERROR and record.failure_category == FailureCategory.DATA_FAILURE and any(
        group.get("setup_stage") in {"reset_status", "fixture_status"}
        and group.get(group["setup_stage"]) == "FAILED" for group in groups
    ):
        classification = Classification.DATA_FAILURE
        reason = "Readiness completed, but deterministic reset or required fixture preparation failed verification. Product behavior was not established."
        action = "Restore the approved seed and fixture preconditions, then rerun."
        if not all(group.get("readiness_status") == "PASSED" for group in groups):
            classification, reason = Classification.UNKNOWN, "Data failure lacks supporting readiness evidence."
    elif record.failure_category == FailureCategory.UNSUPPORTED_BEHAVIOR and any(
        group.get("capability_status") == "UNSUPPORTED" for group in groups
    ):
        classification = Classification.UNSUPPORTED_BEHAVIOR
        reason = "Provider capability validation explicitly rejected the requested semantics before target execution."
        action = "Use supported semantics or separately implement and qualify the missing capability."
    elif record.status == ExecutionStatus.FAILED and record.failure_category == FailureCategory.ASSERTION_FAILURE:
        stages = ("capability_status", "readiness_status", "reset_status", "fixture_status", "setup_status")
        setup_ok = bool(groups) and all(all(group.get(stage) == "PASSED" for stage in stages) for group in groups)
        submit_ids = {step.step_id for step in spec.steps if step.action == SemanticAction.SUBMIT}
        reached_target = any(item.step_id in submit_ids and item.status == ResultStatus.PASSED for item in record.step_results)
        concrete = [item for item in failed if item.observed and any(ref.sha256 for ref in item.evidence_refs)]
        if setup_ok and reached_target and concrete and not any(item.status == ResultStatus.ERROR for item in record.step_results + assertions):
            classification = Classification.PRODUCT_DEFECT
            reason = (
                "Supported execution reached the target after verified readiness, reset, and fixture setup. "
                f"Assertion {concrete[0].assertion_id} contradicts the expected behavior: {concrete[0].observed}"
            )
            action = "Investigate the observed product behavior using the retained assertion evidence."
            failed = concrete
    elif record.status == ExecutionStatus.PASSED:
        reason = "No behavioral failure was observed in this execution; no defect classification is warranted."
        action = "Retain the healthy baseline evidence."

    selected = failed[0] if failed else None
    refs = record.evidence_refs + [ref for item in assertions for ref in item.evidence_refs]
    unique_refs = {ref.uri: ref for ref in refs}
    return TriageRecord(
        triage_id=uuid4().hex,
        execution_id=record.execution_id,
        test_id=record.test_id,
        classification=classification,
        summary=reason,
        expected_behavior_reference=selected.assertion_id if selected else None,
        observed_behavior_reference=f"assertion:{selected.assertion_id}" if selected else None,
        supporting_evidence_refs=list(unique_refs.values()),
        recommended_next_action=action,
        source_ids=record.source_ids,
        source_fingerprints=record.source_fingerprints,
        correlation_id=record.correlation_id,
        producer="autoqe-triage",
        producer_version="0.4.0",
        limitations=["Deterministic evidence classification; no inferred component-level root cause."],
    )
