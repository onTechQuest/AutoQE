import json
from pathlib import Path
from typing import Mapping

from autoqe.interfaces.model_provider import ModelProvider


class UnknownReplayKeyError(LookupError):
    pass


class ReplayModelProvider(ModelProvider):
    def __init__(self, fixtures_path: str | Path) -> None:
        path = Path(fixtures_path).resolve(strict=True)
        self._fixtures = json.loads(path.read_text(encoding="utf-8"))

    def generate_structured(
        self,
        task: str,
        context: Mapping[str, object],
        output_schema: Mapping[str, object],
    ) -> Mapping[str, object]:
        schema_version = output_schema.get("properties", {}).get("schema_version", {})
        if output_schema.get("title") != "BehavioralContract" or schema_version.get("const") != "1.0":
            raise UnknownReplayKeyError("approved replay requires BehavioralContract schema version 1.0")
        project_id = context.get("project_id")
        source_ids = tuple(sorted(context.get("source_ids", ())))
        fingerprints = context.get("source_fingerprints")
        limitations = context.get("limitations")
        matches = [
            entry
            for entry in self._fixtures.get("replays", [])
            if entry.get("task") == task
            and entry.get("project_id") == project_id
            and tuple(sorted(entry.get("source_ids", ()))) == source_ids
            and entry.get("source_fingerprints") == fingerprints
            and entry.get("limitations") == limitations
        ]
        if len(matches) != 1:
            raise UnknownReplayKeyError(
                "no unique approved replay matches the task, project, source IDs, and fingerprints"
            )
        response = matches[0].get("response")
        if not isinstance(response, dict):
            raise ValueError("approved replay response must be a JSON object")
        return json.loads(json.dumps(response))