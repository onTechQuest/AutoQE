import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from autoqe.contracts import ExecutionRecord, ProjectProfile, TestSpec
from autoqe.triage import triage_execution


def main() -> int:
    parser = argparse.ArgumentParser(description="Triage normalized AutoQE execution evidence offline.")
    parser.add_argument("--project-profile", type=Path, required=True)
    parser.add_argument("--test-spec", type=Path, required=True)
    parser.add_argument("--execution-record", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        profile = ProjectProfile.model_validate_json(args.project_profile.read_text(encoding="utf-8"))
        spec = TestSpec.model_validate_json(args.test_spec.read_text(encoding="utf-8"))
        execution = ExecutionRecord.model_validate_json(args.execution_record.read_text(encoding="utf-8"))
        result = triage_execution(profile, spec, execution)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(result.model_dump_json(indent=2) + "\n", encoding="utf-8")
        print(result.classification.value)
    except Exception as exc:
        print(f"Triage failed: {type(exc).__name__}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
