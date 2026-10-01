"""Report metrics from explicit local evidence without invoking AutoQE runtime."""

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from autoqe.metrics import MetricsEvidenceError, calculate_metrics, load_evidence


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-manifest", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        report = calculate_metrics(load_evidence(args.evidence_manifest))
        args.output.mkdir(parents=True, exist_ok=True)
        destination = args.output / "quality-metrics.json"
        destination.write_text(report.stable_json(), encoding="utf-8")
        for metric in report.metrics:
            result = f"{metric.numerator}/{metric.denominator}" if metric.unit == "ratio" else str(metric.value)
            print(f"{metric.metric_id}: {result if metric.availability == 'AVAILABLE' else metric.availability} (n={metric.sample_size})")
    except MetricsEvidenceError as exc:
        print(f"Metrics evidence rejected: {exc}", file=sys.stderr)
        return 2
    except (OSError, ValueError):
        print("Metrics report failed: invalid report or inaccessible output", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
