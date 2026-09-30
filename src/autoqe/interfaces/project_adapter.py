from typing import Mapping, Protocol

from autoqe.contracts.project_profile import ProjectProfile


class ProjectAdapter(Protocol):
    def reset_environment(self, project_profile: ProjectProfile) -> Mapping[str, str]: ...

    def setup_test_data(
        self,
        project_profile: ProjectProfile,
        data_requirements: tuple[str, ...],
    ) -> Mapping[str, str]: ...

    def authenticate_if_needed(self, project_profile: ProjectProfile) -> Mapping[str, str]: ...