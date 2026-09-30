import re
from pathlib import Path
from typing import Sequence

from autoqe.contracts.project_profile import ProjectProfile, RequirementProvider as SourceProvider
from autoqe.requirements.fingerprints import content_fingerprint, normalize_markdown
from autoqe.requirements.models import RequirementMetadata, RequirementSource, RequirementSourceType

_HEADING = re.compile(r"^#\s+(REQ-[A-Z0-9]+-[0-9]+):\s+(.+?)\s*$")
_SECTION = re.compile(r"^##\s+(.+?)\s*$")
_BULLET = re.compile(r"^\s*[-*+]\s+(.+?)\s*$")
_RWA_EXCLUDED_PATH_MARKERS = ("defect-profile", "fault-profile", "fault-injection", "mutation-profile")
MAX_SOURCES = 10
MAX_TOTAL_CONTENT = 65536


def _section_content(content: str) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {}
    current = ""
    for line in content.splitlines():
        match = _SECTION.match(line)
        if match:
            current = match.group(1).strip().lower()
            sections.setdefault(current, [])
            continue
        if current:
            bullet = _BULLET.match(line)
            if bullet:
                sections[current].append(bullet.group(1))
            elif line.strip():
                sections[current].append(line.strip())
    return sections


def parse_requirement_metadata(content: str) -> RequirementMetadata:
    heading = next((_HEADING.match(line) for line in content.splitlines() if line.startswith("# ")), None)
    if heading is None:
        raise ValueError("requirement Markdown needs a '# REQ-...: title' heading")
    requirement_id, title = heading.groups()
    sections = _section_content(content)
    intent = " ".join(sections.get("business intent", []))
    if not intent:
        raise ValueError("requirement Markdown is missing a Business intent section")
    risk_level = " ".join(sections.get("risk level", [])).upper() or "UNKNOWN"
    return RequirementMetadata(
        requirement_id=requirement_id,
        title=title,
        business_intent=intent,
        risk_level=risk_level,
        explicit_unknowns=tuple(sections.get("explicit unknowns", [])),
        acceptance_criteria=tuple(sections.get("acceptance criteria", [])),
        forbidden_behaviors=tuple(sections.get("forbidden behaviors", [])),
        preconditions=tuple(sections.get("preconditions", [])),
        business_conditions=tuple(sections.get("business conditions", [])),
        authorization_constraints=tuple(sections.get("authorization constraints", [])),
        state_transitions=tuple(sections.get("state transitions", [])),
    )


class MarkdownRequirementProvider:
    def __init__(self, project_profile: ProjectProfile, project_root: str | Path) -> None:
        if project_profile.requirements.provider != SourceProvider.LOCAL_FILES:
            raise ValueError("MarkdownRequirementProvider requires LOCAL_FILES in ProjectProfile")
        self.project_profile = project_profile
        self.project_root = Path(project_root).resolve(strict=True)
        self.allowed_locations = tuple(
            (self.project_root / location).resolve(strict=False)
            for location in project_profile.requirements.locations
        )
        self.is_rwa_reference = (
            project_profile.project_id == "cypress-rwa"
            and project_profile.reference_target is not None
            and str(project_profile.reference_target.repository_url).startswith(
                "https://github.com/cypress-io/cypress-realworld-app"
            )
        )

    def _is_allowed(self, source_path: Path) -> bool:
        for allowed in self.allowed_locations:
            if allowed.is_file() and source_path == allowed:
                return True
            if allowed.is_dir():
                try:
                    source_path.relative_to(allowed)
                    return True
                except ValueError:
                    continue
        return False

    def load(self, paths: Sequence[str | Path]) -> tuple[RequirementSource, ...]:
        if not paths:
            raise ValueError("at least one requirement Markdown file is required")
        if len(paths) > MAX_SOURCES:
            raise ValueError(f"at most {MAX_SOURCES} requirement sources may be loaded")

        loaded: list[RequirementSource] = []
        total_size = 0
        seen_source_ids: set[str] = set()
        seen_requirement_ids: set[str] = set()

        for requested_path in paths:
            candidate = Path(requested_path)
            if not candidate.is_absolute():
                candidate = self.project_root / candidate
            if self.is_rwa_reference:
                lowered_parts = tuple(part.lower() for part in candidate.parts)
                if any(part == "cypress" for part in lowered_parts):
                    raise ValueError("Cypress benchmark sources are not allowed in RWA extraction context")
                if any(marker in part for marker in _RWA_EXCLUDED_PATH_MARKERS for part in lowered_parts):
                    raise ValueError("defect/fault profile sources are not allowed in RWA extraction context")
            source_path = candidate.resolve(strict=True)
            try:
                relative_path = source_path.relative_to(self.project_root)
            except ValueError as exc:
                raise ValueError("requirement source must be inside the configured project root") from exc
            if not source_path.is_file() or source_path.suffix.lower() != ".md":
                raise ValueError("only local Markdown files are supported as requirements")
            if self.is_rwa_reference:
                lowered_parts = tuple(part.lower() for part in relative_path.parts)
                if any(part == "cypress" for part in lowered_parts):
                    raise ValueError("Cypress benchmark sources are not allowed in RWA extraction context")
                if any(marker in part for marker in _RWA_EXCLUDED_PATH_MARKERS for part in lowered_parts):
                    raise ValueError("defect/fault profile sources are not allowed in RWA extraction context")
            if not self._is_allowed(source_path):
                raise ValueError(f"requirement source is not allowed by ProjectProfile: {relative_path.as_posix()}")

            with source_path.open("rb") as source_file:
                raw_bytes = source_file.read(32769)
            if len(raw_bytes) > 32768:
                raise ValueError(f"requirement source exceeds 32768 bytes: {relative_path.as_posix()}")
            raw_content = raw_bytes.decode("utf-8")
            content = normalize_markdown(raw_content)
            encoded_size = len(content.encode("utf-8"))
            if encoded_size > 32768:
                raise ValueError(f"requirement source exceeds 32768 bytes: {relative_path.as_posix()}")
            total_size += encoded_size
            if total_size > MAX_TOTAL_CONTENT:
                raise ValueError(f"combined requirement context exceeds {MAX_TOTAL_CONTENT} bytes")

            try:
                metadata = parse_requirement_metadata(content)
            except ValueError as exc:
                raise ValueError(f"invalid requirement source {relative_path}: {exc}") from exc
            source_id = "md-" + re.sub(r"[^a-z0-9-]+", "-", relative_path.with_suffix("").as_posix().lower()).strip("-")
            if source_id in seen_source_ids or metadata.requirement_id in seen_requirement_ids:
                raise ValueError("duplicate requirement source or requirement ID")
            seen_source_ids.add(source_id)
            seen_requirement_ids.add(metadata.requirement_id)
            loaded.append(
                RequirementSource(
                    source_id=source_id,
                    source_type=RequirementSourceType.MARKDOWN,
                    location=relative_path.as_posix(),
                    content_fingerprint=content_fingerprint(content),
                    content=content,
                    metadata=metadata,
                )
            )
        return tuple(loaded)