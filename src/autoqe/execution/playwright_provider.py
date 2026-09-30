from datetime import datetime, timezone
import hashlib
from pathlib import Path
from time import perf_counter
from urllib.parse import urlsplit
from uuid import uuid4

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

from autoqe.adapters.rwa import RwaProjectAdapter
from autoqe.contracts.common import EvidenceReference
from autoqe.contracts.execution_record import (
    AssertionResult,
    ExecutionStatus,
    FailureCategory,
    ResultStatus,
    StepResult,
)
from autoqe.contracts.project_profile import ProjectProfile
from autoqe.contracts.test_spec import ScenarioType, SemanticAction, TestLayer, TestSpec
from autoqe.execution.actions import ResolvedAction, RwaOperation, RwaSemanticActionResolver
from autoqe.execution.records import evidence_uri, make_execution_record


class PlaywrightExecutionProvider:
    provider_version = "1.63.0"
    _SUPPORTED_ACTIONS = {
        SemanticAction.AUTHENTICATE,
        SemanticAction.SELECT_ENTITY,
        SemanticAction.ENTER_VALUE,
        SemanticAction.SUBMIT,
        SemanticAction.ASSERT,
        SemanticAction.WAIT_FOR_STATE,
    }

    def __init__(
        self,
        project_adapter: RwaProjectAdapter,
        evidence_root: str | Path | None = None,
        repository_root: str | Path | None = None,
    ) -> None:
        self.project_adapter = project_adapter
        self.repository_root = Path(repository_root or Path(__file__).resolve().parents[3]).resolve()
        self.evidence_root = Path(evidence_root or self.repository_root / "reports" / "evidence")
        self.resolver = RwaSemanticActionResolver()

    def supports(self, test_spec: TestSpec) -> bool:
        return (
            test_spec.test_layer in {TestLayer.UI, TestLayer.BOTH}
            and all(step.action in self._SUPPORTED_ACTIONS for step in test_spec.steps)
        )

    def execute(self, test_spec: TestSpec, project_profile: ProjectProfile):
        started_at = datetime.now(timezone.utc)
        started_clock = perf_counter()
        execution_id = uuid4().hex
        step_results: list[StepResult] = []
        assertions: list[AssertionResult] = []
        evidence: list[EvidenceReference] = []
        observed: list[str] = []
        status = ExecutionStatus.PASSED
        failure_category = None
        try:
            if not self.supports(test_spec):
                return make_execution_record(
                    test_spec,
                    project_profile,
                    "playwright",
                    self.provider_version,
                    ExecutionStatus.SKIPPED,
                    started_at,
                    started_clock,
                    observed_outcomes=["Playwright provider does not support this TestSpec layer or semantic action."],
                    reset_identity=project_profile.environment.reset_identity,
                    execution_id=execution_id,
                )
            actors = self.project_adapter.actors
            ui_base, _ = self.project_adapter.base_urls(project_profile)
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                context = browser.new_context()
                context.route("**/*", self._local_only_route)
                page = context.new_page()
                page.set_default_timeout(12_000)
                current_actor = "sender"

                for step in test_spec.steps:
                    action = self.resolver.resolve(step, actors)
                    evidence_before = len(evidence)
                    if action.operation == RwaOperation.AUTHENTICATE:
                        current_actor = action.actor_role or "sender"
                        self._authenticate(page, ui_base, current_actor)
                    elif action.operation == RwaOperation.SELECT_RECIPIENT:
                        self.project_adapter.ui_locator(page, "new_transaction").click()
                        self.project_adapter.ui_locator(page, "recipient").click()
                    elif action.operation == RwaOperation.ENTER_PAYMENT_AMOUNT:
                        self.project_adapter.ui_locator(page, "amount").fill(str(action.amount))
                        self.project_adapter.ui_locator(page, "description").fill(action.description or "")
                    elif action.operation == RwaOperation.SUBMIT_VALID_PAYMENT:
                        self.project_adapter.ui_locator(page, "submit_payment").click()
                        confirmation = self.project_adapter.ui_locator(page, "payment_confirmation")
                        self._assert_visible(confirmation)
                        evidence.append(self._capture(confirmation, execution_id, step.step_id))
                        observed.append("RWA displayed the payment submission confirmation.")
                    elif action.operation == RwaOperation.WAIT_FOR_RECORDED_PAYMENT:
                        try:
                            page.get_by_text(action.description or "", exact=False).wait_for(state="visible")
                        except PlaywrightTimeoutError as exc:
                            raise AssertionError("completed payment summary was not visible") from exc
                        observed.append("RWA displayed the completed payment summary.")
                    elif action.operation == RwaOperation.ASSERT_PAYMENT_OUTCOME:
                        self._assert_payment_visible(page, ui_base, action.description or "")
                        visible = self.project_adapter.ui_locator(
                            page,
                            "transaction_description",
                            actor_role="sender",
                        )
                        evidence.append(self._capture_page(page, execution_id, step.step_id))
                        assertions.append(
                            AssertionResult(
                                assertion_id="payment-recorded-once",
                                status=ResultStatus.PASSED,
                                expected="A valid payment is recorded once after submission.",
                                observed="Exactly one matching payment is visible in sender history.",
                            )
                        )
                    elif action.operation == RwaOperation.ASSERT_TRANSACTION_VISIBLE:
                        requested_actor = action.actor_role or current_actor
                        if requested_actor != current_actor:
                            self.project_adapter.ui_locator(page, "signout").click()
                            self._authenticate(page, ui_base, requested_actor)
                        current_actor = requested_actor
                        self._assert_history_visible(page, ui_base, action.description or "")
                        evidence.append(self._capture_page(page, execution_id, step.step_id))
                        outcome_id = "sender-sees-payment" if current_actor == "sender" else "recipient-sees-payment"
                        assertions.append(
                            AssertionResult(
                                assertion_id=outcome_id,
                                status=ResultStatus.PASSED,
                                expected="The transaction participant can find the recorded payment in personal history.",
                                observed=f"The {current_actor} account displays the seeded history transaction.",
                            )
                        )
                    else:
                        raise ValueError("RWA UI operation is not registered")

                    step_results.append(
                        StepResult(
                            step_id=step.step_id,
                            status=ResultStatus.PASSED,
                            observed=action.operation.value,
                            evidence_refs=evidence[evidence_before:],
                        )
                    )
                context.close()
                browser.close()
        except AssertionError as exc:
            status = ExecutionStatus.FAILED
            failure_category = FailureCategory.ASSERTION_FAILURE
            observed.append(str(exc))
            failed_step = test_spec.steps[min(len(step_results), len(test_spec.steps) - 1)]
            step_results.append(
                StepResult(step_id=failed_step.step_id, status=ResultStatus.FAILED, observed="Expected UI state was not observed.")
            )
        except (PlaywrightTimeoutError, PlaywrightError, OSError, RuntimeError, ValueError) as exc:
            status = ExecutionStatus.ERROR
            failure_category = FailureCategory.ENVIRONMENT_FAILURE if isinstance(exc, OSError) else FailureCategory.PROVIDER_ERROR
            observed.append(f"Playwright provider stopped with {type(exc).__name__}.")
            if len(step_results) < len(test_spec.steps):
                failed_step = test_spec.steps[len(step_results)]
                step_results.append(
                    StepResult(step_id=failed_step.step_id, status=ResultStatus.ERROR, observed="Provider could not complete this semantic action.")
                )

        return make_execution_record(
            test_spec,
            project_profile,
            "playwright",
            self.provider_version,
            status,
            started_at,
            started_clock,
            step_results=step_results,
            assertion_results=assertions,
            observed_outcomes=observed,
            evidence_refs=evidence,
            failure_category=failure_category,
            reset_identity=project_profile.environment.reset_identity,
            execution_id=execution_id,
        )

    def _authenticate(self, page, ui_base: str, actor_role: str) -> None:
        actor = self._actor_for_role(actor_role)
        page.goto(f"{ui_base}/signin", wait_until="domcontentloaded")
        self.project_adapter.ui_locator(page, "signin_username").fill(actor["username"])
        self.project_adapter.ui_locator(page, "signin_password").fill(self.project_adapter.test_password())
        self.project_adapter.ui_locator(page, "signin_submit").click()
        self.project_adapter.ui_locator(page, "new_transaction").wait_for(state="visible")

    def _actor_for_role(self, role: str) -> dict[str, str]:
        actors = self.project_adapter.actors
        if role == "sender":
            return {"username": actors.sender_username}
        if role == "recipient":
            return {"username": actors.recipient_username}
        raise ValueError("unsupported RWA actor role")

    def _assert_payment_visible(self, page, ui_base: str, description: str) -> None:
        self._assert_history_visible(page, ui_base, description)
        matches = page.get_by_text(description, exact=True)
        if matches.count() != 1 or not matches.is_visible():
            raise AssertionError("expected payment was not visible exactly once in sender history")

    def _assert_history_visible(self, page, ui_base: str, description: str) -> None:
        try:
            page.goto(f"{ui_base}/personal", wait_until="domcontentloaded")
        except PlaywrightTimeoutError as exc:
            raise AssertionError("RWA personal-history navigation did not complete") from exc
        try:
            self.project_adapter.ui_locator(page, "transaction_list").wait_for(state="visible")
        except PlaywrightTimeoutError as exc:
            raise AssertionError("RWA personal-history list did not become visible") from exc
        matches = page.get_by_text(description, exact=True)
        try:
            matches.first.wait_for(state="visible")
        except PlaywrightTimeoutError as exc:
            raise AssertionError("expected transaction description was not visible in participant history") from exc
        if matches.count() < 1 or not matches.first.is_visible():
            raise AssertionError("expected participant history transaction was not visible")

    def _capture(self, locator, execution_id: str, step_id: str) -> EvidenceReference:
        safe_step = hashlib.sha256(step_id.encode("utf-8")).hexdigest()[:12]
        output_path = self.evidence_root / execution_id / f"{safe_step}.png"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        locator.screenshot(path=str(output_path), animations="disabled")
        return EvidenceReference(
            kind="SCREENSHOT",
            uri=evidence_uri(output_path, self.repository_root),
            description="Cropped synthetic UI confirmation/state evidence.",
        )

    def _capture_page(self, page, execution_id: str, step_id: str) -> EvidenceReference:
        safe_step = hashlib.sha256(step_id.encode("utf-8")).hexdigest()[:12]
        output_path = self.evidence_root / execution_id / f"{safe_step}.png"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(output_path), full_page=False, animations="disabled")
        return EvidenceReference(
            kind="SCREENSHOT",
            uri=evidence_uri(output_path, self.repository_root),
            description="Viewport screenshot after a contract-backed transaction-history assertion.",
        )

    @staticmethod
    def _assert_visible(locator) -> None:
        try:
            locator.wait_for(state="visible")
        except PlaywrightTimeoutError as exc:
            raise AssertionError("expected UI confirmation was not visible") from exc

    @staticmethod
    def _local_only_route(route) -> None:
        hostname = urlsplit(route.request.url).hostname
        if hostname not in {"localhost", "127.0.0.1", "::1"}:
            route.abort()
            return
        route.continue_()