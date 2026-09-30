import json
from pathlib import Path
import sys

import pytest
from pydantic import ValidationError

from autoqe.context import ContextBundle
from autoqe.contracts import BehavioralContract, ProjectProfile
from autoqe.extraction.grounding import validate_contract_grounding
from autoqe.extraction.service import (
    EXTRACTION_TASK,
    GroundingValidationError,
    extract_behavioral_contract,
)
from autoqe.providers.replay import ReplayModelProvider, UnknownReplayKeyError
from autoqe.requirements.fingerprints import content_fingerprint, normalize_markdown
from autoqe.requirements.markdown import MarkdownRequirementProvider
from autoqe.requirements.models import RequirementSource

ROOT = Path(__file__).resolve().parents[1]
REQUIREMENTS = ROOT / "examples" / "rwa" / "requirements"
REPLAYS = ROOT / "examples" / "rwa" / "replays.json"


class FixedModelProvider:
    def __init__(self, response: dict[str, object]) -> None:
        self.response = response

    def generate_structured(self, task, context, output_schema):
        assert task == EXTRACTION_TASK
        assert output_schema["title"] == "BehavioralContract"
        return self.response


def load_profile() -> ProjectProfile:
    return ProjectProfile.model_validate_json(
        (ROOT / "examples/rwa/project-profile.json").read_text(encoding="utf-8")
    )


def load_source(name: str) -> RequirementSource:
    profile = load_profile()
    provider = MarkdownRequirementProvider(profile, ROOT)
    return provider.load([REQUIREMENTS / name])[0]


def make_context(source_name: str) -> tuple[ProjectProfile, ContextBundle]:
    profile = load_profile()
    source = load_source(source_name)
    return profile, ContextBundle(project_id=profile.project_id, requirement_sources=(source,))


def approved_response(source_name: str) -> tuple[ProjectProfile, ContextBundle, dict[str, object]]:
    profile, bundle = make_context(source_name)
    replay = ReplayModelProvider(REPLAYS)
    response = replay.generate_structured(
        EXTRACTION_TASK,
        bundle.to_model_context(),
        BehavioralContract.model_json_schema(mode="validation"),
    )
    return profile, bundle, response


def test_markdown_provider_loads_bounded_requirement_sources() -> None:
    profile = load_profile()
    provider = MarkdownRequirementProvider(profile, ROOT)
    paths = sorted(REQUIREMENTS.glob("*.md"))
    sources = provider.load(paths)
    context = ContextBundle(project_id=profile.project_id, requirement_sources=sources)
    assert len(context.requirement_sources) == 5
    assert {source.metadata.requirement_id for source in sources} == {
        "REQ-AUTH-001",
        "REQ-ACCT-001",
        "REQ-PAY-001",
        "REQ-HIST-001",
        "REQ-AUTHZ-001",
    }
    assert all(source.content_fingerprint == content_fingerprint(source.content) for source in sources)


def test_markdown_provider_rejects_unapproved_and_cypress_paths() -> None:
    profile = load_profile()
    provider = MarkdownRequirementProvider(profile, ROOT)
    with pytest.raises(ValueError, match="not allowed by ProjectProfile"):
        provider.load([ROOT / "docs/M1_REFERENCE_QUALIFICATION.md"])
    with pytest.raises(ValueError, match="Cypress benchmark"):
        provider.load(["examples/rwa/requirements/cypress/auth.spec.md"])
    with pytest.raises(ValueError, match="defect/fault profile"):
        provider.load(["examples/rwa/requirements/hidden-defect-profile.md"])


def test_markdown_provider_rejects_oversized_source_before_parsing(tmp_path) -> None:
    profile_data = load_profile().model_dump(mode="json")
    profile_data["requirements"]["locations"] = ["requirements"]
    profile = ProjectProfile.model_validate(profile_data)
    source_path = tmp_path / "requirements" / "large.md"
    source_path.parent.mkdir()
    source_path.write_text(
        "# REQ-LARGE-001: Oversized source\n\n## Business intent\nA bounded test.\n\n"
        + "x" * 33000,
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="exceeds 32768 bytes"):
        MarkdownRequirementProvider(profile, tmp_path).load([source_path])


def test_markdown_normalization_and_fingerprint_are_deterministic() -> None:
    first = "# Requirement\r\n\r\n- Statement.  \r\n"
    second = "# Requirement\n\n- Statement.\n"
    assert normalize_markdown(first) == normalize_markdown(second)
    assert content_fingerprint(first) == content_fingerprint(second)
    assert content_fingerprint(first) != content_fingerprint(first.replace("Statement", "Changed"))


def test_context_bundle_rejects_stale_source_fingerprint() -> None:
    profile, _ = make_context("payments.md")
    source = load_source("payments.md")
    stale_source = source.model_copy(update={"content": source.content + "New unsupported text.\n"})
    with pytest.raises(ValidationError, match="fingerprint mismatch"):
        ContextBundle(project_id=profile.project_id, requirement_sources=(stale_source,))


def test_context_bundle_rejects_duplicate_requirement_ids() -> None:
    profile, _ = make_context("payments.md")
    source = load_source("payments.md")
    duplicate = source.model_copy(update={"source_id": source.source_id + "-duplicate"})
    with pytest.raises(ValidationError, match="requirement IDs must be unique"):
        ContextBundle(project_id=profile.project_id, requirement_sources=(source, duplicate))


def test_replay_model_provider_matches_approved_context_and_fingerprint() -> None:
    profile, context, response = approved_response("payments.md")
    contract = extract_behavioral_contract(profile, context, FixedModelProvider(response))
    assert contract.contract_id == "contract-payment-valid-001"

    source = load_source("payments.md")
    changed_content = source.content + "\n## Notes\nChanged contextual note.\n"
    changed_source = source.model_copy(
        update={
            "content": changed_content,
            "content_fingerprint": content_fingerprint(changed_content),
        }
    )
    changed_context = ContextBundle(project_id=profile.project_id, requirement_sources=(changed_source,))
    with pytest.raises(UnknownReplayKeyError, match="no unique approved replay"):
        ReplayModelProvider(REPLAYS).generate_structured(
            EXTRACTION_TASK,
            changed_context.to_model_context(),
            BehavioralContract.model_json_schema(mode="validation"),
        )

    changed_limits = ContextBundle(
        project_id=profile.project_id,
        requirement_sources=context.requirement_sources,
        limitations=("A different bounded-context limitation.",),
    )
    with pytest.raises(UnknownReplayKeyError, match="no unique approved replay"):
        ReplayModelProvider(REPLAYS).generate_structured(
            EXTRACTION_TASK,
            changed_limits.to_model_context(),
            BehavioralContract.model_json_schema(mode="validation"),
        )


def test_valid_payment_extraction_and_quality_metrics() -> None:
    profile, context = make_context("payments.md")
    contract = extract_behavioral_contract(profile, context, ReplayModelProvider(REPLAYS))
    assert BehavioralContract.model_validate_json(contract.model_dump_json()) == contract
    quality = validate_contract_grounding(profile, context, contract)
    assert isinstance(contract, BehavioralContract)
    assert contract.requirement_ids == ["REQ-PAY-001"]
    assert quality.schema_valid
    assert quality.requirements_traceable
    assert quality.source_refs_valid
    assert quality.grounding_validation_pass
    assert quality.unknown_count == 1
    assert quality.assumption_count == 0
    assert quality.source_backed_behavior_count > 0


def test_authorization_and_incomplete_requirement_replays() -> None:
    auth_profile, auth_context = make_context("authorization.md")
    auth_contract = extract_behavioral_contract(auth_profile, auth_context, ReplayModelProvider(REPLAYS))
    assert auth_contract.authorization_constraints == [
        "Private account access and changes are limited to the account owner."
    ]

    account_profile, account_context = make_context("account-setup.md")
    account_contract = extract_behavioral_contract(
        account_profile, account_context, ReplayModelProvider(REPLAYS)
    )
    assert account_contract.unknowns == [
        "Required account fields and account-number validation rules are not specified."
    ]
    assert account_contract.assumptions == [
        "The account setup request identifies the authenticated owner."
    ]
    quality = validate_contract_grounding(account_profile, account_context, account_contract)
    assert quality.unknown_count == 1
    assert quality.assumption_count == 1


@pytest.mark.parametrize(
    "fixture_name",
    [
        "malformed-model-output.json",
        "unsupported-schema-version.json",
    ],
)
def test_schema_invalid_and_unsupported_replay_outputs_are_rejected(fixture_name: str) -> None:
    profile, context = make_context("payments.md")
    response = json.loads(
        (ROOT / "tests/fixtures/extraction" / fixture_name).read_text(encoding="utf-8")
    )
    with pytest.raises(ValidationError):
        extract_behavioral_contract(profile, context, FixedModelProvider(response))


def test_fabricated_and_missing_source_references_are_rejected() -> None:
    profile, context, response = approved_response("payments.md")
    fabricated = json.loads(
        (ROOT / "tests/fixtures/extraction/fabricated-source-reference.json").read_text(
            encoding="utf-8"
        )
    )
    fabricated_response = {**response, **fabricated}
    with pytest.raises(GroundingValidationError) as caught:
        extract_behavioral_contract(profile, context, FixedModelProvider(fabricated_response))
    assert not caught.value.report.source_refs_valid

    missing_reference_response = {**response, "source_ids": [], "source_fingerprints": {}}
    with pytest.raises(GroundingValidationError) as caught:
        extract_behavioral_contract(profile, context, FixedModelProvider(missing_reference_response))
    assert not caught.value.report.source_refs_valid


def test_requirement_ids_fingerprints_project_ids_and_claims_are_grounded() -> None:
    profile, context, response = approved_response("payments.md")
    cases = [
        ({"requirement_ids": ["REQ-NOT-SUPPLIED-999"]}, "requirement IDs do not resolve"),
        ({"source_fingerprints": {response["source_ids"][0]: "0" * 64}}, "fingerprint"),
        ({"project_id": "different-project"}, "project IDs"),
        (
            {
                "expected_behaviors": [
                    {"behavior_id": "invented-claim", "description": "Invented payment behavior."}
                ]
            },
            "not supported",
        ),
    ]
    for patch, expected_error in cases:
        candidate = {**response, **patch}
        with pytest.raises(GroundingValidationError) as caught:
            extract_behavioral_contract(profile, context, FixedModelProvider(candidate))
        assert any(expected_error in message for message in caught.value.report.errors)


def test_privacy_sentinels_are_rejected_in_requirement_sources() -> None:
    profile = load_profile()
    source = load_source("payments.md")
    secret_content = source.content + "\nCredential: sk-123456789abcdef\n"
    with pytest.raises(ValidationError):
        source.model_copy(
            update={
                "content": secret_content,
                "content_fingerprint": content_fingerprint(secret_content),
            }
        ).__class__.model_validate(
            {
                **source.model_dump(),
                "content": secret_content,
                "content_fingerprint": content_fingerprint(secret_content),
            }
        )


def test_extraction_emits_no_test_spec_and_imports_no_execution_stack() -> None:
    profile, context = make_context("payments.md")
    contract = extract_behavioral_contract(profile, context, ReplayModelProvider(REPLAYS))
    assert type(contract) is BehavioralContract
    assert "test_id" not in contract.model_dump()
    sources = [path.read_text(encoding="utf-8").lower() for path in (ROOT / "src/autoqe").rglob("*.py")]
    assert not any("import playwright" in source or "import httpx" in source for source in sources)
    assert not any("agentguard" in source for source in sources)


def test_replay_cli_persists_only_the_contract_artifact(tmp_path, monkeypatch, capsys) -> None:
    from autoqe.cli.extract_contract import main

    output_dir = tmp_path / "contracts"
    monkeypatch.chdir(ROOT)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "autoqe-extract-contract",
            "--project-profile",
            "examples/rwa/project-profile.json",
            "--requirements",
            "examples/rwa/requirements/payments.md",
            "--provider",
            "replay",
            "--output",
            str(output_dir),
        ],
    )
    assert main() == 0
    result = json.loads(capsys.readouterr().out)
    artifact_path = Path(result["artifact"])
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert artifact_path.parent == output_dir
    assert artifact["source_ids"] == ["md-examples-rwa-requirements-payments"]
    assert "content" not in artifact
    assert result["grounding_validation_pass"] is True


def test_live_cli_option_fails_closed_before_loading_inputs(monkeypatch, capsys) -> None:
    from autoqe.cli.extract_contract import main

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "autoqe-extract-contract",
            "--project-profile",
            "missing-profile.json",
            "--requirements",
            "missing-requirement.md",
            "--provider",
            "live",
        ],
    )
    assert main() == 2
    captured = capsys.readouterr()
    assert "Live model provider is deferred in M1" in captured.err
    assert captured.out == ""