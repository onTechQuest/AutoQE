import re
from typing import Iterable

from pydantic import Field

from autoqe.context import ContextBundle
from autoqe.contracts.behavioral_contract import BehavioralContract
from autoqe.contracts.common import RiskLevel, StrictModel
from autoqe.contracts.project_profile import ProjectProfile
from autoqe.requirements.fingerprints import content_fingerprint
from autoqe.requirements.models import RequirementSource


class GroundingReport(StrictModel):
    schema_valid: bool
    requirements_traceable: bool
    source_refs_valid: bool
    unknown_count: int = Field(ge=0)
    assumption_count: int = Field(ge=0)
    source_backed_behavior_count: int = Field(ge=0)
    grounding_validation_pass: bool
    errors: list[str] = Field(default_factory=list)


def _normalize_statement(value: str) -> str:
    return " ".join(value.split())


def _metadata_list(source: RequirementSource, name: str) -> list[str]:
    value = getattr(source.metadata, name, ())
    if isinstance(value, tuple):
        return list(value)
    return []


def _matches_one_source(value: str, sources: Iterable[RequirementSource], metadata_key: str) -> bool:
    normalized = _normalize_statement(value)
    return any(
        normalized == _normalize_statement(statement)
        for source in sources
        for statement in _metadata_list(source, metadata_key)
    )


def validate_contract_grounding(
    project_profile: ProjectProfile,
    context_bundle: ContextBundle,
    contract: BehavioralContract,
) -> GroundingReport:
    errors: list[str] = []
    source_by_id = {source.source_id: source for source in context_bundle.requirement_sources}
    requirement_sources: dict[str, RequirementSource] = {}
    for source in context_bundle.requirement_sources:
        requirement_sources[source.metadata.requirement_id] = source

    requirements_traceable = (
        bool(contract.requirement_ids)
        and all(requirement_id in requirement_sources for requirement_id in contract.requirement_ids)
        and contract.project_id == project_profile.project_id == context_bundle.project_id
    )
    if not requirements_traceable:
        errors.append("one or more requirement IDs do not resolve to supplied sources")

    selected_sources = [
        requirement_sources[requirement_id]
        for requirement_id in contract.requirement_ids
        if requirement_id in requirement_sources
    ]
    expected_source_ids = {source.source_id for source in selected_sources}
    source_refs_valid = (
        bool(expected_source_ids)
        and set(contract.source_ids) == expected_source_ids
        and set(contract.source_fingerprints) == expected_source_ids
    )
    if not source_refs_valid:
        errors.append("source IDs and fingerprint keys must exactly resolve selected requirements")

    for source_id in contract.source_ids:
        source = source_by_id.get(source_id)
        if source is None:
            source_refs_valid = False
            errors.append(f"source reference does not resolve: {source_id}")
            continue
        if content_fingerprint(source.content) != source.content_fingerprint:
            source_refs_valid = False
            errors.append(f"context source fingerprint is stale: {source_id}")
        if contract.source_fingerprints.get(source_id) != source.content_fingerprint:
            source_refs_valid = False
            errors.append(f"contract fingerprint does not match source: {source_id}")

    if contract.project_id != project_profile.project_id or contract.project_id != context_bundle.project_id:
        errors.append("contract, profile, and context project IDs must match")

    for source in selected_sources:
        if source.metadata.title != contract.title:
            errors.append(f"contract title is not grounded in source {source.source_id}")
        if source.metadata.business_intent != contract.intent:
            errors.append(f"contract intent is not grounded in source {source.source_id}")

    source_backed_claim_count = 0
    claim_checks = (
        (contract.preconditions, "preconditions"),
        (contract.business_conditions, "business_conditions"),
        ([item.description for item in contract.expected_behaviors], "acceptance_criteria"),
        ([item.description for item in contract.forbidden_behaviors], "forbidden_behaviors"),
        (contract.authorization_constraints, "authorization_constraints"),
    )
    for values, metadata_key in claim_checks:
        for value in values:
            if _matches_one_source(value, selected_sources, metadata_key):
                source_backed_claim_count += 1
            else:
                errors.append(f"behavioral claim is not supported by a selected source ({metadata_key})")

    for transition in contract.state_transitions:
        statement = f"{transition.from_state} -> {transition.event} -> {transition.to_state}"
        if _matches_one_source(statement, selected_sources, "state_transitions"):
            source_backed_claim_count += 1
        else:
            errors.append("state transition is not supported by a selected source")

    expected_unknowns = {
        item for source in selected_sources for item in _metadata_list(source, "explicit_unknowns")
    }
    if not expected_unknowns.issubset(set(contract.unknowns)):
        errors.append("explicit source unknowns must be preserved in the contract")
    if any(
        not _matches_one_source(item, selected_sources, "explicit_unknowns")
        for item in contract.unknowns
    ):
        errors.append("contract unknowns must resolve to explicit source unknowns")

    risk_levels = []
    for source in selected_sources:
        risk_value = source.metadata.risk_level
        try:
            risk_levels.append(RiskLevel(risk_value))
        except (ValueError, TypeError):
            errors.append(f"source risk level is missing or invalid: {source.source_id}")
    if risk_levels:
        risk_order = {
            RiskLevel.UNKNOWN: 0,
            RiskLevel.LOW: 1,
            RiskLevel.MEDIUM: 2,
            RiskLevel.HIGH: 3,
            RiskLevel.CRITICAL: 4,
        }
        if contract.risk_level != max(risk_levels, key=risk_order.__getitem__):
            errors.append("contract risk level does not match the selected requirement source")

    schema_valid = True
    requirements_traceable = requirements_traceable and contract.project_id == project_profile.project_id
    source_refs_valid = source_refs_valid and all(
        contract.source_fingerprints.get(source_id) == source_by_id[source_id].content_fingerprint
        for source_id in contract.source_ids
        if source_id in source_by_id
    )
    passed = schema_valid and requirements_traceable and source_refs_valid and not errors
    return GroundingReport(
        schema_valid=schema_valid,
        requirements_traceable=requirements_traceable,
        source_refs_valid=source_refs_valid,
        unknown_count=len(contract.unknowns),
        assumption_count=len(contract.assumptions),
        source_backed_behavior_count=source_backed_claim_count,
        grounding_validation_pass=passed,
        errors=errors,
    )