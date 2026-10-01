from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from time import perf_counter
from uuid import uuid4

import httpx

from autoqe.adapters.rwa import RwaProjectAdapter, RwaTestActors
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
from autoqe.execution.actions import RwaOperation, RwaSemanticActionResolver
from autoqe.execution.records import evidence_uri, make_execution_record


class ApiExecutionProvider:
    provider_name = "httpx"
    execution_layer = TestLayer.API
    provider_version = httpx.__version__

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
        return not self.capability_errors(test_spec)

    def capability_errors(self, test_spec: TestSpec) -> tuple[str, ...]:
        return self.resolver.capability_errors(test_spec, self.execution_layer)

    @staticmethod
    def _actor_for_role(actors: RwaTestActors, role: str) -> dict[str, str]:
        if role == "sender":
            return {"id": actors.sender_id, "username": actors.sender_username}
        if role == "recipient":
            return {"id": actors.recipient_id, "username": actors.recipient_username}
        raise ValueError("unsupported RWA actor role")

    def execute(self, test_spec: TestSpec, project_profile: ProjectProfile):
        started_at = datetime.now(timezone.utc)
        started_clock = perf_counter()
        execution_id = uuid4().hex
        step_results: list[StepResult] = []
        assertions: list[AssertionResult] = []
        observed: list[str] = []
        http_events: list[dict[str, object]] = []
        status = ExecutionStatus.PASSED
        failure_category = None
        try:
            if not self.supports(test_spec):
                return make_execution_record(
                    test_spec,
                    project_profile,
                    "httpx",
                    self.provider_version,
                    ExecutionStatus.SKIPPED,
                    started_at,
                    started_clock,
                    observed_outcomes=list(self.capability_errors(test_spec)),
                    failure_category=FailureCategory.UNSUPPORTED_BEHAVIOR,
                    reset_identity=project_profile.environment.reset_identity,
                    execution_id=execution_id,
                )
            actors = self.project_adapter.actors
            _, api_base = self.project_adapter.base_urls(project_profile)
            amount = None
            description = None
            invalid_rejected = False
            created_fingerprint = None
            sender_has_transaction = False
            recipient_has_transaction = False
            completed_status = False
            payment_properties = False
            transaction_id = None

            with httpx.Client(base_url=api_base, timeout=self.project_adapter.timeout_seconds, trust_env=False) as client:
                for step in test_spec.steps:
                    assertion_count = len(assertions)
                    action = self.resolver.resolve(step, actors)
                    if action.operation == RwaOperation.AUTHENTICATE:
                        actor = self._actor_for_role(actors, action.actor_role or "sender")
                        response = client.post(
                            self.project_adapter.api_endpoint(project_profile, "login"),
                            json={"username": actor["username"], "password": self.project_adapter.test_password()},
                        )
                        self._require_status(response.status_code, 200, "RWA authentication failed")
                        http_events.append({"operation": "login", "status": response.status_code})
                    elif action.operation == RwaOperation.SELECT_RECIPIENT:
                        http_events.append({"operation": "select_fixture_recipient", "status": "LOCAL_FIXTURE"})
                    elif action.operation == RwaOperation.ENTER_PAYMENT_AMOUNT:
                        amount = action.amount
                        description = action.description
                        http_events.append({"operation": "prepare_payment_intent", "status": "READY"})
                    elif action.operation == RwaOperation.SUBMIT_VALID_PAYMENT:
                        amount = action.amount
                        description = action.description
                        before = self._matching_transactions(client, project_profile, description or "")
                        receiver = self._actor_for_role(actors, action.actor_role or "recipient")
                        response = client.post(
                            self.project_adapter.api_endpoint(project_profile, "transactions"),
                            json={
                                "transactionType": "payment",
                                "receiverId": receiver["id"],
                                "amount": amount,
                                "description": description,
                            },
                        )
                        self._require_status(response.status_code, 200, "RWA payment request failed")
                        payload = response.json()
                        transaction = payload.get("transaction", {})
                        transaction_id = transaction.get("id")
                        if not isinstance(transaction_id, str) or not transaction_id:
                            raise RuntimeError("RWA payment response omitted transaction identity")
                        after = self._matching_transactions(client, project_profile, description or "")
                        sender_has_transaction = len(before) == 0 and len(after) == 1
                        recipient_transactions = self._recipient_transactions(
                            client, project_profile, actors, description or ""
                        )
                        recipient_has_transaction = len(recipient_transactions) == 1
                        payment_properties = self._payment_properties_match(
                            after, recipient_transactions, actors, amount, transaction_id
                        )
                        completed_status = any(item.get("status") == "complete" for item in after)
                        created_fingerprint = hashlib.sha256(transaction_id.encode("utf-8")).hexdigest()
                        http_events.append(
                            {
                                "operation": "create_payment",
                                "status": response.status_code,
                                "baseline_matching_records": len(before),
                                "resulting_matching_records": len(after),
                                "transaction_reference_sha256": created_fingerprint,
                            }
                        )
                    elif action.operation == RwaOperation.SUBMIT_INVALID_PAYMENT:
                        description = action.description
                        before = self._matching_transactions(client, project_profile, description or "")
                        response = client.post(
                            self.project_adapter.api_endpoint(project_profile, "transactions").removeprefix(api_base),
                            json={
                                "transactionType": "payment",
                                "amount": RwaSemanticActionResolver.PAYMENT_AMOUNT,
                                "description": description,
                            },
                        )
                        invalid_rejected = response.status_code == 422
                        after = self._matching_transactions(client, project_profile, description or "")
                        if len(after) != len(before):
                            invalid_rejected = False
                        http_events.append(
                            {
                                "operation": "reject_invalid_payment",
                                "status": response.status_code,
                                "baseline_matching_records": len(before),
                                "resulting_matching_records": len(after),
                                "transaction_reference_sha256": created_fingerprint,
                            }
                        )
                    elif action.operation == RwaOperation.WAIT_FOR_RECORDED_PAYMENT:
                        matching = self._matching_transactions(client, project_profile, action.description or "")
                        completed_status = any(item.get("status") == "complete" for item in matching)
                        sender_has_transaction = len(matching) == 1
                        recipient_transactions = self._recipient_transactions(
                            client, project_profile, actors, action.description or ""
                        )
                        recipient_has_transaction = len(recipient_transactions) == 1
                        payment_properties = self._payment_properties_match(
                            matching, recipient_transactions, actors, amount, transaction_id
                        )
                        http_events.append({"operation": "observe_recorded_state", "status": "OBSERVED" if completed_status else "MISSING"})
                    elif action.operation == RwaOperation.ASSERT_NO_TRANSACTION:
                        passed = invalid_rejected and not self._matching_transactions(
                            client, project_profile, action.description or ""
                        )
                        assertions.append(
                            AssertionResult(
                                assertion_id="invalid-payment-not-recorded",
                                status=ResultStatus.PASSED if passed else ResultStatus.FAILED,
                                expected=next(item.description for item in test_spec.expected_outcomes if item.outcome_id == "invalid-payment-not-recorded"),
                                observed="The API rejected the invalid payload and no matching transaction exists." if passed else "The rejection/status or resulting state did not match the expected outcome.",
                            )
                        )
                    elif action.operation == RwaOperation.ASSERT_PAYMENT_OUTCOME:
                        for outcome in test_spec.expected_outcomes:
                            if outcome.outcome_id == "payment-recorded-once":
                                passed = sender_has_transaction and payment_properties
                            elif outcome.outcome_id == "payment-reflected":
                                passed = sender_has_transaction and recipient_has_transaction and payment_properties
                            elif outcome.outcome_id == "transition-1":
                                passed = sender_has_transaction and recipient_has_transaction and completed_status and payment_properties
                            else:
                                continue
                            assertions.append(
                                AssertionResult(
                                    assertion_id=outcome.outcome_id,
                                    status=ResultStatus.PASSED if passed else ResultStatus.FAILED,
                                    expected=outcome.description,
                                    observed="Both participant histories contain the same payment with the submitted amount, correct actors, and complete state." if passed else "Payment count, amount, actors, identity, or complete state did not match.",
                                )
                            )
                            http_events.append({"operation": "assert_payment_properties", "outcome_id": outcome.outcome_id, "passed": passed})
                    elif action.operation == RwaOperation.ASSERT_TRANSACTION_VISIBLE:
                        visible = self._actor_sees_transaction(
                            client,
                            project_profile,
                            actors,
                            action.actor_role or "sender",
                            action.description or "",
                        )
                        outcome_id = "sender-sees-payment" if action.actor_role == "sender" else "recipient-sees-payment"
                        assertions.append(
                            AssertionResult(
                                assertion_id=outcome_id,
                                status=ResultStatus.PASSED if visible else ResultStatus.FAILED,
                                expected=next(item.description for item in test_spec.expected_outcomes if item.outcome_id == outcome_id),
                                observed="The API returned the seeded history transaction for this participant." if visible else "The transaction was absent from this participant's API history.",
                            )
                        )
                    else:
                        raise ValueError("RWA API operation is not registered")

                    step_results.append(
                        StepResult(
                            step_id=step.step_id,
                            status=(ResultStatus.FAILED if any(
                                item.status == ResultStatus.FAILED for item in assertions[assertion_count:]
                            ) else ResultStatus.PASSED),
                            observed=action.operation.value,
                        )
                    )

            if any(assertion.status == ResultStatus.FAILED for assertion in assertions):
                status = ExecutionStatus.FAILED
                failure_category = FailureCategory.ASSERTION_FAILURE
            evidence_refs = self._write_safe_evidence(execution_id, test_spec, http_events)
            observed.append("httpx used the local authenticated RWA API; raw payloads, cookies, and headers were not retained.")
        except AssertionError as exc:
            status = ExecutionStatus.FAILED
            failure_category = FailureCategory.ASSERTION_FAILURE
            observed.append(str(exc))
            failed_step = test_spec.steps[min(len(step_results), len(test_spec.steps) - 1)]
            step_results.append(StepResult(step_id=failed_step.step_id, status=ResultStatus.FAILED, observed="Expected API result was not observed."))
            evidence_refs = self._write_safe_evidence(execution_id, test_spec, http_events)
        except (httpx.HTTPError, RuntimeError, ValueError) as exc:
            status = ExecutionStatus.ERROR
            failure_category = FailureCategory.ENVIRONMENT_FAILURE if isinstance(exc, httpx.ConnectError) else FailureCategory.PROVIDER_ERROR
            observed.append(f"httpx provider stopped with {type(exc).__name__}.")
            if len(step_results) < len(test_spec.steps):
                failed_step = test_spec.steps[len(step_results)]
                step_results.append(StepResult(step_id=failed_step.step_id, status=ResultStatus.ERROR, observed="Provider could not complete this semantic action."))
            evidence_refs = self._write_safe_evidence(execution_id, test_spec, http_events)

        return make_execution_record(
            test_spec,
            project_profile,
            "httpx",
            self.provider_version,
            status,
            started_at,
            started_clock,
            step_results=step_results,
            assertion_results=assertions,
            observed_outcomes=observed,
            evidence_refs=evidence_refs,
            failure_category=failure_category,
            reset_identity=project_profile.environment.reset_identity,
            execution_id=execution_id,
        )

    def _matching_transactions(self, client: httpx.Client, profile: ProjectProfile, description: str) -> list[dict[str, object]]:
        response = client.get(
                            self.project_adapter.api_endpoint(profile, "transactions"),
            params={"page": 1, "limit": 100},
        )
        self._require_status(response.status_code, 200, "RWA transaction query failed")
        results = response.json().get("results")
        if not isinstance(results, list):
            raise RuntimeError("RWA transaction response has an invalid result shape")
        return [
            {
                "id": item.get("id"),
                "description": item.get("description"),
                "status": item.get("status"),
                "amount": item.get("amount"),
                "senderId": item.get("senderId"),
                "receiverId": item.get("receiverId"),
                "requestStatus": item.get("requestStatus"),
            }
            for item in results
            if isinstance(item, dict) and item.get("description") == description
        ]

    def _recipient_transactions(
        self,
        client: httpx.Client,
        profile: ProjectProfile,
        actors,
        description: str,
    ) -> list[dict[str, object]]:
        self._login(client, profile, actors.recipient_username)
        result = self._matching_transactions(client, profile, description)
        self._login(client, profile, actors.sender_username)
        return result

    @staticmethod
    def _payment_properties_match(sender_records, recipient_records, actors, amount, transaction_id) -> bool:
        if len(sender_records) != 1 or len(recipient_records) != 1 or not transaction_id or amount is None:
            return False
        return all(
            item.get("id") == transaction_id
            and item.get("amount") == amount * 100
            and item.get("status") == "complete"
            and item.get("senderId") == actors.sender_id
            and item.get("receiverId") == actors.recipient_id
            and not item.get("requestStatus")
            for item in [sender_records[0], recipient_records[0]]
        )

    def _actor_sees_transaction(self, client, profile, actors, role: str, description: str) -> bool:
        username = actors.sender_username if role == "sender" else actors.recipient_username
        self._login(client, profile, username)
        return bool(self._matching_transactions(client, profile, description))

    def _login(self, client: httpx.Client, profile: ProjectProfile, username: str) -> None:
        response = client.post(
            self.project_adapter.api_endpoint(profile, "login"),
            json={"username": username, "password": self.project_adapter.test_password()},
        )
        self._require_status(response.status_code, 200, "RWA authentication failed")

    @staticmethod
    def _require_status(actual: int, expected: int, message: str) -> None:
        if actual != expected:
            raise RuntimeError(message)

    def _write_safe_evidence(self, execution_id: str, test_spec: TestSpec, events: list[dict[str, object]]) -> list[EvidenceReference]:
        output_path = self.evidence_root / execution_id / "api-result-metadata.json"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        safe_events = [
            {key: value for key, value in event.items() if key not in {"username", "password", "cookie", "headers", "payload", "body"}}
            for event in events
        ]
        output_path.write_text(
            json.dumps(
                {
                    "provider": "httpx",
                    "test_id": test_spec.test_id,
                    "network_scope": "LOCAL_ONLY",
                    "events": safe_events,
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        return [
            EvidenceReference(
                kind="API_RESULT_METADATA",
                uri=evidence_uri(output_path, self.repository_root),
                description="Sanitized API status and assertion metadata; no request/response bodies or headers.",
            )
        ]
