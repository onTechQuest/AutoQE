"""Qualify an external evaluator after artifact production, without a live target."""

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from autoqe_integration.contracts import ExternalEvaluationWindow, PlannedEvaluation, canonical_json
from autoqe_integration.providers.agentguard.provider import AgentGuardEvaluationProvider, QUALIFIED_REVISION
from qualification.m6.evidence import load_requests
from autoqe.metrics import calculate_metrics, load_evidence


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--expectations", type=Path, required=True)
    parser.add_argument("--evaluator-root", type=Path, required=True)
    parser.add_argument("--evaluator-python", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        requests = load_requests(args.evidence, args.expectations)
        provider = AgentGuardEvaluationProvider(evaluator_root=args.evaluator_root, python_executable=args.evaluator_python)
        # Never overwrite a previous qualification window.
        args.output.mkdir(parents=True, exist_ok=False)
        window = ExternalEvaluationWindow(
            project_id=requests[0].project_id, window_id=requests[0].window_id, provider_id="agentguard",
            provider_revision=QUALIFIED_REVISION, evaluation_dimension=requests[0].evaluation_dimension,
            planned=[PlannedEvaluation(evaluation_case_id=item.evaluation_case_id, request_sha256=item.sha256,
                                       qualification_only=item.qualification_only) for item in requests],
        )
        manifest = dict(project_id=window.project_id, window_id=window.window_id, artifacts={},
                        external_evaluation_window=window.model_dump(mode="json"))
        # Persist the intended population before invoking providers. Missing
        # results after interruption remain explicitly missing, not excluded.
        manifest_path = args.output / "metrics-manifest.json"
        manifest_path.write_text(canonical_json(manifest) + "\n", encoding="utf-8")
        controls = []
        for request in requests:
            result = provider.evaluate(request)
            filename = f"{request.evaluation_case_id}.json"
            (args.output / filename).write_text(result.stable_json(), encoding="utf-8")
            manifest["artifacts"][str(request.evaluation_case_id)] = dict(kind="external_evaluation", path=filename)
            manifest_path.write_text(canonical_json(manifest) + "\n", encoding="utf-8")
            if request.qualification_only:
                controls.append(dict(evaluation_case_id=str(request.evaluation_case_id), actual=request.actual_value,
                                     expected=request.expected_value, status=result.status))
        report = calculate_metrics(load_evidence(manifest_path))
        (args.output / "quality-metrics.json").write_text(report.stable_json(), encoding="utf-8")
        metric = next(item for item in report.metrics if item.metric_id == "agentguard_pass_rate")
        positive = [item for item in controls if item["expected"] == item["actual"] == "PRODUCT_DEFECT"]
        negative = [item for item in controls if item["expected"] == "PRODUCT_DEFECT" and item["actual"] == "DATA_FAILURE"]
        qualified = (len(positive) == len(negative) == 1 and positive[0]["status"] == "COMPLETED_PASS"
                     and negative[0]["status"] == "COMPLETED_FAIL" and metric.availability == "AVAILABLE")
        summary = dict(schema_version="1.0", result="PASS" if qualified else "FAIL", controls=controls,
                       real_population=metric.details, metric_availability=metric.availability, metric_value=metric.value,
                       live_model_calls=0, scope="triage_classification_agreement")
        (args.output / "qualification.json").write_text(canonical_json(summary) + "\n", encoding="utf-8")
        print(f"M6 qualification: {summary['result']}; real evaluations {metric.numerator}/{metric.denominator}; {metric.availability}")
        return 0 if qualified else 1
    except (OSError, ValueError):
        print("M6 qualification failed: invalid inputs or inaccessible output/environment", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
