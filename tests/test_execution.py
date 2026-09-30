from datetime import datetime, timezone
import json
import hashlib
from pathlib import Path
import re
import shutil
import subprocess
from time import perf_counter

import pytest
from pydantic import ValidationError

from autoqe.adapters.rwa import RWA_REVISION, RwaProjectAdapter, RwaTestActors
from autoqe.contracts import ProjectProfile
from autoqe.contracts.common import EvidenceReference
from autoqe.contracts.execution_record import (
    AssertionResult,
    ExecutionRecord,
    ExecutionStatus,
    FailureCategory,
    ResultStatus,
    StepResult,
)
from autoqe.contracts.test_spec import SemanticAction, SemanticStep
from autoqe.contracts.test_spec import TestSpec as AutoQETestSpec
from autoqe.execution.actions import RwaOperation, RwaSemanticActionResolver, UnsupportedSemanticActionError
from autoqe.execution.api_provider import ApiExecutionProvider
from autoqe.execution.playwright_provider import PlaywrightExecutionProvider
from autoqe.execution.records import make_execution_record
from autoqe.execution.service import (
    UnsupportedExecutionProviderError,
    _combine_records,
    execute_test_spec,
)

ROOT = Path(__file__).resolve().parents[1]


def load_profile() -> ProjectProfile:
    return ProjectProfile.model_validate_json(
        (ROOT / "examples/rwa/project-profile.json").read_text(encoding="utf-8")
    )


def load_spec(filename: str) -> AutoQETestSpec:
    return AutoQETestSpec.model_validate_json(
        (ROOT / "reports/plans/contract-payment-valid-001" / filename).read_text(encoding="utf-8")
    )


def make_record(spec: AutoQETestSpec, provider: str, status: ExecutionStatus) -> ExecutionRecord:
    now = datetime.now(timezone.utc)
    return make_execution_record(
        spec,
        load_profile(),
        provider,
        "test-version",
        status,
        now,
        perf_counter(),
        step_results=[StepResult(step_id=spec.steps[0].step_id, status=ResultStatus.PASSED)],
        assertion_results=[
            AssertionResult(
                assertion_id="payment-recorded-once",
                status=ResultStatus.PASSED,
                expected="A transaction is present exactly once.",
                observed=f"observed-by-{provider}",
            )
        ],
        evidence_refs=[
            EvidenceReference(
                kind="API_RESULT_METADATA",
                uri=f"reports/evidence/{provider}.json",
            )
        ],
        failure_category=(
            FailureCategory.ASSERTION_FAILURE
            if status == ExecutionStatus.FAILED
            else FailureCategory.ENVIRONMENT_FAILURE
            if status == ExecutionStatus.ERROR
            else None
        ),
    )


def test_semantic_action_allowlist_resolves_only_registered_targets() -> None:
    actors = RwaTestActors("sender-id", "sender", "Test", "Sender", "receiver-id", "receiver", "Test", "Receiver")
    resolver = RwaSemanticActionResolver()
    auth = resolver.resolve(
        SemanticStep(step_id="auth-1", action=SemanticAction.AUTHENTICATE, target="sender"),
        actors,
    )
    assert auth.operation == RwaOperation.AUTHENTICATE
    assert auth.actor_role == "sender"

    payment = resolver.resolve(
        SemanticStep(
            step_id="amount-1",
            action=SemanticAction.ENTER_VALUE,
            target="positive payment amount",
            data_ref="payment-amount",
        ),
        actors,
    )
    assert payment.amount == 35
    assert payment.description == "AutoQE M3 payment qualification"

    with pytest.raises(UnsupportedSemanticActionError):
        resolver.resolve(
            SemanticStep(step_id="unknown-1", action=SemanticAction.NAVIGATE, target="arbitrary route"),
            actors,
        )
    with pytest.raises(UnsupportedSemanticActionError):
        resolver.resolve(
            SemanticStep(
                step_id="amount-2",
                action=SemanticAction.ENTER_VALUE,
                target="amount",
                value="__import__('os').system('whoami')",
            ),
            actors,
        )


def test_adapter_enforces_pinned_profile_and_loopback_only() -> None:
    adapter = RwaProjectAdapter()
    profile = load_profile()
    ui, api = adapter.base_urls(profile)
    assert ui == "http://localhost:3000"
    assert api == "http://localhost:3001"
    assert profile.reference_target.revision == RWA_REVISION
    with pytest.raises(ValueError, match="127.0.0.1"):
        adapter._loopback_base_url("http://192.168.1.4:3000")


def test_adapter_reset_uses_existing_seed_endpoint(tmp_path) -> None:
    calls = []
    database_dir = tmp_path / "data"
    database_dir.mkdir()
    seed_bytes = b'{"users":[]}\n'
    (database_dir / "database.json").write_bytes(seed_bytes)
    (database_dir / "database-seed.json").write_bytes(seed_bytes)
    profile_data = load_profile().model_dump(mode="json")
    profile_data["environment"]["reset_identity"] = "sha256:" + hashlib.sha256(seed_bytes).hexdigest()
    profile = ProjectProfile.model_validate(profile_data)

    class FakeResponse:
        status_code = 200

    class FakeClient:
        def __init__(self, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def post(self, url):
            calls.append(url)
            return FakeResponse()

    adapter = RwaProjectAdapter(rwa_root=tmp_path, http_client_factory=FakeClient)
    reset = adapter.reset_environment(profile)
    assert calls == ["http://localhost:3001/testData/seed"]
    assert reset["reset_adapter"] == "rwa.testData.seed"
    assert reset["reset_identity"] == profile.environment.reset_identity


def test_adapter_actor_setup_reads_only_safe_fixture_fields() -> None:
    class FakeResponse:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {
                "results": [
                    {"id": "user-1", "username": "sender", "firstName": "Test", "lastName": "Sender", "password": "must-not-copy"},
                    {"id": "user-2", "username": "receiver", "firstName": "Test", "lastName": "Receiver", "password": "must-not-copy"},
                ]
            }

    class FakeClient:
        def __init__(self, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def get(self, _url):
            return FakeResponse()

    adapter = RwaProjectAdapter(http_client_factory=FakeClient)
    result = adapter.setup_test_data(load_profile(), ("recipient account",))
    assert result["actor_count"] == "2"
    assert adapter.actors.sender_username == "sender"
    assert "password" not in adapter.actors.__dict__
    assert "must-not-copy" not in json.dumps(result)


def test_adapter_creates_history_fixture_only_when_named(monkeypatch) -> None:
    calls = []

    class FakeResponse:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {
                "results": [
                    {"id": "user-1", "username": "sender", "firstName": "Test", "lastName": "Sender"},
                    {"id": "user-2", "username": "receiver", "firstName": "Test", "lastName": "Receiver"},
                ]
            }

    class FakeClient:
        def __init__(self, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def get(self, url):
            calls.append(("GET", url))
            return FakeResponse()

        def post(self, url, json=None):
            calls.append(("POST", url, dict(json or {})))
            return FakeResponse()

    monkeypatch.setenv("RWA_TEST_PASSWORD", "synthetic-test-password")
    adapter = RwaProjectAdapter(http_client_factory=FakeClient)
    result = adapter.setup_test_data(load_profile(), ("rwa.history.baseline",))
    assert result["history_fixture_created"] == "true"
    assert [call[0] for call in calls] == ["GET", "POST", "POST"]
    assert calls[1][2]["password"] == "synthetic-test-password"
    assert "password" not in calls[2][2]
    assert "synthetic-test-password" not in json.dumps(result)


def test_adapter_credentials_are_environment_only(monkeypatch) -> None:
    adapter = RwaProjectAdapter()
    monkeypatch.delenv("RWA_TEST_PASSWORD", raising=False)
    with pytest.raises(ValueError, match="environment variable"):
        adapter.authenticate_if_needed(load_profile())


def test_api_actor_resolution_is_allowlisted() -> None:
    actors = RwaTestActors("sender-id", "sender", "Test", "Sender", "receiver-id", "receiver", "Test", "Receiver")
    assert ApiExecutionProvider._actor_for_role(actors, "sender") == {
        "id": "sender-id",
        "username": "sender",
    }
    assert ApiExecutionProvider._actor_for_role(actors, "recipient") == {
        "id": "receiver-id",
        "username": "receiver",
    }
    with pytest.raises(ValueError, match="unsupported RWA actor"):
        ApiExecutionProvider._actor_for_role(actors, "arbitrary")


def test_providers_enforce_supported_layers_and_allowlisted_steps() -> None:
    adapter = RwaProjectAdapter()
    ui_provider = PlaywrightExecutionProvider(adapter)
    api_provider = ApiExecutionProvider(adapter)
    ui_spec = load_spec("testspec-01-contract-payment-valid-001-positive.json")
    api_spec = load_spec("testspec-02-contract-payment-valid-001-negative.json")
    assert ui_provider.supports(ui_spec)
    assert not ui_provider.supports(api_spec)
    assert api_provider.supports(api_spec)
    assert api_provider.supports(ui_spec)

    unknown = ui_spec.model_copy(update={"steps": [SemanticStep(step_id="unknown", action="RESET", target="arbitrary")]})
    assert not ui_provider.supports(unknown)


def test_both_layer_requires_exact_playwright_and_httpx_provider_pair() -> None:
    both_spec = load_spec("testspec-01-contract-payment-valid-001-positive.json")
    adapter = RwaProjectAdapter()
    with pytest.raises(UnsupportedExecutionProviderError, match="provider pair"):
        execute_test_spec(
            both_spec,
            load_profile(),
            adapter,
            PlaywrightExecutionProvider(adapter),
        )


def test_composite_both_merges_assertions_and_evidence_truthfully() -> None:
    spec = load_spec("testspec-01-contract-payment-valid-001-positive.json")
    ui_record = make_record(spec, "playwright", ExecutionStatus.PASSED)
    api_record = make_record(spec, "httpx", ExecutionStatus.PASSED)
    composite = _combine_records(spec, load_profile(), [ui_record, api_record], "seed-identity")
    assert composite.provider == "playwright+httpx"
    assert composite.status == ExecutionStatus.PASSED
    assert len(composite.assertion_results) == 1
    assert "playwright:" in composite.assertion_results[0].observed
    assert "httpx:" in composite.assertion_results[0].observed
    assert {evidence.uri for evidence in composite.evidence_refs} == {
        "reports/evidence/playwright.json",
        "reports/evidence/httpx.json",
    }
    assert composite.test_data_reset_identity == "seed-identity"


def test_composite_failure_and_error_statuses_are_not_flattened() -> None:
    spec = load_spec("testspec-01-contract-payment-valid-001-positive.json")
    passed = make_record(spec, "playwright", ExecutionStatus.PASSED)
    failed = make_record(spec, "httpx", ExecutionStatus.FAILED)
    failed_record = _combine_records(spec, load_profile(), [passed, failed], None)
    assert failed_record.status == ExecutionStatus.FAILED
    assert failed_record.failure_category == FailureCategory.ASSERTION_FAILURE

    errored = make_record(spec, "httpx", ExecutionStatus.ERROR)
    errored_record = _combine_records(spec, load_profile(), [passed, errored], None)
    assert errored_record.status == ExecutionStatus.ERROR


def test_execution_provider_layer_mismatch_is_skipped_without_rwa_access() -> None:
    spec = load_spec("testspec-02-contract-payment-valid-001-negative.json")
    provider = PlaywrightExecutionProvider(RwaProjectAdapter())
    record = execute_test_spec(spec, load_profile(), RwaProjectAdapter(), provider)
    assert record.status == ExecutionStatus.SKIPPED
    assert record.assertion_results == []


def test_normalized_execution_record_preserves_all_terminal_statuses() -> None:
    spec = load_spec("testspec-01-contract-payment-valid-001-positive.json")
    for status in (
        ExecutionStatus.PASSED,
        ExecutionStatus.FAILED,
        ExecutionStatus.ERROR,
        ExecutionStatus.INCOMPLETE,
    ):
        record = make_record(spec, "test-provider", status)
        assert record.status == status
        if status in {ExecutionStatus.FAILED, ExecutionStatus.ERROR}:
            assert record.failure_category is not None

    skipped = make_execution_record(
        spec,
        load_profile(),
        "test-provider",
        "test-version",
        ExecutionStatus.SKIPPED,
        datetime.now(timezone.utc),
        perf_counter(),
    )
    assert skipped.status == ExecutionStatus.SKIPPED


def test_execution_record_rejects_private_payload_evidence() -> None:
    spec = load_spec("testspec-02-contract-payment-valid-001-negative.json")
    now = datetime.now(timezone.utc)
    with pytest.raises(ValidationError):
        ExecutionRecord.model_validate(
            {
                "execution_id": "execution-private-test",
                "test_id": spec.test_id,
                "project_id": spec.project_id,
                "provider": "httpx",
                "provider_version": "test",
                "status": "PASSED",
                "started_at": now.isoformat(),
                "evidence_refs": [
                    {
                        "kind": "API_RESULT_METADATA",
                        "uri": "reports/private.json",
                        "response_body": "private payload",
                    }
                ],
            }
        )


def test_m3_modules_do_not_import_agentguard_or_eval_exec() -> None:
    modules = list((ROOT / "src/autoqe/adapters").rglob("*.py")) + list(
        (ROOT / "src/autoqe/execution").rglob("*.py")
    )
    contents = [path.read_text(encoding="utf-8").lower() for path in modules]
    assert not any("agentguard" in text for text in contents)
    assert not any(re.search(r"\b(eval|exec)\s*\(", text) for text in contents)


def test_node_preload_forces_loopback_and_rejects_remote_binds() -> None:
    node = shutil.which("node")
    assert node is not None
    preload = ROOT / "scripts/force_loopback_bind.cjs"
    loopback = subprocess.run(
        [
            node,
            f"--require={preload}",
            "-e",
            "const n=require('node:net');const s=n.createServer();s.listen(0,()=>{console.log(s.address().address);s.close()})",
        ],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert loopback.returncode == 0
    assert loopback.stdout.strip() == "127.0.0.1"
    rejected = subprocess.run(
        [
            node,
            f"--require={preload}",
            "-e",
            "const n=require('node:net');try{n.createServer().listen(0,'192.0.2.1');process.exitCode=1}catch(e){console.log('rejected')}",
        ],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert rejected.returncode == 0
    assert rejected.stdout.strip() == "rejected"


def test_execution_cli_exposes_only_two_providers() -> None:
    script = ROOT / "scripts/execute_testspec.py"
    completed = subprocess.run(
        [str(ROOT / ".venv/Scripts/python.exe"), str(script), "--help"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert completed.returncode == 0
    assert "playwright" in completed.stdout
    assert "api" in completed.stdout
    assert "cypress" not in completed.stdout.lower()