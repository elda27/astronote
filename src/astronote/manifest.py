from datetime import datetime, timezone
from typing import Any, Literal

from astronote import __version__
from astronote._model import FrozenModel
from astronote.params import ParameterResolution


class Manifest(FrozenModel):
    source_path: str
    entrypoint: str
    generated_at: str
    tool_version: str
    parameters: dict[str, Any]
    parameter_sources: dict[
        str, Literal["cli_override", "parameter_json", "signature_default"]
    ]
    parameter_file: str | None
    parameter_schema: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="python")


def build_manifest(source_path: str, resolution: ParameterResolution) -> Manifest:
    resolved_ir = resolution.resolved_ir
    return Manifest(
        source_path=source_path,
        entrypoint=resolved_ir.entrypoint_name,
        generated_at=datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z"),
        tool_version=__version__,
        parameter_file=resolution.parameter_file,
        parameters=resolved_ir.resolved_parameters,
        parameter_sources=resolved_ir.parameter_sources,
        parameter_schema=resolution.parameter_schema.as_dict(),
    )
