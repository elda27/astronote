from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from astronote.ir import FunctionSignatureIR, ResolvedIR, StaticIR


class ParameterFileError(ValueError):
    """Raised when a parameter file or CLI override cannot be resolved."""


@dataclass(frozen=True)
class ParameterField:
    name: str
    annotation: str | None
    required: bool
    kind: str
    default: Any = None


@dataclass(frozen=True)
class ParameterSchema:
    entrypoint: str
    fields: list[ParameterField]

    def as_dict(self) -> dict[str, Any]:
        return {
            "entrypoint": self.entrypoint,
            "fields": [
                {
                    "name": field.name,
                    "kind": field.kind,
                    "type": field.annotation,
                    "required": field.required,
                    "default": field.default,
                }
                for field in self.fields
            ],
        }


@dataclass(frozen=True)
class LoadedParameters:
    values: dict[str, Any]
    source_path: str | None
    schema: ParameterSchema


@dataclass(frozen=True)
class ParameterResolution:
    resolved_ir: ResolvedIR
    parameter_file: str | None
    schema: ParameterSchema
    cli_overrides: dict[str, Any]


def _function_for_entrypoint(static_ir: StaticIR, entrypoint: str):
    function = next((fn for fn in static_ir.functions if fn.name == entrypoint), None)
    if function is None:
        raise ParameterFileError(f"Entrypoint {entrypoint!r} was not found.")
    if not function.is_entrypoint:
        raise ParameterFileError(f"Function {entrypoint!r} is not marked as an entrypoint.")
    return function


def build_parameter_schema(signature: FunctionSignatureIR, *, entrypoint: str) -> ParameterSchema:
    return ParameterSchema(
        entrypoint=entrypoint,
        fields=[
            ParameterField(
                name=arg.name,
                annotation=arg.annotation,
                required=not arg.has_default and arg.kind not in {"vararg", "kwarg"},
                kind=arg.kind,
                default=arg.default,
            )
            for arg in signature.args
        ],
    )


def load_parameter_file(
    static_ir: StaticIR,
    *,
    entrypoint: str,
    parameter_file: str | Path | None = None,
) -> LoadedParameters:
    function = _function_for_entrypoint(static_ir, entrypoint)
    schema = build_parameter_schema(function.signature, entrypoint=entrypoint)
    if parameter_file is None:
        return LoadedParameters(values={}, source_path=None, schema=schema)

    path = Path(parameter_file)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ParameterFileError("Parameter JSON must decode to an object.")
    return LoadedParameters(values=payload, source_path=str(path), schema=schema)


def parse_cli_overrides(overrides: list[str]) -> dict[str, Any]:
    parsed: dict[str, Any] = {}
    for override in overrides:
        if "=" not in override:
            raise ParameterFileError(f"Override {override!r} must use KEY=JSON syntax.")
        key, raw_value = override.split("=", 1)
        if not key:
            raise ParameterFileError("Override key must not be empty.")
        try:
            parsed[key] = json.loads(raw_value)
        except json.JSONDecodeError as exc:
            raise ParameterFileError(f"Override {override!r} is not valid JSON.") from exc
    return parsed


def resolve_entrypoint_parameters(
    static_ir: StaticIR,
    *,
    entrypoint: str,
    parameter_file: str | Path | None = None,
    cli_overrides: dict[str, Any] | None = None,
) -> ParameterResolution:
    from astronote.analysis.pipeline import resolve_parameters

    loaded = load_parameter_file(static_ir, entrypoint=entrypoint, parameter_file=parameter_file)
    overrides = cli_overrides or {}
    resolved_ir = resolve_parameters(
        static_ir,
        entrypoint=entrypoint,
        parameter_json=loaded.source_path,
        cli_overrides=overrides,
    )
    return ParameterResolution(
        resolved_ir=resolved_ir,
        parameter_file=loaded.source_path,
        schema=loaded.schema,
        cli_overrides=overrides,
    )
