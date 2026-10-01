"""Observational accounting over generic external results, never provider code."""

from autoqe_integration.contracts import ExternalEvaluationResult
from autoqe.metrics.evidence import MetricsEvidenceError
from autoqe.metrics.models import Metric


def validate_external_window(bundle):
    window = bundle.manifest.external_evaluation_window
    results = [item for item in bundle.artifacts.values() if isinstance(item, ExternalEvaluationResult)]
    if window is None:
        if results:
            raise MetricsEvidenceError("external results require an explicit planned window")
        return {}
    if window.project_id != bundle.manifest.project_id or window.window_id != bundle.manifest.window_id:
        raise MetricsEvidenceError("external window identity mismatch")
    planned = {item.evaluation_case_id: item for item in window.planned}
    found = {}
    for result in results:
        request = result.request
        key = request.evaluation_case_id
        if key in found:
            raise MetricsEvidenceError("duplicate external evaluation result")
        if key not in planned:
            raise MetricsEvidenceError("unplanned external evaluation result")
        expected = planned[key]
        if (request.project_id != window.project_id or request.window_id != window.window_id
                or request.evaluation_dimension != window.evaluation_dimension or result.provider_id != window.provider_id
                or request.qualification_only != expected.qualification_only or result.request_sha256 != expected.request_sha256):
            raise MetricsEvidenceError("external result contradicts planned identity")
        if result.status.startswith("COMPLETED_") and result.provider_revision != window.provider_revision:
            raise MetricsEvidenceError("completed external result has unqualified revision")
        found[key] = result
    return found


def external_pass_rate(bundle, *, provider_id, metric_id):
    window = bundle.manifest.external_evaluation_window
    definition = "Real completed triage-classification evaluations passing / real completed evaluations (pass or fail); available only for the complete planned window."
    if window is None or window.provider_id != provider_id:
        return Metric(metric_id=metric_id, definition=definition, availability="UNAVAILABLE", sample_size=0,
                      limitations=["No matching external evaluation dataset/result exists for this metrics window. M6 evidence is required."])
    found = validate_external_window(bundle)
    real = [item for item in window.planned if not item.qualification_only]
    rows = [found[item.evaluation_case_id] for item in real if item.evaluation_case_id in found]
    passed = [str(row.request.evaluation_case_id) for row in rows if row.status == "COMPLETED_PASS"]
    failed = [str(row.request.evaluation_case_id) for row in rows if row.status == "COMPLETED_FAIL"]
    missing = [str(item.evaluation_case_id) for item in real if item.evaluation_case_id not in found]
    errors = [str(row.request.evaluation_case_id) for row in rows if row.status == "ERROR"]
    incomplete = [str(row.request.evaluation_case_id) for row in rows if row.status == "INCOMPLETE"]
    completed = len(passed) + len(failed)
    available = bool(real) and completed == len(real)
    counts = dict(planned=len(real), attempted=sum(row.attempted for row in rows), completed=completed,
                  passed=len(passed), failed=len(failed), error=len(errors), incomplete=len(incomplete) + len(missing),
                  missing=len(missing), excluded_controls=sum(item.qualification_only for item in window.planned))
    return Metric(metric_id=metric_id, definition=definition, numerator=len(passed), denominator=completed,
                  value=len(passed) / completed if available else None, sample_size=completed,
                  availability="AVAILABLE" if available else "UNAVAILABLE", source_refs=sorted(bundle.sources),
                  details={**counts, "passed_ids": sorted(passed), "failed_ids": sorted(failed),
                           "error_ids": sorted(errors), "incomplete_ids": sorted(incomplete), "missing_ids": sorted(missing),
                           "dimension": window.evaluation_dimension, "provider_id": provider_id},
                  limitations=["Classification agreement only; not rationale, semantic quality or release readiness."] +
                              ([] if available else ["The real planned window is empty or not completely evaluated; partial success is unavailable."]))
