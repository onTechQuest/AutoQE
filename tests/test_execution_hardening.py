from itertools import product
import json
from pathlib import Path
from types import SimpleNamespace
from contextlib import nullcontext
from urllib.parse import urlsplit

import httpx
import pytest

from autoqe.adapters.rwa import RwaProjectAdapter, RwaTestActors
from autoqe.contracts.behavioral_contract import BehavioralContract
from autoqe.contracts.common import EvidenceReference
from autoqe.contracts.execution_record import AssertionResult, ExecutionStatus, FailureCategory, ResultStatus
from autoqe.contracts.test_spec import ExpectedOutcome, SemanticStep, TestLayer as Layer
from autoqe.execution.api_provider import ApiExecutionProvider
from autoqe.execution.playwright_provider import PlaywrightExecutionProvider
from autoqe.execution.records import validate_completeness
from autoqe.execution.runtime import ExecutionSetup
from autoqe.execution.service import _combine_records, execute_test_spec, UnsupportedExecutionProviderError
from autoqe.planning.service import plan_tests
from autoqe.providers.replay import ReplayModelProvider
from test_execution import ROOT, load_profile, load_spec, make_record


def payment_spec():
    return load_spec("testspec-01-contract-payment-valid-001-positive.json")


def history_spec():
    contract = BehavioralContract.model_validate_json(
        (ROOT / "examples/rwa/plans/contracts/incomplete-history.json").read_text(encoding="utf-8")
    )
    return plan_tests(load_profile(), contract, ReplayModelProvider(ROOT / "examples/rwa/replays.json")).test_specs[0]


@pytest.mark.parametrize("first,second", list(product(ExecutionStatus, repeat=2)))
def test_every_provider_status_pair_is_conservative(first, second):
    spec = payment_spec()
    records = [make_record(spec, "ui", first), make_record(spec, "api", second)]
    result = _combine_records(spec, load_profile(), records, "seed")
    statuses = {first, second}
    if ExecutionStatus.ERROR in statuses:
        expected = ExecutionStatus.ERROR
    elif ExecutionStatus.FAILED in statuses:
        expected = ExecutionStatus.FAILED
    elif ExecutionStatus.INCOMPLETE in statuses:
        expected = ExecutionStatus.INCOMPLETE
    elif first == second:
        expected = first
    else:
        expected = ExecutionStatus.INCOMPLETE
    assert result.status == expected
    assert len(result.evidence_refs) == 2
    assert len(result.step_results) == 2 * len(spec.steps)
    assert "ui:" in result.assertion_results[0].observed
    assert "api:" in result.assertion_results[0].observed
    if expected == ExecutionStatus.ERROR:
        assert result.failure_category == FailureCategory.ENVIRONMENT_FAILURE


@pytest.mark.parametrize("first,second", list(product(ResultStatus, repeat=2)))
def test_assertion_aggregation_never_flattens_unknown_or_error(first, second):
    spec = payment_spec()
    records = [make_record(spec, "ui", ExecutionStatus.PASSED), make_record(spec, "api", ExecutionStatus.PASSED)]
    records[0].assertion_results[0].status = first
    records[1].assertion_results[0].status = second
    result = _combine_records(spec, load_profile(), records, None)
    statuses = {first, second}
    if ResultStatus.ERROR in statuses:
        expected = ResultStatus.ERROR
    elif ResultStatus.FAILED in statuses:
        expected = ResultStatus.FAILED
    elif first == second == ResultStatus.PASSED:
        expected = ResultStatus.PASSED
    elif first == second == ResultStatus.SKIPPED:
        expected = ResultStatus.SKIPPED
    else:
        expected = ResultStatus.UNKNOWN
    assert result.assertion_results[0].status == expected
    assert (result.status == ExecutionStatus.PASSED) == (first == second == ResultStatus.PASSED)


@pytest.mark.parametrize("gap", ["missing", "unknown", "skipped", "duplicate", "mismatch", "extra", "unexecuted", "wrong-identity"])
def test_completeness_blocks_false_passes(gap):
    spec = payment_spec()
    record = make_record(spec, "test", ExecutionStatus.PASSED)
    if gap == "missing":
        record.assertion_results.pop()
    elif gap in {"unknown", "skipped"}:
        record.assertion_results[0].status = ResultStatus(gap.upper())
    elif gap == "duplicate":
        record.assertion_results.append(record.assertion_results[0].model_copy())
    elif gap == "mismatch":
        record.assertion_results[0].expected = "Different behavior."
    elif gap == "extra":
        record.assertion_results.append(AssertionResult(assertion_id="extra", status="PASSED", expected="Unrequested behavior."))
    elif gap == "unexecuted":
        record.step_results.pop()
    else:
        record.test_id = "different-test"
    result = validate_completeness(spec, record)
    assert result.status == ExecutionStatus.INCOMPLETE
    assert result.limitations
    assert {item.outcome_id for item in spec.expected_outcomes} <= {item.assertion_id for item in result.assertion_results}
    assert result.evidence_refs == record.evidence_refs
    if gap == "missing":
        assert result.assertion_results[-1].status == ResultStatus.UNKNOWN
    composite = _combine_records(spec, load_profile(), [record, make_record(spec, "other", ExecutionStatus.PASSED)], None)
    assert composite.status == ExecutionStatus.INCOMPLETE


@pytest.mark.parametrize("provider_type", [ApiExecutionProvider, PlaywrightExecutionProvider])
@pytest.mark.parametrize("unsupported", ["target", "arguments", "outcome-id", "outcome-description", "missing-assert", "missing-auth", "duplicate-outcome", "duplicate-step"])
def test_capabilities_reject_unsupported_semantics_before_any_setup(provider_type, unsupported):
    spec = payment_spec()
    if unsupported == "target":
        spec.steps[-1].target = "unregistered assertion"
    elif unsupported == "arguments":
        spec.steps[0].value = "unregistered value"
    elif unsupported == "outcome-id":
        spec.expected_outcomes[0].outcome_id = "unregistered-outcome"
    elif unsupported == "outcome-description":
        spec.expected_outcomes[0].description = "A different requirement with a familiar ID."
    elif unsupported == "missing-assert":
        spec.steps.pop()
    elif unsupported == "missing-auth":
        spec.steps.pop(0)
    elif unsupported == "duplicate-outcome":
        spec.expected_outcomes.append(spec.expected_outcomes[0].model_copy())
    else:
        spec.steps[1].step_id = spec.steps[0].step_id
    provider = provider_type(RwaProjectAdapter())
    spec.test_layer = provider.execution_layer
    assert not provider.supports(spec)
    assert provider.capability_errors(spec)
    class NoSetup:
        def prepare_execution(self, *_):
            pytest.fail("unsupported semantics must not reach application setup")
    result = execute_test_spec(spec, load_profile(), NoSetup(), provider)
    assert result.status == ExecutionStatus.SKIPPED
    assert result.failure_category == FailureCategory.UNSUPPORTED_BEHAVIOR
    assert result.observed_outcomes
    assert all(item.status == ResultStatus.UNKNOWN for item in result.assertion_results)
    # Direct provider calls obey the same fail-closed preflight.
    direct = provider.execute(spec, load_profile())
    assert direct.status == ExecutionStatus.SKIPPED
    assert direct.failure_category == FailureCategory.UNSUPPORTED_BEHAVIOR


def test_setup_is_project_generic_and_runs_once_per_required_provider():
    spec = payment_spec()
    spec.project_id = "another-project"
    profile = load_profile().model_copy(update={"project_id": "another-project"})
    calls = []
    class Adapter:
        def prepare_execution(self, supplied_spec, supplied_profile):
            assert supplied_spec.project_id == supplied_profile.project_id == "another-project"
            calls.append("setup")
            return ExecutionSetup({"fixture": str(len(calls))}, f"reset-{len(calls)}")
    class Provider:
        provider_version = "test"
        def __init__(self, layer):
            self.execution_layer = layer
            self.provider_name = layer.value.lower()
        def capability_errors(self, _):
            return ()
        def supports(self, _):
            return True
        def execute(self, supplied_spec, _):
            calls.append(self.provider_name)
            return make_record(supplied_spec, self.provider_name, ExecutionStatus.PASSED)
    result = execute_test_spec(spec, profile, Adapter(), (Provider(Layer.API), Provider(Layer.UI)))
    assert result.status == ExecutionStatus.PASSED
    assert calls == ["setup", "api", "setup", "ui"]
    assert result.environment_identity["provider-1.fixture"] == "1"
    assert result.environment_identity["provider-2.fixture"] == "3"
    assert result.test_data_reset_identity == "reset-1;reset-3"
    with pytest.raises(UnsupportedExecutionProviderError):
        execute_test_spec(spec, profile, Adapter(), (Provider(Layer.API), Provider(Layer.API)))


def test_rwa_history_setup_depends_on_semantics_not_contract_id(monkeypatch):
    adapter = RwaProjectAdapter()
    requested = []
    monkeypatch.setattr(adapter, "verify_reference_checkout", lambda _: {})
    monkeypatch.setattr(adapter, "verify_ready", lambda _: {})
    monkeypatch.setattr(adapter, "authenticate_if_needed", lambda _: {})
    monkeypatch.setattr(adapter, "reset_environment", lambda _: {"reset_identity": "test-seed"})
    monkeypatch.setattr(adapter, "setup_test_data", lambda _, requirements: requested.append(requirements) or {})
    history = history_spec()
    history.contract_id = "renamed-contract"
    adapter.prepare_execution(history, load_profile())
    payment = payment_spec()
    payment.contract_id = "contract-transaction-history-001"
    adapter.prepare_execution(payment, load_profile())
    assert "rwa.history.baseline" in requested[0]
    assert "rwa.history.baseline" not in requested[1]


@pytest.mark.parametrize("url,expected", [
    ("http://[::1]:3001/", "http://[::1]:3001"),
    ("http://127.0.0.1:3001/", "http://127.0.0.1:3001"),
    ("http://localhost:3000/", "http://localhost:3000"),
])
def test_loopback_url_roundtrip(url, expected):
    assert RwaProjectAdapter._loopback_base_url(url) == expected
    assert urlsplit(expected).hostname in {"::1", "127.0.0.1", "localhost"}
    assert httpx.URL(expected).port == urlsplit(url).port
    profile = load_profile().model_copy(deep=True)
    data = profile.model_dump(mode="json")
    data["application"]["api_base_url"] = url
    profile = type(profile).model_validate(data)
    assert RwaProjectAdapter().api_endpoint(profile, "transactions") == expected + "/transactions"


@pytest.mark.parametrize("url", ["http://[::]:3001", "http://[2001:db8::1]:3001", "http://0.0.0.0:3001", "http://192.0.2.1:3001", "https://[::1]:3001", "http://user:synthetic@localhost:3001"])
def test_url_fix_does_not_weaken_reference_network_policy(url):
    with pytest.raises(ValueError):
        RwaProjectAdapter._loopback_base_url(url)


ACTORS = RwaTestActors("sender-id", "sender", "Test", "Sender", "recipient-id", "recipient", "Test", "Recipient")


@pytest.mark.parametrize("case", ["healthy", "amount", "state", "sender", "recipient", "identity", "duplicate", "missing-recipient", "request"])
def test_api_execution_verifies_submitted_payment_properties(case, tmp_path, monkeypatch):
    # Synthetic transport responses test the provider; no reference app fault is injected.
    spec = payment_spec()
    spec.test_layer = Layer.API
    adapter = RwaProjectAdapter()
    adapter._actors = ACTORS
    monkeypatch.setattr(adapter, "test_password", lambda: "unit-only-credential")
    state = {"created": False, "actor": "sender"}
    def respond(request):
        payload = json.loads(request.content) if request.content else {}
        if request.url.path == "/login":
            state["actor"] = payload["username"]
            return httpx.Response(200, json={})
        if request.method == "POST":
            assert payload["amount"] == 35
            state["created"] = True
            return httpx.Response(200, json={"transaction": {"id": "new-payment"}})
        transaction = {
            "id": "new-payment", "description": "AutoQE M3 payment qualification",
            "amount": 3500, "status": "complete", "senderId": "sender-id", "receiverId": "recipient-id",
        }
        if case == "amount":
            transaction["amount"] = 3501
        elif case == "state":
            transaction["status"] = "pending"
        elif case == "sender":
            transaction["senderId"] = "other-sender"
        elif case == "recipient":
            transaction["receiverId"] = "other-recipient"
        elif case == "identity" and state["actor"] == "recipient":
            transaction["id"] = "different-payment"
        elif case == "request":
            transaction["requestStatus"] = "pending"
        results = [transaction] if state["created"] else []
        if case == "duplicate" and results:
            results.append(dict(transaction))
        if case == "missing-recipient" and state["actor"] == "recipient":
            results = []
        return httpx.Response(200, json={"results": results})
    real_client = httpx.Client
    monkeypatch.setattr("autoqe.execution.api_provider.httpx.Client", lambda **kwargs: real_client(transport=httpx.MockTransport(respond), **kwargs))
    provider = ApiExecutionProvider(adapter, repository_root=tmp_path, evidence_root=tmp_path / "evidence")
    result = provider.execute(spec, load_profile())
    assert result.status == (ExecutionStatus.PASSED if case == "healthy" else ExecutionStatus.FAILED)
    assert {item.assertion_id for item in result.assertion_results} == {item.outcome_id for item in spec.expected_outcomes}
    persisted = result.model_dump_json() + "".join(path.read_text() for path in tmp_path.rglob("*.json"))
    assert "unit-only-credential" not in persisted
    assert '"password"' not in persisted
    assert '"senderId"' not in persisted
    assert "assert_payment_properties" in persisted


@pytest.mark.parametrize("displayed,passes", [("-$35.00", True), ("-$34.00", False), ("+$35.00", False)])
def test_ui_payment_assertion_checks_amount_and_payment_direction(displayed, passes, monkeypatch):
    adapter = RwaProjectAdapter()
    provider = PlaywrightExecutionProvider(adapter)
    monkeypatch.setattr(provider, "_assert_history_visible", lambda *_: None)
    row = SimpleNamespace(count=lambda: 1, get_attribute=lambda _: "transaction-item-id")
    monkeypatch.setattr(adapter, "payment_row", lambda *_: row)
    monkeypatch.setattr(adapter, "payment_amount_locator", lambda _: SimpleNamespace(inner_text=lambda: displayed))
    page = SimpleNamespace(get_by_text=lambda *_args, **_kwargs: SimpleNamespace(count=lambda: 1, is_visible=lambda: True))
    if passes:
        assert provider._assert_payment_visible(page, "http://localhost:3000", "payment") == "transaction-item-id"
    else:
        with pytest.raises(AssertionError, match="amount"):
            provider._assert_payment_visible(page, "http://localhost:3000", "payment")


@pytest.mark.parametrize("same_identity", [True, False])
def test_ui_execution_accounts_for_both_payment_outcomes_and_retains_partial_evidence(same_identity, monkeypatch):
    spec = payment_spec()
    spec.test_layer = Layer.UI
    adapter = RwaProjectAdapter()
    adapter._actors = ACTORS
    provider = PlaywrightExecutionProvider(adapter)
    actor = {"role": None}
    visited = []
    locator = SimpleNamespace(click=lambda: None, fill=lambda _: None, wait_for=lambda **_: None)
    monkeypatch.setattr(adapter, "ui_locator", lambda *_args, **_kwargs: locator)
    monkeypatch.setattr(provider, "_authenticate", lambda _page, _url, role: actor.update(role=role))
    def observe(*_):
        visited.append(actor["role"])
        return "transaction-item-id" if same_identity or actor["role"] == "sender" else "different-id"
    monkeypatch.setattr(provider, "_assert_payment_visible", observe)
    def evidence(_target, _execution, step):
        return EvidenceReference(kind="SCREENSHOT", uri=f"reports/evidence/{step}.png")
    monkeypatch.setattr(provider, "_capture", evidence)
    monkeypatch.setattr(provider, "_capture_page", evidence)
    page = SimpleNamespace(set_default_timeout=lambda _: None)
    context = SimpleNamespace(route=lambda *_: None, new_page=lambda: page, close=lambda: None)
    browser = SimpleNamespace(new_context=lambda: context, close=lambda: None)
    playwright = SimpleNamespace(chromium=SimpleNamespace(launch=lambda **_: browser))
    monkeypatch.setattr("autoqe.execution.playwright_provider.sync_playwright", lambda: nullcontext(playwright))
    result = provider.execute(spec, load_profile())
    assert visited == ["sender", "sender", "recipient"]
    assert result.status == (ExecutionStatus.PASSED if same_identity else ExecutionStatus.FAILED)
    assert {item.assertion_id for item in result.assertion_results} == {item.outcome_id for item in spec.expected_outcomes}
    assert any("payment-reflected-sender" in item.uri for item in result.evidence_refs)
    if not same_identity:
        assert result.assertion_results[-1].status == ResultStatus.UNKNOWN


@pytest.mark.parametrize("rejection_status,created,expected", [
    (422, False, ExecutionStatus.PASSED), (200, False, ExecutionStatus.FAILED), (422, True, ExecutionStatus.FAILED),
])
def test_api_invalid_payment_requires_rejection_and_unchanged_state(rejection_status, created, expected, tmp_path, monkeypatch):
    spec = load_spec("testspec-02-contract-payment-valid-001-negative.json")
    adapter = RwaProjectAdapter()
    adapter._actors = ACTORS
    monkeypatch.setattr(adapter, "test_password", lambda: "unit-only-credential")
    submitted = False
    def respond(request):
        nonlocal submitted
        if request.url.path == "/login":
            return httpx.Response(200, json={})
        if request.method == "POST":
            submitted = True
            return httpx.Response(rejection_status, json={})
        records = [{"description": "AutoQE M3 invalid request"}] if submitted and created else []
        return httpx.Response(200, json={"results": records})
    real_client = httpx.Client
    monkeypatch.setattr("autoqe.execution.api_provider.httpx.Client", lambda **kwargs: real_client(transport=httpx.MockTransport(respond), **kwargs))
    result = ApiExecutionProvider(adapter, repository_root=tmp_path).execute(spec, load_profile())
    assert result.status == expected
    assert len(result.assertion_results) == 1


def test_unobservable_ui_transition_is_explicitly_unsupported():
    spec = load_spec("testspec-03-contract-payment-valid-001-state-transition.json")
    provider = PlaywrightExecutionProvider(RwaProjectAdapter())
    assert not provider.supports(spec)
    assert any("completion status" in error for error in provider.capability_errors(spec))
    assert ApiExecutionProvider(RwaProjectAdapter()).supports(spec)


def test_execution_fixture_loading_never_opens_reports(monkeypatch):
    from test_execution import _payment_specs
    _payment_specs.cache_clear()
    original = Path.open
    def guarded(path, *args, **kwargs):
        if "reports" in path.parts:
            pytest.fail("Execution test fixture accessed runtime reports")
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, "open", guarded)
    assert payment_spec().expected_outcomes


def test_generic_execution_modules_have_no_project_or_provider_implementation_imports():
    for name in ("service.py", "records.py", "runtime.py"):
        source = (ROOT / "src/autoqe/execution" / name).read_text().lower()
        assert "rwa" not in source
        assert "playwright" not in source
        assert "httpx" not in source
