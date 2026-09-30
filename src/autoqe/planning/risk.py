import re

from autoqe.contracts.behavioral_contract import BehavioralContract
from autoqe.contracts.common import RiskLevel
from autoqe.planning.models import RiskAssessment

_TRANSACTION_MARKERS = re.compile(r"\b(payment|transaction|account|balance|transfer)\b", re.IGNORECASE)
_DATA_INTEGRITY_MARKERS = re.compile(
    r"\b(recorded|reflected|associated|balance|history|private account data)\b", re.IGNORECASE
)

_PRIORITY_BY_RISK = {
    RiskLevel.CRITICAL: 1,
    RiskLevel.HIGH: 2,
    RiskLevel.MEDIUM: 3,
    RiskLevel.LOW: 4,
    RiskLevel.UNKNOWN: 5,
}


class RiskPlanner:
    def analyze(self, contract: BehavioralContract) -> RiskAssessment:
        risk_factors: list[str] = []
        if contract.authorization_constraints:
            risk_factors.append("authorization impact")
        if contract.state_transitions:
            risk_factors.append("state-transition impact")
        if contract.forbidden_behaviors:
            risk_factors.append("negative/forbidden behavior")
        business_text = " ".join(
            [contract.title, contract.intent]
            + [behavior.description for behavior in contract.expected_behaviors]
            + [behavior.description for behavior in contract.forbidden_behaviors]
        )
        if _TRANSACTION_MARKERS.search(business_text):
            risk_factors.append("financial/business transaction impact")
        if _DATA_INTEGRITY_MARKERS.search(business_text):
            risk_factors.append("data integrity impact")
        if contract.unknowns or contract.assumptions:
            risk_factors.append("ambiguity/unknowns present")

        priority = _PRIORITY_BY_RISK[contract.risk_level]
        rationale = (
            f"Declared {contract.risk_level.value} risk maps to TestSpec priority {priority}; "
            "the declared risk is preserved without a probability estimate or override."
        )
        return RiskAssessment(
            declared_risk=contract.risk_level,
            test_priority=priority,
            risk_factors=risk_factors,
            rationale=rationale,
        )