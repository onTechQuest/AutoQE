from datetime import datetime, timezone
from time import perf_counter
from uuid import uuid4

from autoqe.contracts.execution_record import (
    AssertionResult,
    ExecutionRecord,
    ExecutionStatus,
    FailureCategory,
    ResultStatus,
)
from autoqe.contracts.project_profile import ProjectProfile
from autoqe.contracts.test_spec import TestLayer, TestSpec
from autoqe.execution.records import make_execution_record, validate_completeness
from autoqe.execution.runtime import CheckedExecutionProvider, ExecutionSetupAdapter


class UnsupportedExecutionProviderError(ValueError):
    pass


def _combine_records(
    test_spec: TestSpec,
    project_profile: ProjectProfile,
    records: list[ExecutionRecord],
    reset_identity: str | None,
) -> ExecutionRecord:
    if len(records) != 2:
        raise ValueError("BOTH aggregation requires two provider records")
    records = [validate_completeness(test_spec, record) for record in records]
    statuses = {record.status for record in records}
    if ExecutionStatus.ERROR in statuses:
        status = ExecutionStatus.ERROR
    elif ExecutionStatus.FAILED in statuses:
        status = ExecutionStatus.FAILED
    elif ExecutionStatus.INCOMPLETE in statuses:
        status = ExecutionStatus.INCOMPLETE
    elif statuses == {ExecutionStatus.SKIPPED}:
        status = ExecutionStatus.SKIPPED
    elif statuses == {ExecutionStatus.PASSED}:
        status = ExecutionStatus.PASSED
    else:
        status = ExecutionStatus.INCOMPLETE

    assertions_by_id: dict[str, list[AssertionResult]] = {}
    for record in records:
        for assertion in record.assertion_results:
            assertions_by_id.setdefault(assertion.assertion_id, []).append(assertion)

    combined_assertions = []
    for assertion_id, assertions in assertions_by_id.items():
        assertion_statuses = {item.status for item in assertions}
        if ResultStatus.ERROR in assertion_statuses:
            assertion_status = ResultStatus.ERROR
        elif ResultStatus.FAILED in assertion_statuses:
            assertion_status = ResultStatus.FAILED
        elif assertion_statuses == {ResultStatus.SKIPPED}:
            assertion_status = ResultStatus.SKIPPED
        elif assertion_statuses == {ResultStatus.PASSED} and len(assertions) == len(records):
            assertion_status = ResultStatus.PASSED
        else:
            assertion_status = ResultStatus.UNKNOWN
        combined_assertions.append(
            AssertionResult(
                assertion_id=assertion_id,
                status=assertion_status,
                expected=assertions[0].expected,
                observed=" | ".join(
                    f"{record.provider}: {assertion.observed or assertion.status.value}"
                    for record in records
                    for assertion in record.assertion_results
                    if assertion.assertion_id == assertion_id
                ),
                evidence_refs=[ref for assertion in assertions for ref in assertion.evidence_refs],
            )
        )

    failure_category = None
    if status == ExecutionStatus.ERROR:
        failure_category = next(
            (record.failure_category for record in records if record.status == ExecutionStatus.ERROR and record.failure_category),
            FailureCategory.UNKNOWN,
        )
    elif status == ExecutionStatus.FAILED:
        failure_category = FailureCategory.ASSERTION_FAILURE

    first = min(record.started_at for record in records)
    last = max(record.completed_at or record.started_at for record in records)
    return ExecutionRecord(
        execution_id=uuid4().hex,
        test_id=test_spec.test_id,
        project_id=test_spec.project_id,
        provider="+".join(record.provider for record in records),
        provider_version=";".join(f"{record.provider}={record.provider_version}" for record in records),
        status=status,
        started_at=first,
        completed_at=last,
        duration_ms=sum(record.duration_ms or 0 for record in records),
        step_results=[
            step.model_copy(update={"observed": f"{record.provider}: {step.observed or step.status.value}"})
            for record in records for step in record.step_results
        ],
        assertion_results=combined_assertions,
        observed_outcomes=[f"{record.provider}: {item}" for record in records for item in record.observed_outcomes],
        evidence_refs=[ref for record in records for ref in record.evidence_refs],
        failure_category=failure_category,
        environment_identity={
            f"provider-{index}.{key}": value
            for index, record in enumerate(records, start=1)
            for key, value in record.environment_identity.items()
        },
        test_data_reset_identity=reset_identity,
        source_ids=test_spec.source_ids,
        source_fingerprints=test_spec.source_fingerprints,
        correlation_id=test_spec.correlation_id,
        producer="autoqe-execution",
        producer_version="0.3.0",
        limitations=list(dict.fromkeys(
            list(test_spec.limitations) + [item for record in records for item in record.limitations]
        )),
    )


def _execute_single_provider(
    test_spec: TestSpec,
    project_profile: ProjectProfile,
    project_adapter: ExecutionSetupAdapter,
    provider: CheckedExecutionProvider,
) -> tuple[ExecutionRecord, str | None]:
    started_at = datetime.now(timezone.utc)
    started_clock = perf_counter()
    errors = provider.capability_errors(test_spec)
    if errors or not provider.supports(test_spec):
        return (
            make_execution_record(
                test_spec,
                project_profile,
                provider.provider_name,
                provider.provider_version,
                ExecutionStatus.SKIPPED,
                started_at,
                started_clock,
                observed_outcomes=list(errors) or ["Execution provider does not support the requested TestSpec."],
                failure_category=FailureCategory.UNSUPPORTED_BEHAVIOR,
            ),
            None,
        )
    try:
        setup = project_adapter.prepare_execution(test_spec, project_profile)
        record = provider.execute(test_spec, project_profile)
        record.environment_identity.update(setup.environment_identity)
        record.test_data_reset_identity = setup.reset_identity
        return validate_completeness(test_spec, record), setup.reset_identity
    except Exception as exc:
        category = FailureCategory.ENVIRONMENT_FAILURE if isinstance(exc, OSError) else FailureCategory.PROVIDER_ERROR
        record = make_execution_record(
            test_spec,
            project_profile,
            provider.provider_name,
            provider.provider_version,
            ExecutionStatus.ERROR,
            started_at,
            started_clock,
            observed_outcomes=[f"Project setup or provider failed with {type(exc).__name__}."],
            failure_category=category,
        )
        return record, None


def execute_test_spec(
    test_spec: TestSpec,
    project_profile: ProjectProfile,
    project_adapter: ExecutionSetupAdapter,
    execution_provider: CheckedExecutionProvider | tuple[CheckedExecutionProvider, CheckedExecutionProvider],
) -> ExecutionRecord:
    validated_spec = TestSpec.model_validate(test_spec.model_dump(mode="python"))
    validated_profile = ProjectProfile.model_validate(project_profile.model_dump(mode="python"))
    if validated_spec.project_id != validated_profile.project_id:
        raise ValueError("TestSpec and ProjectProfile project IDs do not match")

    if validated_spec.test_layer == TestLayer.BOTH:
        if (
            not isinstance(execution_provider, tuple)
            or len(execution_provider) != 2
            or {provider.execution_layer for provider in execution_provider} != {TestLayer.UI, TestLayer.API}
        ):
            raise UnsupportedExecutionProviderError("BOTH TestSpecs require a UI and API provider pair")
        records: list[ExecutionRecord] = []
        reset_identities: list[str] = []
        for provider in execution_provider:
            record, reset_identity = _execute_single_provider(
                validated_spec, validated_profile, project_adapter, provider
            )
            records.append(record)
            if reset_identity:
                reset_identities.append(reset_identity)
        combined_reset = ";".join(reset_identities) if reset_identities else validated_profile.environment.reset_identity
        return _combine_records(validated_spec, validated_profile, records, combined_reset)

    if isinstance(execution_provider, tuple):
        raise UnsupportedExecutionProviderError("Provider pairs are reserved for BOTH TestSpecs")
    record, _ = _execute_single_provider(
        validated_spec,
        validated_profile,
        project_adapter,
        execution_provider,
    )
    return record
