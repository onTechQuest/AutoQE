from pydantic import ConfigDict, Field, model_validator

from autoqe.contracts.common import Identifier, PrivacySafeModel
from autoqe.requirements.fingerprints import content_fingerprint
from autoqe.requirements.models import RequirementSource
from autoqe.requirements.markdown import MAX_SOURCES, MAX_TOTAL_CONTENT, parse_requirement_metadata


class ContextBundle(PrivacySafeModel):
    model_config = ConfigDict(frozen=True)

    project_id: Identifier
    requirement_sources: tuple[RequirementSource, ...] = Field(min_length=1, max_length=MAX_SOURCES)
    limitations: tuple[str, ...] = (
        "Only explicitly supplied, profile-allowed Markdown requirement sources are included.",
        "No repository browsing, Cypress benchmark source, secrets, or hidden defect metadata is included.",
    )

    @model_validator(mode="after")
    def validate_source_bounds_and_fingerprints(self) -> "ContextBundle":
        if len({source.source_id for source in self.requirement_sources}) != len(self.requirement_sources):
            raise ValueError("ContextBundle source IDs must be unique")
        if len({source.metadata.requirement_id for source in self.requirement_sources}) != len(
            self.requirement_sources
        ):
            raise ValueError("ContextBundle requirement IDs must be unique")
        total_bytes = sum(len(source.content.encode("utf-8")) for source in self.requirement_sources)
        if total_bytes > MAX_TOTAL_CONTENT:
            raise ValueError(f"ContextBundle exceeds {MAX_TOTAL_CONTENT} bytes")
        for source in self.requirement_sources:
            if content_fingerprint(source.content) != source.content_fingerprint:
                raise ValueError(f"content fingerprint mismatch for source {source.source_id}")
            if parse_requirement_metadata(source.content) != source.metadata:
                raise ValueError(f"parsed metadata does not match source content: {source.source_id}")
        return self

    @property
    def source_ids(self) -> tuple[str, ...]:
        return tuple(source.source_id for source in self.requirement_sources)

    @property
    def source_fingerprints(self) -> dict[str, str]:
        return {source.source_id: source.content_fingerprint for source in self.requirement_sources}

    def to_model_context(self) -> dict[str, object]:
        return {
            "project_id": self.project_id,
            "sources": [
                {
                    "source_id": source.source_id,
                    "source_type": source.source_type.value,
                    "location": source.location,
                    "content_fingerprint": source.content_fingerprint,
                    "content": source.content,
                    "metadata": source.metadata.model_dump(mode="json"),
                }
                for source in self.requirement_sources
            ],
            "source_ids": list(self.source_ids),
            "source_fingerprints": self.source_fingerprints,
            "limitations": list(self.limitations),
        }