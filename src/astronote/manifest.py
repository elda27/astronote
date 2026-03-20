from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from astronote import __version__
from astronote.params import ParameterResolution


@dataclass(frozen=True)
class Manifest:
    source_path: str
    entrypoint: str
    generated_at: str
    tool_version: str
    parameters: dict[str, Any]
    parameter_sources: dict[str, str]
    parameter_file: str | None
    parameter_schema: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_path": self.source_path,
            "entrypoint": self.entrypoint,
            "generated_at": self.generated_at,
            "tool_version": self.tool_version,
            "parameter_file": self.parameter_file,
            "parameters": self.parameters,
            "parameter_sources": self.parameter_sources,
            "parameter_schema": self.parameter_schema,
        }


def build_manifest(source_path: str, resolution: ParameterResolution) -> Manifest:
    resolved_ir = resolution.resolved_ir
    return Manifest(
        source_path=source_path,
        entrypoint=resolved_ir.entrypoint_name,
        generated_at=datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        tool_version=__version__,
        parameter_file=resolution.parameter_file,
        parameters=resolved_ir.resolved_parameters,
        parameter_sources=resolved_ir.parameter_sources,
        parameter_schema=resolution.schema.as_dict(),
    )
