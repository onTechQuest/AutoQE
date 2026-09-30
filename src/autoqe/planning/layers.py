from autoqe.contracts.common import Availability, RiskLevel
from autoqe.contracts.project_profile import ProjectProfile
from autoqe.contracts.test_spec import ScenarioType, TestLayer
from autoqe.planning.models import RiskAssessment, ScenarioCandidate


class UnsupportedLayerSelectionError(ValueError):
    pass


class LayerSelector:
    def select(
        self,
        profile: ProjectProfile,
        candidate: ScenarioCandidate,
        risk: RiskAssessment,
    ) -> ScenarioCandidate:
        ui_available = profile.execution_capabilities.ui == Availability.AVAILABLE
        api_available = profile.execution_capabilities.api == Availability.AVAILABLE
        if not ui_available and not api_available:
            raise UnsupportedLayerSelectionError("ProjectProfile exposes no supported UI or API capability")

        high_risk = risk.declared_risk in {RiskLevel.CRITICAL, RiskLevel.HIGH}
        use_both = (
            candidate.scenario_type == ScenarioType.POSITIVE
            and high_risk
            and "financial/business transaction impact" in risk.risk_factors
            and ui_available
            and api_available
        ) or (
            candidate.scenario_type == ScenarioType.STATE_TRANSITION
            and high_risk
            and ui_available
            and api_available
        )

        if use_both:
            selected = TestLayer.BOTH
            rationale = "High-risk user behavior and resulting state both warrant UI and API evidence; both capabilities are available."
        elif candidate.scenario_type in {
            ScenarioType.AUTHORIZATION,
            ScenarioType.NEGATIVE,
            ScenarioType.BOUNDARY,
        } and api_available:
            selected = TestLayer.API
            rationale = "Direct business-rule, boundary, or ownership evidence is available through the API capability."
        elif candidate.scenario_type == ScenarioType.POSITIVE and candidate.ui_material and ui_available:
            selected = TestLayer.UI
            rationale = "The contract makes visible/review interaction material and the UI capability is available."
        elif candidate.scenario_type == ScenarioType.POSITIVE and api_available:
            selected = TestLayer.API
            rationale = "The contract states business behavior without a material UI interaction; direct API evidence is preferred."
        elif api_available:
            selected = TestLayer.API
            rationale = "Direct state/business evidence is preferred and the API capability is available."
        else:
            selected = TestLayer.UI
            rationale = "API capability is unavailable; the supported UI layer is selected."

        if selected == TestLayer.BOTH and not (ui_available and api_available):
            selected = TestLayer.UI if ui_available else TestLayer.API
            rationale = "BOTH was not supported; selected the only available execution layer."
        if selected == TestLayer.UI and not ui_available:
            selected = TestLayer.API
            rationale = "UI capability is unavailable; selected the supported API layer."
        if selected == TestLayer.API and not api_available:
            selected = TestLayer.UI
            rationale = "API capability is unavailable; selected the supported UI layer."

        return candidate.model_copy(update={"test_layer": selected, "layer_rationale": rationale})