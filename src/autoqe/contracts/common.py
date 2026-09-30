import re
from datetime import datetime, timezone
from enum import StrEnum
from typing import Annotated, Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


Identifier = Annotated[
    str,
    StringConstraints(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$"),
]


_SENSITIVE_KEYS = {
    "api_key",
    "access_token",
    "refresh_token",
    "auth_token",
    "password",
    "passwd",
    "secret",
    "client_secret",
    "private_key",
    "cookie",
    "cookies",
    "headers",
    "raw_headers",
    "request_body",
    "response_body",
    "environment_secrets",
}
_SECRET_VALUE = re.compile(
    r"(?i)(?:\bBearer\s+\S+|\bsk-[A-Za-z0-9_-]{12,}|\bgh[pousr]_[A-Za-z0-9_]{12,}|\bAKIA[A-Z0-9]{16}\b)"
)


def _reject_sensitive_fields(value: Any, path: str = "artifact") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            normalized = re.sub(r"[-\s]", "_", str(key)).lower()
            if normalized in _SENSITIVE_KEYS:
                raise ValueError(f"sensitive field is not allowed: {path}.{key}")
            _reject_sensitive_fields(item, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _reject_sensitive_fields(item, f"{path}[{index}]")
    elif isinstance(value, str) and _SECRET_VALUE.search(value):
        raise ValueError(f"credential-like value is not allowed: {path}")


class PrivacySafeModel(StrictModel):
    @model_validator(mode="before")
    @classmethod
    def reject_sensitive_input(cls, value: Any) -> Any:
        _reject_sensitive_fields(value)
        return value


class ProvenanceModel(PrivacySafeModel):
    schema_version: Literal["1.0"] = "1.0"
    record_id: UUID = Field(default_factory=uuid4)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    source_ids: list[Identifier] = Field(default_factory=list)
    source_fingerprints: dict[str, str] = Field(default_factory=dict)
    correlation_id: UUID | None = None
    producer: str = "autoqe"
    producer_version: str = "0.1.0"
    limitations: list[str] = Field(default_factory=list)

    @field_validator("created_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("created_at must include a timezone")
        return value


class Availability(StrEnum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"
    UNKNOWN = "UNKNOWN"


class RiskLevel(StrEnum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    UNKNOWN = "UNKNOWN"


class EvidenceReference(PrivacySafeModel):
    kind: str
    uri: str
    sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    description: str | None = None

    @field_validator("uri")
    @classmethod
    def require_safe_reference(cls, value: str) -> str:
        if "?" in value or "#" in value or "@" in value:
            raise ValueError("evidence references must not contain query, fragment, or userinfo")
        return value