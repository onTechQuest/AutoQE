"""Load only explicitly named local artifacts, retaining malformed TestSpecs."""

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from autoqe.contracts import BehavioralContract, ExecutionRecord, TestSpec, TriageRecord
from autoqe.contracts.common import _reject_sensitive_fields
from autoqe.metrics.models import MetricsManifest, ModelUsage


class MetricsEvidenceError(ValueError):
    """Safe diagnostic: never includes raw artifact values or validation inputs."""


@dataclass(frozen=True)
class MetricsEvidenceBundle:
    manifest: MetricsManifest
    artifacts: dict[str, Any]
    invalid_specs: dict[str, str]
    sources: dict[str, str]


def load_evidence(path: Path) -> MetricsEvidenceBundle:
    try:
        manifest_bytes = path.read_bytes()
        manifest = MetricsManifest.model_validate_json(manifest_bytes)
    except (OSError, ValueError):
        raise MetricsEvidenceError("missing or invalid metrics manifest") from None
    artifacts, invalid, sources = {}, {}, {"manifest": hashlib.sha256(manifest_bytes).hexdigest()}
    models = {"contract": BehavioralContract, "spec": TestSpec, "execution": ExecutionRecord, "triage": TriageRecord, "usage": ModelUsage}
    seen_paths = set()
    for key, ref in sorted(manifest.artifacts.items()):
        if key == "manifest":
            raise MetricsEvidenceError("reserved artifact identifier: manifest")
        resolved = (path.parent / ref.path).resolve()
        if resolved in seen_paths:
            raise MetricsEvidenceError(f"duplicate artifact path: {key}")
        seen_paths.add(resolved)
        try:
            content = resolved.read_bytes()
        except OSError:
            raise MetricsEvidenceError(f"missing referenced artifact: {key}") from None
        sources[key] = hashlib.sha256(content).hexdigest()
        try:
            raw = json.loads(content)
        except (ValueError, UnicodeError):
            if ref.kind == "spec":
                invalid[key] = "malformed JSON"
                continue
            raise MetricsEvidenceError(f"invalid JSON artifact: {key}") from None
        if isinstance(raw, dict) and "project_id" in raw and raw["project_id"] != manifest.project_id:
            raise MetricsEvidenceError(f"mixed project identity: {key}")
        if ref.kind == "qualification" and not isinstance(raw, dict):
            raise MetricsEvidenceError(f"qualification source must be a JSON object: {key}")
        if ref.kind == "qualification":
            try:
                _reject_sensitive_fields(raw)
            except ValueError:
                raise MetricsEvidenceError(f"unsafe qualification metadata: {key}") from None
        try:
            artifacts[key] = models[ref.kind].model_validate(raw) if ref.kind in models else raw
        except ValidationError:
            if ref.kind == "spec":
                invalid[key] = "frozen TestSpec schema validation failed"
                continue
            raise MetricsEvidenceError(f"invalid artifact schema: {key}") from None
    ids = [case.case_id for case in manifest.cases]
    if len(ids) != len(set(ids)):
        raise MetricsEvidenceError("duplicate qualification case IDs")
    contract_ids = [item.contract_id for item in artifacts.values() if isinstance(item, BehavioralContract)]
    if len(contract_ids) != len(set(contract_ids)):
        raise MetricsEvidenceError("duplicate selected contract identities")
    runtime_executions = []
    for case in manifest.cases:
        for stage in ("contract", "spec", "execution", "triage"):
            key = getattr(case, stage)
            if key and (key not in manifest.artifacts or manifest.artifacts[key].kind != stage):
                raise MetricsEvidenceError(f"missing or wrong artifact reference: {case.case_id}/{stage}")
        if case.label_source and (case.label_source not in manifest.artifacts or manifest.artifacts[case.label_source].kind != "qualification"):
            raise MetricsEvidenceError(f"missing qualification source: {case.case_id}")
        contract, spec, execution, triage = (artifacts.get(getattr(case, stage)) for stage in ("contract", "spec", "execution", "triage"))
        if case.execution_attempted and execution:
            runtime_executions.append(execution.execution_id)
        if spec and contract and (spec.contract_id != contract.contract_id or not set(spec.requirement_ids) <= set(contract.requirement_ids)):
            raise MetricsEvidenceError(f"contradictory contract linkage: {case.case_id}")
        if execution and spec and execution.test_id != spec.test_id:
            raise MetricsEvidenceError(f"contradictory execution linkage: {case.case_id}")
        if triage and (not execution or triage.execution_id != execution.execution_id or triage.test_id != execution.test_id):
            raise MetricsEvidenceError(f"contradictory triage linkage: {case.case_id}")
    if len(runtime_executions) != len(set(runtime_executions)):
        raise MetricsEvidenceError("duplicate runtime execution counted as separate attempts")
    for check in manifest.checks:
        try:
            value = artifacts[check.source]
            if hasattr(value, "model_dump"):
                value = value.model_dump(mode="json")
            if check.pointer and not check.pointer.startswith("/"):
                raise ValueError()
            for segment in check.pointer.split("/")[1:] if check.pointer else []:
                segment = segment.replace("~1", "/").replace("~0", "~")
                value = value[int(segment)] if isinstance(value, list) else value[segment]
            if value != check.expected or type(value) is not type(check.expected):
                raise ValueError()
        except (KeyError, IndexError, ValueError, TypeError):
            raise MetricsEvidenceError(f"contradictory external evidence check: {check.source}") from None
    usage = [item for item in artifacts.values() if isinstance(item, ModelUsage)]
    if len(usage) > 1:
        raise MetricsEvidenceError("multiple usage windows would double count telemetry")
    for item in usage:
        if item.window_id != manifest.window_id or item.source not in artifacts or manifest.artifacts[item.source].kind != "qualification":
            raise MetricsEvidenceError("usage window or supporting source mismatch")
        source = artifacts[item.source]
        if type(source.get("live_model_calls")) is not int or source["live_model_calls"] != item.live_model_calls:
            raise MetricsEvidenceError("usage call count contradicts supporting telemetry")
        if item.mode == "TELEMETRY" and (type(source.get("live_model_tokens")) is not int or source["live_model_tokens"] != item.live_model_tokens):
            raise MetricsEvidenceError("usage token count lacks matching source telemetry")
    return MetricsEvidenceBundle(manifest, artifacts, invalid, sources)
