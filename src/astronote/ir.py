from __future__ import annotations

from typing import Any, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field


class FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SourceLocation(FrozenModel):
    path: str
    lineno: int
    end_lineno: int
    col_offset: int
    end_col_offset: int


class DecoratorIR(FrozenModel):
    raw: str
    kind: Literal["entrypoint", "non_entrypoint", "unsupported"]
    resolved_name: str | None = None
    via_alias: str | None = None
    is_call: bool = False
    reason: str | None = None


class FunctionArgIR(FrozenModel):
    name: str
    kind: Literal["positional", "kwonly", "vararg", "kwarg"]
    annotation: str | None = None
    default: Any = None
    has_default: bool = False


class FunctionSignatureIR(FrozenModel):
    args: list[FunctionArgIR]
    return_annotation: str | None = None


class UnsupportedCase(FrozenModel):
    message: str
    location: SourceLocation


class StaticFunctionIR(FrozenModel):
    name: str
    signature: FunctionSignatureIR
    location: SourceLocation
    decorators: list[DecoratorIR]
    is_entrypoint: bool = False


class StaticFunction(StaticFunctionIR):
    pass


class StaticIR(FrozenModel):
    Function: ClassVar[type[StaticFunction]] = StaticFunction

    module_path: str
    import_aliases: dict[str, str]
    functions: list[StaticFunctionIR]
    entrypoints: list[str]
    unsupported: list[UnsupportedCase] = Field(default_factory=list)


class ResolvedIR(FrozenModel):
    static_ir: StaticIR
    entrypoint_name: str
    signature: FunctionSignatureIR
    resolved_parameters: dict[str, Any]
    parameter_sources: dict[
        str, Literal["cli_override", "parameter_json", "signature_default"]
    ]
