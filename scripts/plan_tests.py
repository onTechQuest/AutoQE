import argparse
import json
from pathlib import Path
import re
import sys

from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from autoqe.contracts.behavioral_contract import BehavioralContract
from autoqe.contracts.project_profile import ProjectProfile
from autoqe.planning.models import PlannerConfig
from autoqe.planning.service import PlanningError, plan_tests
from autoqe.providers.replay import ReplayModelProvider


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Plan grounded vendor-neutral TestSpecs offline.")
    parser.add_argument("--project-profile", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--provider", choices=("replay", "live"), default="replay")
    parser.add_argument("--max-tests", type=int, default=5)
    parser.add_argument("--output", type=Path, default=Path("reports/plans"))
    parser.add_argument("--replay-fixtures", type=Path, default=Path("examples/rwa/replays.json"))
    return parser


def _safe_component(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-.") or "plan"


def main() -> int:
    args = build_parser().parse_args()
    if args.provider == "live":
        print("Live model planning is not implemented in M2; no model call was made.", file=sys.stderr)
        return 2

    try:
        profile = ProjectProfile.model_validate_json(args.project_profile.read_text(encoding="utf-8"))
        contract = BehavioralContract.model_validate_json(args.contract.read_text(encoding="utf-8"))
        config = PlannerConfig(max_tests=args.max_tests)
        result = plan_tests(profile, contract, ReplayModelProvider(args.replay_fixtures), config)

        output_dir = args.output / _safe_component(contract.contract_id)
        output_dir.mkdir(parents=True, exist_ok=True)
        artifacts = []
        for index, test_spec in enumerate(result.test_specs, start=1):
            filename = f"testspec-{index:02d}-{_safe_component(test_spec.test_id)}.json"
            artifact_path = output_dir / filename
            artifact_path.write_text(
                json.dumps(test_spec.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            artifacts.append(str(artifact_path))
        summary_path = output_dir / "planning-summary.json"
        summary_path.write_text(
            json.dumps(result.summary.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    except ValidationError as exc:
        details = "; ".join(
            f"{'.'.join(str(part) for part in error['loc'])}: {error['type']}"
            for error in exc.errors(include_input=False)
        )
        print(f"Planning validation failed: {details}", file=sys.stderr)
        return 2
    except (OSError, PlanningError, ValueError, TypeError) as exc:
        print(f"Planning failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    output = {
        "artifact_directory": str(output_dir),
        "test_specs": [
            {"test_id": spec.test_id, "scenario_type": spec.scenario_type.value, "test_layer": spec.test_layer.value}
            for spec in result.test_specs
        ],
        "summary": result.summary.model_dump(mode="json"),
        "summary_artifact": str(summary_path),
        "spec_artifacts": artifacts,
    }
    print(json.dumps(output, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())