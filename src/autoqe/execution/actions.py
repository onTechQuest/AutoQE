from dataclasses import dataclass
from enum import StrEnum

from autoqe.adapters.rwa import RwaTestActors
from autoqe.contracts.test_spec import SemanticAction, SemanticStep


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

    def resolve(self, step: SemanticStep, actors: RwaTestActors) -> ResolvedAction:
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