from enum import StrEnum

from pydantic import AnyHttpUrl, Field, model_validator

from autoqe.contracts.common import Availability, ProvenanceModel, StrictModel


class RequirementProvider(StrEnum):
    LOCAL_FILES = "LOCAL_FILES"
    URLS = "URLS"
    UNKNOWN = "UNKNOWN"


class NetworkScope(StrEnum):
    LOCAL_ONLY = "LOCAL_ONLY"
    REMOTE_ALLOWED = "REMOTE_ALLOWED"
    UNKNOWN = "UNKNOWN"


class AuthenticationStrategy(StrEnum):
    NONE = "NONE"
    TEST_FIXTURE = "TEST_FIXTURE"
    USER_PROVIDED = "USER_PROVIDED"
    UNKNOWN = "UNKNOWN"


class ContractFormat(StrEnum):
    OPENAPI = "OPENAPI"
    JSON_SCHEMA = "JSON_SCHEMA"
    SOURCE_AND_TESTS = "SOURCE_AND_TESTS"
    UNKNOWN = "UNKNOWN"


class RequirementSources(StrictModel):
    provider: RequirementProvider
    locations: list[str] = Field(min_length=1)


class ApplicationEndpoints(StrictModel):
    ui_base_url: AnyHttpUrl | None = None
    api_base_url: AnyHttpUrl | None = None


class RuntimeProfile(StrictModel):
    language: str
    language_version_required: str
    language_version_accepted: str
    language_version_qualified: str
    package_manager: str
    package_manager_version: str


class EnvironmentProfile(StrictModel):
    reset_supported: bool
    reset_adapter: str | None = None
    network_scope: NetworkScope
    readiness_urls: list[AnyHttpUrl] = Field(default_factory=list)
    reset_identity: str | None = None

    @model_validator(mode="after")
    def require_reset_adapter_when_supported(self) -> "EnvironmentProfile":
        if self.reset_supported and not self.reset_adapter:
            raise ValueError("reset_adapter is required when reset_supported is true")
        return self


class AuthenticationProfile(StrictModel):
    strategy: AuthenticationStrategy
    setup_adapter: str | None = None


class ExecutionCapabilities(StrictModel):
    ui: Availability
    api: Availability


class ApiContractProfile(StrictModel):
    location: str
    format: ContractFormat


class ProjectAdapterProfile(StrictModel):
    adapter_id: str
    adapter_version: str


class ReferenceTarget(StrictModel):
    repository_url: AnyHttpUrl
    revision: str = Field(pattern=r"^[0-9a-f]{40}$")


class ProjectProfile(ProvenanceModel):
    project_id: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    project_name: str
    requirements: RequirementSources
    application: ApplicationEndpoints
    runtime: RuntimeProfile
    environment: EnvironmentProfile
    authentication: AuthenticationProfile
    execution_capabilities: ExecutionCapabilities
    api_contract: ApiContractProfile
    project_adapter: ProjectAdapterProfile
    reference_target: ReferenceTarget | None = None

    @model_validator(mode="after")
    def enforce_local_only_endpoints(self) -> "ProjectProfile":
        if self.environment.network_scope != NetworkScope.LOCAL_ONLY:
            return self
        urls = [self.application.ui_base_url, self.application.api_base_url]
        urls.extend(self.environment.readiness_urls)
        for url in urls:
            if url is None:
                continue
            host = url.host.lower().strip("[]")
            if host not in {"localhost", "127.0.0.1", "::1"}:
                raise ValueError("LOCAL_ONLY profiles may use only localhost, 127.0.0.1, or ::1")
            if url.username or url.password:
                raise ValueError("application URLs must not embed credentials")
        return self