import hashlib
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from qualification.m4.harness import MANIFEST, IsolatedTarget, audit_runtime, worker_environment
from autoqe.contracts import TestSpec as Spec, BehavioralContract
from autoqe.planning.service import plan_tests
from autoqe.providers.replay import ReplayModelProvider
from test_execution import load_profile


def test_exactly_three_external_profiles_and_committed_specs_match_approved_planning():
    assert len(MANIFEST["profiles"]) == 3
    assert len({profile["id"] for profile in MANIFEST["profiles"]}) == 3
    contract = BehavioralContract.model_validate_json((ROOT / "examples/rwa/plans/contracts/payment.json").read_text())
    plans = plan_tests(load_profile(), contract, ReplayModelProvider(ROOT / "examples/rwa/replays.json"))
    for profile in MANIFEST["profiles"]:
        spec = Spec.model_validate_json((ROOT / profile["test_spec"]).read_text())
        expected = next(item for item in plans.test_specs if item.test_id == spec.test_id)
        assert spec.model_dump(exclude={"created_at"}) == expected.model_dump(exclude={"created_at"})
        assert profile["cleanup"] and profile["purpose"] and profile["expected_classification"] == "PRODUCT_DEFECT"


def test_one_patch_per_disposable_target_and_canonical_preservation(tmp_path):
    canonical = tmp_path / "canonical"
    canonical.mkdir()
    marker = canonical / "untouched.txt"
    marker.write_text("canonical reference")
    before = hashlib.sha256(marker.read_bytes()).hexdigest()
    target = IsolatedTarget(canonical, tmp_path / "targets", Path("unused"))
    profile = MANIFEST["profiles"][0]
    patch_file = target.path / profile["file"]
    patch_file.parent.mkdir(parents=True)
    patch_file.write_text(profile["before"] + "\n")
    target.apply(profile)
    changed = patch_file.read_bytes()
    assert profile["after"] in patch_file.read_text()
    with pytest.raises(RuntimeError, match="Only one"):
        target.apply(MANIFEST["profiles"][1])
    assert patch_file.read_bytes() == changed
    assert hashlib.sha256(marker.read_bytes()).hexdigest() == before


def test_patch_requires_unique_pinned_source_and_registered_operation(tmp_path):
    target = IsolatedTarget(tmp_path / "canonical", tmp_path / "targets", Path("unused"))
    profile = MANIFEST["profiles"][1]
    patch_file = target.path / profile["file"]
    patch_file.parent.mkdir(parents=True)
    patch_file.write_text(profile["before"] * 2)
    with pytest.raises(RuntimeError, match="unique"):
        target.apply(profile)
    with pytest.raises(ValueError, match="Unregistered"):
        target.apply({**profile, "file": "../../canonical/backend.ts"})


def test_cleanup_is_bounded_and_idempotent_and_runs_on_exception(tmp_path, monkeypatch):
    target = IsolatedTarget(tmp_path / "canonical", tmp_path / "targets", Path("unused"))
    target.path.mkdir(parents=True)
    target.created = True
    calls = []
    def git(_reference, *args):
        calls.append(args)
        assert args[:3] == ("worktree", "remove", "--force")
        assert Path(args[3]) == target.path
        target.path.rmdir()
        return ""
    monkeypatch.setattr("qualification.m4.harness.git", git)
    target.__exit__(RuntimeError, RuntimeError("test"), None)
    target.close()
    assert len(calls) == 1 and not target.path.exists()
    target.path = target.reference
    with pytest.raises(RuntimeError, match="Unsafe"):
        target.close()


def test_worker_environment_excludes_controller_metadata(monkeypatch, tmp_path):
    monkeypatch.setenv("ACTIVE_FAULT_PROFILE", MANIFEST["profiles"][0]["id"])
    monkeypatch.setenv("EXPECTED_CLASSIFICATION", "PRODUCT_DEFECT")
    monkeypatch.setenv("RWA_TEST_PASSWORD", "unit-private-value")
    env = worker_environment(tmp_path)
    assert "ACTIVE_FAULT_PROFILE" not in env and "EXPECTED_CLASSIFICATION" not in env
    assert "RWA_TEST_PASSWORD" not in env
    assert all(profile["id"] not in json.dumps(env) for profile in MANIFEST["profiles"])


@pytest.mark.parametrize("content", [
    {"password": "unit-private-value"},
    {"observed": "unit-private-value"},
    {"source": MANIFEST["profiles"][0]["id"]},
    {"response_body": {"data": "raw"}},
])
def test_runtime_artifact_audit_rejects_secrets_or_controller_identity(tmp_path, content):
    (tmp_path / "opaque.json").write_text(json.dumps(content))
    with pytest.raises(RuntimeError):
        audit_runtime(tmp_path, "unit-private-value")


def test_normal_runtime_evidence_has_no_controller_identity(tmp_path):
    (tmp_path / "opaque.json").write_text(json.dumps({"observed": {"amount_minor": 3500, "state": "complete"}}))
    audit_runtime(tmp_path, "unit-private-value")
