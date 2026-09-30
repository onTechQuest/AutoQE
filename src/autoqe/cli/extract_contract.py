import argparse
import json
from pathlib import Path
import sys

from pydantic import ValidationError

from autoqe.context import ContextBundle
from autoqe.contracts.project_profile import ProjectProfile
from autoqe.extraction.grounding import validate_contract_grounding
from autoqe.extraction.service import extract_behavioral_contract
from autoqe.providers.replay import ReplayModelProvider
from autoqe.requirements.markdown import MarkdownRequirementProvider


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Extract a grounded BehavioralContract from Markdown requirements.")
    parser.add_argument("--project-profile", type=Path, required=True)
    parser.add_argument("--requirements", type=Path, nargs="+", required=True)
    parser.add_argument("--provider", choices=("replay", "live"), required=True)
    parser.add_argument("--output", type=Path, default=Path("reports/contracts"))
    parser.add_argument("--replay-fixtures", type=Path, default=Path("examples/rwa/replays.json"))
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.provider == "live":
        print(
            "Live model provider is deferred in M1; no model call was made. Use --provider replay.",
            file=sys.stderr,
        )
        return 2

    project_root = Path.cwd().resolve()
    try:
        profile = ProjectProfile.model_validate_json(
            args.project_profile.read_text(encoding="utf-8")
        )
        source_provider = MarkdownRequirementProvider(profile, project_root)
        sources = source_provider.load(args.requirements)
        context = ContextBundle(project_id=profile.project_id, requirement_sources=sources)
        model_provider = ReplayModelProvider(args.replay_fixtures)
        contract = extract_behavioral_contract(profile, context, model_provider)
        quality = validate_contract_grounding(profile, context, contract)

        output_path = args.output
        if output_path.suffix.lower() != ".json":
            output_path = output_path / f"{contract.contract_id}.json"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(contract.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    except ValidationError as exc:
        details = "; ".join(
            f"{'.'.join(str(part) for part in error['loc'])}: {error['type']}"
            for error in exc.errors(include_input=False)
        )
        print(f"Contract validation failed: {details}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"Contract extraction failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    print(json.dumps({"artifact": str(output_path), **quality.model_dump(mode="json")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())