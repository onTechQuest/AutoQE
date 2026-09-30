from typing import Mapping, Protocol


class ModelProvider(Protocol):
    def generate_structured(
        self,
        task: str,
        context: Mapping[str, object],
        output_schema: Mapping[str, object],
    ) -> Mapping[str, object]: ...