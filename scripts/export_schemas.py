import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from autoqe.contracts import (
    BehavioralContract,
    ExecutionRecord,
    ProjectProfile,
    TestSpec,
    TriageRecord,
)


def main() -> None:
    schema_dir = ROOT / "schemas"
    schema_dir.mkdir(exist_ok=True)
    models = {
        "project-profile": ProjectProfile,
        "behavioral-contract": BehavioralContract,
        "test-spec": TestSpec,
        "execution-record": ExecutionRecord,
        "triage-record": TriageRecord,
    }
    for name, model in models.items():
        schema = model.model_json_schema(mode="serialization")
        (schema_dir / f"{name}.schema.json").write_text(
            json.dumps(schema, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()