from dataclasses import dataclass
from enum import StrEnum

from autoqe.adapters.rwa import RwaTestActors
from autoqe.contracts.test_spec import SemanticAction, SemanticStep, TestLayer, TestSpec


class RwaOperation(StrEnum):
    AUTHENTICATE = "AUTHENTICATE"
    SELECT_RECIPIENT = "SELECT_RECIPIENT"
    ENTER_PAYMENT_AMOUNT = "ENTER_PAYMENT_AMOUNT"
    SUBMIT_VALID_PAYMENT = "SUBMIT_VALID_PAYMENT"
    SUBMIT_INVALID_PAYMENT = "SUBMIT_INVALID_PAYMENT"
    WAIT_FOR_RECORDED_PAYMENT = "WAIT_FOR_RECORDED_PAYMENT"
    ASSERT_PAYMENT_OUTCOME = "ASSERT_PAYMENT_OUTCOME"
    ASSERT_NO_TRANSACTION = "ASSERT_NO_TRANSACTION"
    ASSERT_TRANSACTION_VISIBLE = "ASSERT_TRANSACTION_VISIBLE"
    NAVIGATE_PERSONAL_HISTORY = "NAVIGATE_PERSONAL_HISTORY"


@dataclass(frozen=True)
class ResolvedAction:
    operation: RwaOperation
    actor_role: str | None = None
    amount: int | None = None
    description: str | None = None


class UnsupportedSemanticActionError(ValueError):
    pass


class RwaSemanticActionResolver:
    PAYMENT_AMOUNT = 35
    PAYMENT_DESCRIPTION = "AutoQE M3 payment qualification"
    OUTCOMES = {
        "payment-recorded-once": "A valid payment is recorded once after submission.",
        "payment-reflected": "A successful payment is reflected in sender and recipient account state.",
        "transition-1": "Pending payment -> Valid payment submitted -> Recorded payment",
        "invalid-payment-not-recorded": "An invalid payment request does not create a transaction.",
        "sender-sees-payment": "A sender can find a recorded payment in their transaction history.",
        "recipient-sees-payment": "A recipient can find a received payment in their transaction history.",
    }

    @staticmethod
    def assertion_ids(action: ResolvedAction) -> set[str]:
        if action.operation == RwaOperation.ASSERT_PAYMENT_OUTCOME:
            return {"payment-recorded-once", "payment-reflected", "transition-1"}
        if action.operation == RwaOperation.ASSERT_NO_TRANSACTION:
            return {"invalid-payment-not-recorded"}
        if action.operation == RwaOperation.ASSERT_TRANSACTION_VISIBLE:
            return {"sender-sees-payment" if action.actor_role == "sender" else "recipient-sees-payment"}
        return set()

    def capability_errors(self, spec: TestSpec, layer: TestLayer) -> tuple[str, ...]:
        errors: list[str] = []
        if spec.project_id != "cypress-rwa":
            errors.append("This semantic resolver supports only the RWA reference project.")
        if spec.test_layer not in {layer, TestLayer.BOTH}:
            errors.append("Requested execution layer is unavailable in this provider.")
        if len({step.step_id for step in spec.steps}) != len(spec.steps):
            errors.append("Semantic step IDs must be unique.")
        if len({item.outcome_id for item in spec.expected_outcomes}) != len(spec.expected_outcomes):
            errors.append("Expected outcome IDs must be unique.")
        covered: list[str] = []
        authenticated = False
        actor_role = None
        selected = entered = submitted = invalid_submitted = False
        expected_ids = {outcome.outcome_id for outcome in spec.expected_outcomes}
        for step in spec.steps:
            try:
                action = self.resolve(step)
            except UnsupportedSemanticActionError:
                errors.append(f"Unsupported semantic action, target, or arguments at step {step.step_id}.")
                continue
            op = action.operation
            if op == RwaOperation.AUTHENTICATE:
                authenticated = True
                actor_role = action.actor_role
            elif not authenticated:
                errors.append(f"Authentication must precede step {step.step_id}.")
            if op == RwaOperation.SELECT_RECIPIENT:
                selected = True
            if op == RwaOperation.ENTER_PAYMENT_AMOUNT:
                if layer == TestLayer.UI and not selected:
                    errors.append("UI amount entry requires prior recipient selection.")
                entered = True
            if op == RwaOperation.SUBMIT_VALID_PAYMENT:
                if submitted or actor_role != "sender":
                    errors.append("Payment submission requires the sender and exactly one submission.")
                if layer == TestLayer.UI and not (selected and entered):
                    errors.append("UI payment submission requires recipient selection and amount entry.")
                submitted = True
            if op == RwaOperation.SUBMIT_INVALID_PAYMENT:
                invalid_submitted = True
                if layer == TestLayer.UI:
                    errors.append("Invalid payment submission is not supported by the UI provider.")
            if op in {RwaOperation.WAIT_FOR_RECORDED_PAYMENT, RwaOperation.ASSERT_PAYMENT_OUTCOME} and not submitted:
                errors.append("Payment observation requires a preceding payment submission.")
            if op == RwaOperation.ASSERT_NO_TRANSACTION and (not invalid_submitted or layer == TestLayer.UI):
                errors.append("Invalid-payment assertion requires a supported invalid submission.")
            ids = self.assertion_ids(action) & expected_ids
            if step.action == SemanticAction.ASSERT and not ids:
                errors.append(f"Assertion step {step.step_id} has no supported expected outcome.")
            covered.extend(ids)
        for outcome in spec.expected_outcomes:
            if self.OUTCOMES.get(outcome.outcome_id) != outcome.description:
                errors.append(f"Unsupported expected outcome ID or description: {outcome.outcome_id}.")
            if covered.count(outcome.outcome_id) != 1:
                errors.append(f"Expected outcome needs exactly one assertion: {outcome.outcome_id}.")
            if layer == TestLayer.UI and outcome.outcome_id == "transition-1":
                errors.append("The UI does not expose the stored transaction completion status.")
        return tuple(dict.fromkeys(errors))

    def resolve(self, step: SemanticStep, actors: RwaTestActors | None = None) -> ResolvedAction:
        if step.action != SemanticAction.ENTER_VALUE and (step.value is not None or step.data_ref is not None):
            raise UnsupportedSemanticActionError("unexpected semantic action arguments")
        if step.action == SemanticAction.AUTHENTICATE:
            if step.target in {"sender", "history participant", "account owner"}:
                return ResolvedAction(RwaOperation.AUTHENTICATE, actor_role="sender")
            if step.target == "recipient":
                return ResolvedAction(RwaOperation.AUTHENTICATE, actor_role="recipient")
            raise UnsupportedSemanticActionError("unsupported RWA authentication target")

        if step.action == SemanticAction.SELECT_ENTITY and step.target == "eligible recipient":
            return ResolvedAction(RwaOperation.SELECT_RECIPIENT, actor_role="recipient")

        if (
            step.action == SemanticAction.ENTER_VALUE
            and step.target == "positive payment amount"
            and step.data_ref == "payment-amount"
            and step.value is None
        ):
            return ResolvedAction(
                RwaOperation.ENTER_PAYMENT_AMOUNT,
                amount=self.PAYMENT_AMOUNT,
                description=self.PAYMENT_DESCRIPTION,
            )

        if step.action == SemanticAction.SUBMIT and step.target == "valid payment":
            return ResolvedAction(
                RwaOperation.SUBMIT_VALID_PAYMENT,
                actor_role="recipient",
                amount=self.PAYMENT_AMOUNT,
                description=self.PAYMENT_DESCRIPTION,
            )

        if step.action == SemanticAction.SUBMIT and step.target == "invalid payment request":
            return ResolvedAction(RwaOperation.SUBMIT_INVALID_PAYMENT, description="AutoQE M3 invalid request")

        if step.action == SemanticAction.WAIT_FOR_STATE and step.target == "recorded payment":
            return ResolvedAction(RwaOperation.WAIT_FOR_RECORDED_PAYMENT, description=self.PAYMENT_DESCRIPTION)

        if step.action == SemanticAction.ASSERT:
            if step.target in {"resulting account state", "sender and recipient state"}:
                return ResolvedAction(RwaOperation.ASSERT_PAYMENT_OUTCOME, description=self.PAYMENT_DESCRIPTION)
            if step.target == "transaction not created":
                return ResolvedAction(RwaOperation.ASSERT_NO_TRANSACTION, description="AutoQE M3 invalid request")
            if step.target == "sender payment visibility":
                return ResolvedAction(
                    RwaOperation.ASSERT_TRANSACTION_VISIBLE,
                    actor_role="sender",
                    description="AutoQE M3 history fixture",
                )
            if step.target == "recipient payment visibility":
                return ResolvedAction(
                    RwaOperation.ASSERT_TRANSACTION_VISIBLE,
                    actor_role="recipient",
                    description="AutoQE M3 history fixture",
                )
        raise UnsupportedSemanticActionError(
            f"unsupported RWA semantic action/target: {step.action.value}/{step.target}"
        )
