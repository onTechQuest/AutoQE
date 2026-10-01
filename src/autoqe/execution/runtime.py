"""Internal execution capabilities; the frozen M0 interfaces remain unchanged."""

from dataclasses import dataclass
from typing import Mapping, Protocol

from autoqe.contracts.project_profile import ProjectProfile
from autoqe.contracts.test_spec import TestLayer, TestSpec
from autoqe.interfaces.execution_provider import ExecutionProvider


@dataclass(frozen=True)
class ExecutionSetup:
    environment_identity: Mapping[str, str]
    reset_identity: str | None


class ExecutionSetupAdapter(Protocol):
    def prepare_execution(self, test_spec: TestSpec, profile: ProjectProfile) -> ExecutionSetup: ...


class CheckedExecutionProvider(ExecutionProvider, Protocol):
    provider_name: str
    provider_version: str
    execution_layer: TestLayer

    def capability_errors(self, test_spec: TestSpec) -> tuple[str, ...]: ...
