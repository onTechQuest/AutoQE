"""Deterministic observational calculators. This module never invokes runtime code."""

from collections import Counter

from autoqe.contracts import BehavioralContract, TestSpec
from autoqe.metrics.evidence import MetricsEvidenceBundle, MetricsEvidenceError
from autoqe.metrics.models import Metric, ModelUsage, QualityMetricsReport


def _ratio(bundle, metric_id, definition, included, eligible, *, details=None, limitations=()):
    included, eligible = sorted(included), sorted(eligible)
    if len(set(included)) != len(included) or len(set(eligible)) != len(eligible) or not set(included) <= set(eligible):
        raise MetricsEvidenceError(f"inconsistent numerator/denominator evidence: {metric_id}")
    return Metric(
        metric_id=metric_id, definition=definition, numerator=len(included), denominator=len(eligible),
        value=len(included) / len(eligible) if eligible else None, sample_size=len(eligible),
        availability="AVAILABLE" if eligible else "NOT_APPLICABLE",
        source_refs=sorted(bundle.sources),
        details={"numerator_ids": included, "denominator_ids": eligible, **(details or {})},
        limitations=list(limitations) + ([] if eligible else ["No eligible observations in this explicitly selected window."]),
    )


def requirement_traceability(bundle):
    contracts = {item.contract_id: item for item in bundle.artifacts.values() if isinstance(item, BehavioralContract)}
    requirements = {req for item in contracts.values() for req in item.requirement_ids}
    covered = set()
    for item in bundle.artifacts.values():
        if isinstance(item, TestSpec):
            contract = contracts.get(item.contract_id)
            if contract is None or not set(item.requirement_ids) <= set(contract.requirement_ids):
                raise MetricsEvidenceError("TestSpec references requirements outside selected contracts")
            covered.update(item.requirement_ids)
    return _ratio(bundle, "requirement_traceability", "Unique explicitly referenced requirement IDs / unique requirement IDs in selected BehavioralContracts.",
                  covered, requirements, details={"uncovered_requirement_ids": sorted(requirements - covered)},
                  limitations=["Identifier traceability only; not semantic or full behavioral coverage. Malformed specs cannot establish linkage."])


def schema_validity(bundle):
    selected = [key for key, ref in bundle.manifest.artifacts.items() if ref.kind == "spec"]
    return _ratio(bundle, "testspec_schema_validity", "Unique valid TestSpec inputs / all unique selected TestSpec inputs, including malformed JSON.",
                  [key for key in selected if key not in bundle.invalid_specs], selected,
                  details={"invalid_inputs": dict(sorted(bundle.invalid_specs.items()))})


def _setup_ready(record):
    if record is None:
        return False
    groups = {}
    for key, value in record.environment_identity.items():
        if key.startswith("provider-") and "." in key:
            group, field = key.split(".", 1)
        else:
            group, field = "single", key
        groups.setdefault(group, {})[field] = value
    if any(key.startswith("provider-") for key in groups):
        groups.pop("single", None)
    required = ("capability_status", "readiness_status", "setup_status")
    for group in groups.values():
        if any(group.get(key) != "PASSED" for key in required):
            return False
        # An overall setup success must not override a concrete failed stage.
        if any(value != "PASSED" for key, value in group.items()
               if key.endswith("_status") and key not in ("ui_status", "api_status")):
            return False
    return bool(groups)


def _meaningful_execution(spec, record):
    target_steps = {step.step_id for step in spec.steps if step.action in ("SUBMIT", "ASSERT", "WAIT_FOR_STATE")}
    assertion_steps = {step.step_id for step in spec.steps if step.action == "ASSERT"}
    return (
        any(item.step_id in target_steps and item.status == "PASSED" for item in record.step_results)
        or (any(item.step_id in assertion_steps and item.status == "FAILED" for item in record.step_results)
            and any(item.status == "FAILED" and item.observed for item in record.assertion_results))
    )


def _exclusion(bundle, case):
    spec, record = bundle.artifacts.get(case.spec), bundle.artifacts.get(case.execution)
    if not spec:
        return "missing_or_invalid_spec"
    if not record:
        return "missing_execution"
    if record.failure_category == "UNSUPPORTED_BEHAVIOR" or record.status == "SKIPPED":
        return "unsupported_or_skipped"
    if not _setup_ready(record):
        return "setup_or_capability_not_established"
    if record.status == "ERROR":
        return "execution_error"
    if record.status not in ("PASSED", "FAILED") or record.completed_at is None:
        return "nonterminal_or_incomplete"
    if record.status == "FAILED" and record.failure_category != "ASSERTION_FAILURE":
        return "non_assertion_failure"
    expected = {outcome.outcome_id: outcome.description for outcome in spec.expected_outcomes}
    actual = {assertion.assertion_id: assertion for assertion in record.assertion_results}
    if len(expected) != len(spec.expected_outcomes) or len(actual) != len(record.assertion_results) or actual.keys() != expected.keys():
        return "incomplete_or_duplicate_outcomes"
    if any(item.expected != expected[key] or item.status not in ("PASSED", "FAILED") for key, item in actual.items()):
        return "unresolved_or_inconsistent_outcomes"
    failures = [item for item in actual.values() if item.status == "FAILED"]
    if (record.status == "PASSED" and failures) or (record.status == "FAILED" and not failures):
        return "inconsistent_terminal_status"
    steps = {step.step_id for step in spec.steps}
    if len(steps) != len(spec.steps) or not record.step_results or any(item.step_id not in steps or item.status in ("ERROR", "UNKNOWN", "SKIPPED") for item in record.step_results):
        return "no_meaningful_provider_execution"
    if not _meaningful_execution(spec, record):
        return "no_meaningful_provider_execution"
    if record.status == "PASSED" and (steps != {item.step_id for item in record.step_results} or any(item.status != "PASSED" for item in record.step_results)):
        return "incomplete_steps"
    return None


def executability(bundle):
    cases = [case for case in bundle.manifest.cases if case.execution_attempted]
    exclusions = {case.case_id: reason for case in cases if (reason := _exclusion(bundle, case))}
    return _ratio(bundle, "test_executability", "Executable runtime evaluation attempts / runtime evaluation attempts; assertion failure can be executable.",
                  [case.case_id for case in cases if case.case_id not in exclusions], [case.case_id for case in cases],
                  details={"exclusions": exclusions, "exclusion_counts": dict(Counter(exclusions.values()))},
                  limitations=["Attempt-based, not unique-TestSpec or pass rate. Synthetic evidence fixtures excluded. Composite final outcomes are evaluated; interrupted component outcomes may be resolved by another provider."])


def healthy_false_positives(bundle):
    cases = [case for case in bundle.manifest.cases if case.target_state == "HEALTHY"]
    eligible, positives, exclusions = [], [], {}
    for case in cases:
        record, triage = bundle.artifacts.get(case.execution), bundle.artifacts.get(case.triage)
        if not _setup_ready(record) or record.failure_category in ("ENVIRONMENT_FAILURE", "DATA_FAILURE", "UNSUPPORTED_BEHAVIOR"):
            exclusions[case.case_id] = "readiness/setup/capability not successful or non-product setup failure"
            continue
        eligible.append(case.case_id)
        if (record.status == "FAILED" and record.failure_category == "ASSERTION_FAILURE") or (triage and triage.classification in ("PRODUCT_DEFECT", "TEST_DEFECT")):
            positives.append(case.case_id)
    return _ratio(bundle, "healthy_false_positive_rate", "Healthy cases signaling assertion/product/test failure / externally healthy cases with successful setup and supported semantics.",
                  positives, eligible, details={"exclusions": exclusions},
                  limitations=["Provider errors without product/test failure signals are not false positives; consult executability alongside this rate."])


def defect_detection(bundle):
    cases = [case for case in bundle.manifest.cases if case.target_state == "CONTROLLED_FAULT"]
    detected = []
    for case in cases:
        record, spec = bundle.artifacts.get(case.execution), bundle.artifacts.get(case.spec)
        if not record or not spec or not _setup_ready(record):
            continue
        if record.status != "FAILED" or record.failure_category != "ASSERTION_FAILURE" or record.completed_at is None:
            continue
        expected = {outcome.outcome_id: outcome.description for outcome in spec.expected_outcomes}
        assertions = record.assertion_results
        if len(expected) != len(spec.expected_outcomes) or len({item.assertion_id for item in assertions}) != len(assertions):
            continue
        if any(item.expected != expected.get(item.assertion_id) or item.status == "ERROR" for item in assertions):
            continue
        if any(item.status == "ERROR" for item in record.step_results) or not _meaningful_execution(spec, record):
            continue
        if any(
            item.status == "FAILED" and item.observed and any(ref.sha256 for ref in item.evidence_refs)
            for item in assertions
        ):
            detected.append(case.case_id)
    attempted = [case.case_id for case in cases]
    return _ratio(bundle, "controlled_defect_detection", "Controlled faults with successful setup, meaningful provider execution and a referenced observed assertion mismatch / controlled fault cases attempted.",
                  detected, attempted, details={"attempted_faults": sorted(attempted), "detected_faults": sorted(detected), "missed_faults": sorted(set(attempted) - set(detected))},
                  limitations=["Bounded external fault sample; no statistical generalization or root-cause inference. A concrete mismatch can detect a fault even when other outcomes remain unresolved; executability reports that incompleteness separately."])


def triage_accuracy(bundle):
    cases = [case for case in bundle.manifest.cases if case.expected_classification is not None]
    correct, comparisons, confusion, support = [], {}, {}, Counter()
    for case in cases:
        triage = bundle.artifacts.get(case.triage)
        expected = case.expected_classification.value
        actual = triage.classification.value if triage else "MISSING"
        support[expected] += 1
        row = confusion.setdefault(expected, {})
        row[actual] = row.get(actual, 0) + 1
        comparisons[case.case_id] = {"expected": expected, "actual": actual, "kind": case.kind}
        if expected == actual:
            correct.append(case.case_id)
    return _ratio(bundle, "triage_accuracy", "Actual classification matching external expected label / externally labeled triage cases, including missing results as incorrect.",
                  correct, [case.case_id for case in cases], details={"correct": len(correct), "incorrect": len(cases) - len(correct), "per_class_support": dict(support), "confusion_counts": confusion, "comparisons": comparisons},
                  limitations=["Small selected qualification sample; synthetic cases are explicitly identified, not observed application defects."])


def task_completion(bundle):
    complete, missing, counts = [], {}, Counter()
    for case in bundle.manifest.cases:
        stages = [stage for stage in case.required_stages if getattr(case, stage) not in bundle.artifacts]
        record = bundle.artifacts.get(case.execution)
        if "execution" in case.required_stages and record and (record.completed_at is None or record.status == "INCOMPLETE"):
            stages.append("execution")
        if stages:
            missing[case.case_id] = sorted(set(stages))
            counts.update(set(stages))
        else:
            complete.append(case.case_id)
    return _ratio(bundle, "task_completion", "Cases producing all explicitly required valid artifacts and terminal execution results / evaluation cases attempted.",
                  complete, [case.case_id for case in bundle.manifest.cases], details={"incomplete_stages": missing, "stage_incomplete_counts": dict(counts)},
                  limitations=["Completion is not correctness: PASSED, FAILED, ERROR and SKIPPED may be terminal; INCOMPLETE or missing completion timestamp is not. Synthetic triage-only tasks require only their declared stages."])


def model_usage(bundle):
    usage = next((item for item in bundle.artifacts.values() if isinstance(item, ModelUsage)), None)
    return Metric(metric_id="ai_token_usage", definition="Observed live model tokens for the explicitly bounded evidence window; no text-length estimation.",
                  value=(usage.live_model_tokens or 0) if usage else None, unit="tokens", sample_size=usage.live_model_calls if usage else 0,
                  availability="AVAILABLE" if usage else "UNAVAILABLE", source_refs=sorted(bundle.sources),
                  details={"live_model_calls": usage.live_model_calls if usage else None, "mode": usage.mode if usage else None},
                  limitations=[] if usage else ["No model usage telemetry or explicit no-live-processing attestation for this window."])


def agentguard(bundle):
    return Metric(metric_id="agentguard_pass_rate", definition="Passing independent AgentGuard evaluations / AgentGuard evaluations performed.",
                  availability="UNAVAILABLE", sample_size=0, source_refs=[],
                  limitations=["AgentGuard evaluation integration is planned for M6 and no AgentGuard evaluation dataset/result exists for this metrics window."])


def calculate_metrics(bundle: MetricsEvidenceBundle) -> QualityMetricsReport:
    calculators = (requirement_traceability, schema_validity, executability, healthy_false_positives, defect_detection,
                   triage_accuracy, task_completion, model_usage, agentguard)
    return QualityMetricsReport(project_id=bundle.manifest.project_id, window_id=bundle.manifest.window_id,
                                metrics=[calculator(bundle) for calculator in calculators], sources=bundle.sources,
                                limitations=["Observational metrics only; no aggregate score, thresholds, or release decision.",
                                             "External labels and no-live attestations are trusted qualification inputs; hashes identify bytes, not independent truth.",
                                             *bundle.manifest.limitations])
