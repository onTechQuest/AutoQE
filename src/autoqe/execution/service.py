from datetime import datetime, timezone
from time import perf_counter
from uuid import uuid4

from autoqe.adapters.rwa import RwaProjectAdapter
from autoqe.contracts.execution_record import (
    AssertionResult,
    ExecutionRecord,
    ExecutionStatus,
    FailureCategory,
    ResultStatus,
)
from autoqe.contracts.project_profile import ProjectProfile
from autoqe.contracts.test_spec import TestLayer, TestSpec
from autoqe.execution.api_provider import ApiExecutionProvider
from autoqe.execution.playwright_provider import PlaywrightExecutionProvider
from autoqe.execution.records import make_execution_record


class UnsupportedExecutionProviderError(ValueError):
    pass


def _combine_records(
    test_spec: TestSpec,
    project_profile: ProjectProfile,
    records: list[ExecutionRecord],
    reset_identity: str | None,
) -> ExecutionRecord:
    statuses = {record.status for record in records}
    if ExecutionStatus.ERROR in statuses:
        status = ExecutionStatus.ERROR
    elif ExecutionStatus.FAILED in statuses:
        status = ExecutionStatus.FAILED
    elif all(record.status == ExecutionStatus.SKIPPED for record in records):
        status = ExecutionStatus.SKIPPED
    else:
        status = ExecutionStatus.PASSED

    assertions_by_id: dict[str, list[AssertionResult]] = {}
    for record in records:
        for assertion in record.assertion_results:
            assertions_by_id.setdefault(assertion.assertion_id, []).append(assertion)

    combined_assertions = []
    for assertion_id, assertions in assertions_by_id.items():
        assertion_statuses = {item.status for item in assertions}
        if ResultStatus.FAILED in assertion_statuses:
            assertion_status = ResultStatus.FAILED
        elif ResultStatus.ERROR in assertion_statuses:
            assertion_status = ResultStatus.ERROR
        elif all(item.status == ResultStatus.SKIPPED for item in assertions):
            assertion_status = ResultStatus.SKIPPED
        else:
            assertion_status = ResultStatus.PASSED
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
            (record.failure_category for record in records if record.failure_category),
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
        provider="playwright+httpx",
        provider_version=f"playwright={PlaywrightExecutionProvider.provider_version};httpx={ApiExecutionProvider.provider_version}",
        status=status,
        started_at=first,
        completed_at=last,
        duration_ms=sum(record.duration_ms or 0 for record in records),
        step_results=[step for record in records for step in record.step_results],
        assertion_results=combined_assertions,
        observed_outcomes=[f"{record.provider}: {item}" for record in records for item in record.observed_outcomes],
        evidence_refs=[ref for record in records for ref in record.evidence_refs],
        failure_category=failure_category,
        environment_identity=records[0].environment_identity,
        test_data_reset_identity=reset_identity,
        source_ids=test_spec.source_ids,
        source_fingerprints=test_spec.source_fingerprints,
        correlation_id=test_spec.correlation_id,
        producer="autoqe-execution",
        producer_version="0.3.0",
        limitations=list(test_spec.limitations),
    )


def _execute_single_provider(
    test_spec: TestSpec,
    project_profile: ProjectProfile,
    project_adapter: RwaProjectAdapter,
    provider: PlaywrightExecutionProvider | ApiExecutionProvider,
) -> tuple[ExecutionRecord, str | None]:
    started_at = datetime.now(timezone.utc)
    started_clock = perf_counter()
    if not provider.supports(test_spec):
        return (
            make_execution_record(
                test_spec,
                project_profile,
                type(provider).__name__,
                provider.provider_version,
                ExecutionStatus.SKIPPED,
                started_at,
                started_clock,
                observed_outcomes=["Execution provider does not support the requested TestSpec."],
            ),
            None,
        )
    try:
        checkout = project_adapter.verify_reference_checkout(project_profile)
        ready = project_adapter.verify_ready(project_profile)
        project_adapter.authenticate_if_needed(project_profile)
        reset = project_adapter.reset_environment(project_profile)
        data_requirements = tuple(test_spec.test_data_requirements)
        if test_spec.contract_id == "contract-transaction-history-001":
            data_requirements += ("rwa.history.baseline",)
        setup = project_adapter.setup_test_data(project_profile, data_requirements)
        record = provider.execute(test_spec, project_profile)
        record.environment_identity.update(checkout)
        record.environment_identity.update(ready)
        record.environment_identity.update(setup)
        return record, reset.get("reset_identity")
    except (OSError, RuntimeError, ValueError) as exc:
        category = FailureCategory.ENVIRONMENT_FAILURE if isinstance(exc, OSError) else FailureCategory.PROVIDER_ERROR
        record = make_execution_record(
            test_spec,
            project_profile,
            type(provider).__name__,
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
    project_adapter: RwaProjectAdapter,
    execution_provider: (
        PlaywrightExecutionProvider
        | ApiExecutionProvider
        | tuple[PlaywrightExecutionProvider, ApiExecutionProvider]
    ),
) -> ExecutionRecord:
    validated_spec = TestSpec.model_validate(test_spec.model_dump(mode="python"))
    validated_profile = ProjectProfile.model_validate(project_profile.model_dump(mode="python"))
    if validated_spec.project_id != validated_profile.project_id:
        raise ValueError("TestSpec and ProjectProfile project IDs do not match")

    if validated_spec.test_layer == TestLayer.BOTH:
        if (
            not isinstance(execution_provider, tuple)
            or len(execution_provider) != 2
            or not isinstance(execution_provider[0], PlaywrightExecutionProvider)
            or not isinstance(execution_provider[1], ApiExecutionProvider)
            or not execution_provider[0].supports(validated_spec)
            or not execution_provider[1].supports(validated_spec)
        ):
            raise UnsupportedExecutionProviderError("BOTH TestSpecs require the supported Playwright and httpx provider pair")
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