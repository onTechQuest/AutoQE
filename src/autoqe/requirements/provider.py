from pathlib import Path
from typing import Protocol, Sequence

from autoqe.requirements.models import RequirementSource


class RequirementProvider(Protocol):
    def load(self, paths: Sequence[str | Path]) -> tuple[RequirementSource, ...]: ...