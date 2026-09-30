from typing import Protocol

from autoqe.contracts.execution_record import ExecutionRecord
from autoqe.contracts.project_profile import ProjectProfile
from autoqe.contracts.test_spec import TestSpec


class ExecutionProvider(Protocol):
    def supports(self, test_spec: TestSpec) -> bool: ...

    def execute(self, test_spec: TestSpec, project_profile: ProjectProfile) -> ExecutionRecord: ...