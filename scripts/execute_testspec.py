import argparse
import json
from pathlib import Path
import re
import sys

from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from autoqe.adapters.rwa import RwaProjectAdapter
from autoqe.contracts.project_profile import ProjectProfile
from autoqe.contracts.test_spec import TestLayer, TestSpec
from autoqe.execution.api_provider import ApiExecutionProvider
from autoqe.execution.playwright_provider import PlaywrightExecutionProvider
from autoqe.execution.service import execute_test_spec


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Execute one approved RWA TestSpec locally.")
    parser.add_argument("--project-profile", type=Path, required=True)
    parser.add_argument("--test-spec", type=Path, required=True)
    parser.add_argument("--provider", choices=("playwright", "api"), required=True)
    parser.add_argument("--rwa-root", type=Path, default=Path(r"C:\Projects\autoqe-reference-rwa"))
    parser.add_argument("--output", type=Path, default=Path("reports/executions"))
    return parser


def _safe_component(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-.") or "execution"


def main() -> int:
    args = build_parser().parse_args()
    try:
        project_profile = ProjectProfile.model_validate_json(args.project_profile.read_text(encoding="utf-8"))
        test_spec = TestSpec.model_validate_json(args.test_spec.read_text(encoding="utf-8"))
        project_adapter = RwaProjectAdapter(args.rwa_root)
        if test_spec.test_layer == TestLayer.BOTH:
            provider = (
                PlaywrightExecutionProvider(project_adapter),
                ApiExecutionProvider(project_adapter),
            )
        elif args.provider == "playwright":
            provider = PlaywrightExecutionProvider(project_adapter)
        else:
            provider = ApiExecutionProvider(project_adapter)

        record = execute_test_spec(
            test_spec,
            project_profile,
            project_adapter,
            provider,
        )
        output_dir = args.output / _safe_component(test_spec.test_id)
        output_dir.mkdir(parents=True, exist_ok=True)
        artifact_path = output_dir / f"execution-{record.execution_id}.json"
        artifact_path.write_text(
            json.dumps(record.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    except ValidationError as exc:
        details = "; ".join(
            f"{'.'.join(str(part) for part in error['loc'])}: {error['type']}"
            for error in exc.errors(include_input=False)
        )
        print(f"Execution input validation failed: {details}", file=sys.stderr)
        return 2
    except (OSError, RuntimeError, ValueError, TypeError) as exc:
        print(f"Execution failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    print(
        json.dumps(
            {
                "execution_id": record.execution_id,
                "test_id": record.test_id,
                "provider": record.provider,
                "status": record.status.value,
                "duration_ms": record.duration_ms,
                "assertion_results": [
                    {"assertion_id": result.assertion_id, "status": result.status.value}
                    for result in record.assertion_results
                ],
                "artifact": str(artifact_path),
            },
            indent=2,
        )
    )
    return 0 if record.status.value == "PASSED" else 1


if __name__ == "__main__":
    raise SystemExit(main())