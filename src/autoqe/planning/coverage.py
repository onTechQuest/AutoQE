import re

from autoqe.contracts.behavioral_contract import BehavioralContract
from autoqe.contracts.common import RiskLevel
from autoqe.contracts.test_spec import ExpectedOutcome, ScenarioType
from autoqe.planning.models import PlannerConfig, RiskAssessment, ScenarioCandidate

_BOUNDARY = re.compile(
    r"\b(at least|at most|minimum|maximum|no more than|no less than|between|greater than|less than)\b|(?:<=|>=)|\b\d+(?:\.\d+)?\b",
    re.IGNORECASE,
)
_AUTHORIZATION = re.compile(r"\b(owner|non-owner|unauthenticated|unauthorized|permission|access control)\b", re.I)
_UI_INTERACTION = re.compile(
    r"\b(show|display|visible|review|history|navigate|screen|form|button|user interface)\b", re.I
)


class CoveragePlanner:
    @staticmethod
    def contradictory_unauthenticated_behaviors(contract: BehavioralContract) -> tuple[str, ...]:
        has_authenticated_precondition = any(
            "authenticated" in precondition.lower() for precondition in contract.preconditions
        )
        if not has_authenticated_precondition:
            return ()
        return tuple(
            item.behavior_id
            for item in contract.forbidden_behaviors
            if "unauthenticated" in item.description.lower()
        )

    def build(
        self,
        contract: BehavioralContract,
        risk: RiskAssessment,
        config: PlannerConfig,
    ) -> tuple[ScenarioCandidate, ...]:
        candidates: list[ScenarioCandidate] = []

        if contract.expected_behaviors:
            outcomes = [
                ExpectedOutcome(outcome_id=item.behavior_id, description=item.description)
                for item in contract.expected_behaviors
            ]
            candidates.append(
                self._candidate(
                    contract,
                    risk,
                    ScenarioType.POSITIVE,
                    [item.behavior_id for item in contract.expected_behaviors],
                    outcomes,
                    "Cover the contract's expected behavior in a successful scenario.",
                    contract.preconditions + contract.business_conditions,
                )
            )

        contradictory_ids = set(self.contradictory_unauthenticated_behaviors(contract))
        auth_forbidden = [
            item
            for item in contract.forbidden_behaviors
            if item.behavior_id not in contradictory_ids and _AUTHORIZATION.search(item.description)
        ]
        non_auth_forbidden = [
            item
            for item in contract.forbidden_behaviors
            if item not in auth_forbidden and item.behavior_id not in contradictory_ids
        ]

        if contract.authorization_constraints:
            auth_refs = [f"authorization-{index + 1}" for index in range(len(contract.authorization_constraints))]
            auth_outcomes = [
                ExpectedOutcome(outcome_id=ref, description=constraint)
                for ref, constraint in zip(auth_refs, contract.authorization_constraints, strict=True)
            ]
            auth_outcomes.extend(
                ExpectedOutcome(outcome_id=item.behavior_id, description=item.description)
                for item in auth_forbidden
            )
            auth_data = list(contract.preconditions)
            if auth_forbidden:
                auth_data.append("Distinct owner and non-owner identities for the source-stated access constraint.")
            candidates.append(
                self._candidate(
                    contract,
                    risk,
                    ScenarioType.AUTHORIZATION,
                    auth_refs + [item.behavior_id for item in auth_forbidden],
                    auth_outcomes,
                    "Cover the explicit authorization constraint and its related forbidden behavior.",
                    auth_data,
                )
            )

        if non_auth_forbidden:
            outcomes = [
                ExpectedOutcome(outcome_id=item.behavior_id, description=item.description)
                for item in non_auth_forbidden
            ]
            candidates.append(
                self._candidate(
                    contract,
                    risk,
                    ScenarioType.NEGATIVE,
                    [item.behavior_id for item in non_auth_forbidden],
                    outcomes,
                    "Cover source-stated forbidden behavior without adding an unstated rejection rule.",
                    [f"An input that exercises: {item.description}" for item in non_auth_forbidden],
                )
            )

        if contract.state_transitions:
            outcomes = []
            refs = []
            for index, transition in enumerate(contract.state_transitions, start=1):
                reference = f"transition-{index}"
                refs.append(reference)
                outcomes.append(
                    ExpectedOutcome(
                        outcome_id=reference,
                        description=f"{transition.from_state} -> {transition.event} -> {transition.to_state}",
                    )
                )
            candidates.append(
                self._candidate(
                    contract,
                    risk,
                    ScenarioType.STATE_TRANSITION,
                    refs,
                    outcomes,
                    "Cover the explicitly declared state transition.",
                    contract.preconditions + contract.business_conditions,
                )
            )

        boundary_conditions = [
            condition for condition in contract.business_conditions if _BOUNDARY.search(condition)
        ]
        if boundary_conditions:
            outcomes = []
            refs = []
            for index, condition in enumerate(boundary_conditions, start=1):
                reference = f"condition-{index}"
                refs.append(reference)
                outcomes.append(ExpectedOutcome(outcome_id=reference, description=condition))
            candidates.append(
                self._candidate(
                    contract,
                    risk,
                    ScenarioType.BOUNDARY,
                    refs,
                    outcomes,
                    "Cover only the explicit boundary stated in the business condition.",
                    contract.preconditions + boundary_conditions,
                )
            )

        if risk.declared_risk == RiskLevel.CRITICAL:
            category_order = [
                ScenarioType.AUTHORIZATION,
                ScenarioType.NEGATIVE,
                ScenarioType.POSITIVE,
                ScenarioType.STATE_TRANSITION,
                ScenarioType.BOUNDARY,
            ]
        elif risk.declared_risk == RiskLevel.HIGH:
            category_order = [
                ScenarioType.POSITIVE,
                ScenarioType.NEGATIVE,
                ScenarioType.AUTHORIZATION,
                ScenarioType.STATE_TRANSITION,
                ScenarioType.BOUNDARY,
            ]
        else:
            category_order = [
                ScenarioType.POSITIVE,
                ScenarioType.NEGATIVE,
                ScenarioType.STATE_TRANSITION,
                ScenarioType.AUTHORIZATION,
                ScenarioType.BOUNDARY,
            ]
        order = {scenario_type: index for index, scenario_type in enumerate(category_order)}
        candidates.sort(key=lambda candidate: (candidate.priority, order[candidate.scenario_type]))
        return tuple(candidates[: config.max_tests])

    @staticmethod
    def _candidate(
        contract: BehavioralContract,
        risk: RiskAssessment,
        scenario_type: ScenarioType,
        coverage_refs: list[str],
        outcomes: list[ExpectedOutcome],
        rationale: str,
        test_data_requirements: list[str],
    ) -> ScenarioCandidate:
        scenario_name = scenario_type.value.lower().replace("_", "-")
        contract_text = " ".join(
            [contract.title, contract.intent]
            + [item.description for item in contract.expected_behaviors]
            + [item.description for item in contract.forbidden_behaviors]
        )
        return ScenarioCandidate(
            scenario_id=f"{contract.contract_id}-{scenario_name}",
            scenario_type=scenario_type,
            coverage_refs=coverage_refs,
            expected_outcomes=outcomes,
            preconditions=contract.preconditions,
            test_data_requirements=list(dict.fromkeys(test_data_requirements)),
            priority=risk.test_priority,
            ui_material=bool(_UI_INTERACTION.search(contract_text)),
            title=f"{contract.title} ({scenario_type.value.lower().replace('_', ' ')})",
            intent="; ".join(outcome.description for outcome in outcomes),
            rationale=rationale,
        )