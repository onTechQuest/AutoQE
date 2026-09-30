from collections.abc import Mapping

from pydantic import ValidationError

from autoqe.context import ContextBundle
from autoqe.contracts.behavioral_contract import BehavioralContract
from autoqe.contracts.project_profile import ProjectProfile
from autoqe.extraction.grounding import GroundingReport, validate_contract_grounding
from autoqe.interfaces.model_provider import ModelProvider

EXTRACTION_TASK = "extract_behavioral_contract"


class GroundingValidationError(ValueError):
    def __init__(self, report: GroundingReport) -> None:
        self.report = report
        super().__init__("; ".join(report.errors))


def extract_behavioral_contract(
    project_profile: ProjectProfile,
    context_bundle: ContextBundle,
    model_provider: ModelProvider,
) -> BehavioralContract:
    if project_profile.project_id != context_bundle.project_id:
        raise ValueError("ProjectProfile and ContextBundle project IDs must match")
    response = model_provider.generate_structured(
        task=EXTRACTION_TASK,
        context=context_bundle.to_model_context(),
        output_schema=BehavioralContract.model_json_schema(mode="validation"),
    )
    if not isinstance(response, Mapping):
        raise TypeError("ModelProvider must return a structured JSON object")
    try:
        contract = BehavioralContract.model_validate(response)
    except ValidationError:
        raise
    report = validate_contract_grounding(project_profile, context_bundle, contract)
    if not report.grounding_validation_pass:
        raise GroundingValidationError(report)
    return contract