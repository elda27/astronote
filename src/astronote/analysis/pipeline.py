from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

from astronote.ir import (
    DecoratorIR,
    FunctionArgIR,
    FunctionSignatureIR,
    ResolvedIR,
    SourceLocation,
    StaticIR,
    UnsupportedCase,
)

from .resolver import build_import_alias_map, resolve_notebook_entry_decorator


def _annotation_to_str(node: ast.expr | None) -> str | None:
    return ast.unparse(node) if node is not None else None


def _expr_to_str(node: ast.expr | None) -> str | None:
    return ast.unparse(node) if node is not None else None


def _build_signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> FunctionSignatureIR:
    args: list[FunctionArgIR] = []
    positional = [*node.args.posonlyargs, *node.args.args]
    positional_defaults: list[ast.expr | None] = [None] * (len(positional) - len(node.args.defaults)) + list(node.args.defaults)

    for arg, default in zip(positional, positional_defaults, strict=True):
        args.append(
            FunctionArgIR(
                name=arg.arg,
                kind="positional",
                annotation=_annotation_to_str(arg.annotation),
                default=_expr_to_str(default),
            ),
        )

    if node.args.vararg is not None:
        args.append(
            FunctionArgIR(
                name=node.args.vararg.arg,
                kind="vararg",
                annotation=_annotation_to_str(node.args.vararg.annotation),
            ),
        )

    for arg, default in zip(node.args.kwonlyargs, node.args.kw_defaults, strict=True):
        args.append(
            FunctionArgIR(
                name=arg.arg,
                kind="kwonly",
                annotation=_annotation_to_str(arg.annotation),
                default=_expr_to_str(default),
            ),
        )

    if node.args.kwarg is not None:
        args.append(
            FunctionArgIR(
                name=node.args.kwarg.arg,
                kind="kwarg",
                annotation=_annotation_to_str(node.args.kwarg.annotation),
            ),
        )

    return FunctionSignatureIR(args=args, return_annotation=_annotation_to_str(node.returns))


def analyze_python_file(path: str | Path) -> StaticIR:
    source_path = Path(path)
    module = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
    alias_map = build_import_alias_map(module)

    functions = []
    entrypoints = []
    unsupported: list[UnsupportedCase] = []

    for node in module.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue

        decorators: list[DecoratorIR] = []
        is_entrypoint = False
        for decorator in node.decorator_list:
            resolution = resolve_notebook_entry_decorator(decorator, alias_map)
            decorator_ir = DecoratorIR(
                raw=resolution.raw,
                kind=resolution.kind,
                resolved_name=resolution.resolved_name,
                via_alias=resolution.via_alias,
                is_call=resolution.is_call,
                reason=resolution.reason,
            )
            decorators.append(decorator_ir)
            if resolution.kind == "entrypoint":
                is_entrypoint = True
            elif resolution.kind == "unsupported":
                unsupported.append(
                    UnsupportedCase(
                        message=resolution.reason or "Unsupported decorator resolution.",
                        location=SourceLocation(
                            path=str(source_path),
                            lineno=decorator.lineno,
                            end_lineno=getattr(decorator, "end_lineno", decorator.lineno),
                            col_offset=decorator.col_offset,
                            end_col_offset=getattr(decorator, "end_col_offset", decorator.col_offset),
                        ),
                    ),
                )

        function_ir = StaticIR.Function(
            name=node.name,
            signature=_build_signature(node),
            location=SourceLocation(
                path=str(source_path),
                lineno=node.lineno,
                end_lineno=getattr(node, "end_lineno", node.lineno),
                col_offset=node.col_offset,
                end_col_offset=getattr(node, "end_col_offset", node.col_offset),
            ),
            decorators=decorators,
            is_entrypoint=is_entrypoint,
        )
        functions.append(function_ir)
        if is_entrypoint:
            entrypoints.append(node.name)

    return StaticIR(
        module_path=str(source_path),
        import_aliases=alias_map.aliases,
        functions=functions,
        entrypoints=entrypoints,
        unsupported=unsupported,
    )


def resolve_parameters(
    static_ir: StaticIR,
    *,
    entrypoint: str,
    parameter_json: str | Path | None = None,
    cli_overrides: dict[str, Any] | None = None,
) -> ResolvedIR:
    function = next((fn for fn in static_ir.functions if fn.name == entrypoint), None)
    if function is None:
        raise ValueError(f"Entrypoint {entrypoint!r} was not found.")
    if not function.is_entrypoint:
        raise ValueError(f"Function {entrypoint!r} is not marked as an entrypoint.")

    file_parameters: dict[str, Any] = {}
    if parameter_json is not None:
        file_parameters = json.loads(Path(parameter_json).read_text(encoding="utf-8"))
        if not isinstance(file_parameters, dict):
            raise ValueError("Parameter JSON must decode to an object.")

    overrides = cli_overrides or {}
    resolved_parameters: dict[str, Any] = {}
    sources: dict[str, str] = {}

    for arg in function.signature.args:
        if arg.name in file_parameters:
            resolved_parameters[arg.name] = file_parameters[arg.name]
            sources[arg.name] = "parameter_json"
        if arg.default is not None and arg.name not in resolved_parameters:
            resolved_parameters[arg.name] = arg.default
            sources[arg.name] = "signature_default"
        if arg.name in overrides:
            resolved_parameters[arg.name] = overrides[arg.name]
            sources[arg.name] = "cli_override"

    known_parameters = {arg.name for arg in function.signature.args}
    unknown = sorted((set(file_parameters) | set(overrides)) - known_parameters)
    if unknown:
        raise ValueError(f"Unknown parameter override(s): {', '.join(unknown)}")

    return ResolvedIR(
        static_ir=static_ir,
        entrypoint_name=entrypoint,
        signature=function.signature,
        resolved_parameters=resolved_parameters,
        parameter_sources=sources,
    )
