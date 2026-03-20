from __future__ import annotations

import ast

import pytest
from pydantic import BaseModel

from astronote.analysis.resolver import (
    DecoratorResolutionError,
    ImportAliasMap,
    build_import_alias_map,
    resolve_notebook_entry_decorator,
)


def _function_from_module(module: ast.Module) -> ast.FunctionDef | ast.AsyncFunctionDef:
    return next(node for node in module.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)))


def test_build_import_alias_map_collects_import_and_from_aliases() -> None:
    module = ast.parse(
        "import astronote as an\nfrom astronote import notebook_entry as entry\n",
    )

    alias_map = build_import_alias_map(module)

    assert alias_map.aliases == {
        "an": "astronote",
        "entry": "astronote.notebook_entry",
    }
    assert alias_map.skipped == []


def test_build_import_alias_map_records_unsupported_imports() -> None:
    module = ast.parse(
        "from . import notebook_entry\nfrom pkg import *\n",
    )

    alias_map = build_import_alias_map(module)

    reasons = [reason for reason, _ in alias_map.skipped]
    assert reasons == [
        "Relative imports are unsupported for decorator resolution.",
        "Star imports are unsupported.",
    ]


def test_resolve_notebook_entry_decorator_marks_alias_call_as_entrypoint() -> None:
    module = ast.parse(
        "from astronote import notebook_entry as entry\n\n@entry(name='daily')\ndef run():\n    pass\n",
    )
    alias_map = build_import_alias_map(module)
    function = _function_from_module(module)

    resolution = resolve_notebook_entry_decorator(function.decorator_list[0], alias_map)

    assert isinstance(resolution, BaseModel)
    assert resolution.kind == "entrypoint"
    assert resolution.resolved_name == "astronote.notebook_entry"
    assert resolution.via_alias == "entry"
    assert resolution.is_call is True


def test_resolve_notebook_entry_decorator_marks_reexport_as_unsupported() -> None:
    module = ast.parse(
        "from another_pkg import notebook_entry\n\n@notebook_entry\ndef run():\n    pass\n",
    )
    alias_map = build_import_alias_map(module)
    function = _function_from_module(module)

    resolution = resolve_notebook_entry_decorator(function.decorator_list[0], alias_map)

    assert resolution.kind == "unsupported"
    assert resolution.resolved_name == "another_pkg.notebook_entry"
    assert "unsupported re-export" in (resolution.reason or "")


def test_import_alias_map_resolve_expr_rejects_non_name_or_attribute() -> None:
    alias_map = ImportAliasMap()
    expr = ast.parse("factory()", mode="eval").body

    with pytest.raises(DecoratorResolutionError, match="Unsupported decorator expression"):
        alias_map.resolve_expr(expr)