from __future__ import annotations

import ast
from typing import Literal

from astronote._model import FrozenModel


class DecoratorResolutionError(ValueError):
    """Raised when a decorator cannot be statically resolved."""


class DecoratorResolution(FrozenModel):
    raw: str
    kind: Literal["entrypoint", "non_entrypoint", "unsupported"]
    resolved_name: str | None = None
    reason: str | None = None
    via_alias: str | None = None
    is_call: bool = False


class ImportAliasMap:
    def __init__(self) -> None:
        self._aliases: dict[str, str] = {}
        self._skipped: list[tuple[str, ast.stmt]] = []

    @property
    def aliases(self) -> dict[str, str]:
        return dict(self._aliases)

    @property
    def skipped(self) -> list[tuple[str, ast.stmt]]:
        """Unsupported import statements that could not be resolved."""
        return list(self._skipped)

    def register_import(self, node: ast.Import) -> None:
        for alias in node.names:
            name = alias.asname or alias.name
            self._aliases[name] = alias.name

    def register_import_from(self, node: ast.ImportFrom) -> None:
        if node.level != 0:
            self._skipped.append(
                ("Relative imports are unsupported for decorator resolution.", node),
            )
            return
        if node.module is None:
            self._skipped.append(
                ("Dynamic import-from statements are unsupported.", node),
            )
            return
        for alias in node.names:
            if alias.name == "*":
                self._skipped.append(("Star imports are unsupported.", node))
                return
            name = alias.asname or alias.name
            self._aliases[name] = f"{node.module}.{alias.name}"

    def resolve_expr(self, expr: ast.expr) -> str:
        if isinstance(expr, ast.Name):
            return self._aliases.get(expr.id, expr.id)
        if isinstance(expr, ast.Attribute):
            base = self.resolve_expr(expr.value)
            return f"{base}.{expr.attr}"
        raise DecoratorResolutionError(
            f"Unsupported decorator expression: {ast.dump(expr, include_attributes=False)}",
        )


def build_import_alias_map(module: ast.Module) -> ImportAliasMap:
    alias_map = ImportAliasMap()
    for node in module.body:
        if isinstance(node, ast.Import):
            alias_map.register_import(node)
        elif isinstance(node, ast.ImportFrom):
            alias_map.register_import_from(node)
    return alias_map


def resolve_notebook_entry_decorator(
    decorator: ast.expr,
    alias_map: ImportAliasMap,
) -> DecoratorResolution:
    target = decorator
    is_call = False
    if isinstance(decorator, ast.Call):
        target = decorator.func
        is_call = True

    try:
        resolved = alias_map.resolve_expr(target)
    except DecoratorResolutionError as exc:
        return DecoratorResolution(
            raw=ast.unparse(decorator),
            kind="unsupported",
            reason=str(exc),
            is_call=is_call,
        )

    if resolved == "astronote.notebook_entry":
        via_alias = target.id if isinstance(target, ast.Name) and target.id != resolved else None
        return DecoratorResolution(
            raw=ast.unparse(decorator),
            kind="entrypoint",
            resolved_name=resolved,
            via_alias=via_alias,
            is_call=is_call,
        )

    # Only treat as unsupported re-export when the resolved name is qualified
    # (contains a module path), to avoid false positives for locally-defined
    # decorators that happen to be named notebook_entry.
    if resolved.endswith("notebook_entry") and "." in resolved:
        return DecoratorResolution(
            raw=ast.unparse(decorator),
            kind="unsupported",
            resolved_name=resolved,
            reason="Decorator looks like notebook_entry but comes from an unsupported re-export.",
            is_call=is_call,
        )

    return DecoratorResolution(
        raw=ast.unparse(decorator),
        kind="non_entrypoint",
        resolved_name=resolved,
        is_call=is_call,
    )
