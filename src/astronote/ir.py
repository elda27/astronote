from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass(frozen=True)
class SourceLocation:
    path: str
    lineno: int
    end_lineno: int
    col_offset: int
    end_col_offset: int


@dataclass(frozen=True)
class DecoratorIR:
    raw: str
    kind: Literal["entrypoint", "non_entrypoint", "unsupported"]
    resolved_name: str | None = None
    via_alias: str | None = None
    is_call: bool = False
    reason: str | None = None


@dataclass(frozen=True)
class FunctionArgIR:
    name: str
    kind: Literal["positional", "kwonly", "vararg", "kwarg"]
    annotation: str | None = None
    default: Any = None


@dataclass(frozen=True)
class FunctionSignatureIR:
    args: list[FunctionArgIR]
    return_annotation: str | None = None


@dataclass(frozen=True)
class UnsupportedCase:
    message: str
    location: SourceLocation


@dataclass(frozen=True)
class StaticFunctionIR:
    name: str
    signature: FunctionSignatureIR
    location: SourceLocation
    decorators: list[DecoratorIR]
    is_entrypoint: bool = False


@dataclass(frozen=True)
class StaticIR:
    @dataclass(frozen=True)
    class Function(StaticFunctionIR):
        pass

    module_path: str
    import_aliases: dict[str, str]
    functions: list[StaticFunctionIR]
    entrypoints: list[str]
    unsupported: list[UnsupportedCase] = field(default_factory=list)


@dataclass(frozen=True)
class ResolvedIR:
    static_ir: StaticIR
    entrypoint_name: str
    signature: FunctionSignatureIR
    resolved_parameters: dict[str, Any]
    parameter_sources: dict[str, Literal["cli_override", "parameter_json", "signature_default"]]
