import json
from pathlib import Path

import pytest
from pydantic import BaseModel

from astronote.analysis import analyze_python_file, resolve_parameters

SAMPLE = """
from astronote import notebook_entry
from astronote import notebook_entry as entry
import astronote as an

@notebook_entry
def run(alpha: int, beta: str = "x") -> None:
    return None

@entry(timeout=3)
def via_alias(gamma: float) -> int:
    return 1

@an.notebook_entry()
def via_module(delta, *, eps: bool = True):
    return delta
"""

UNSUPPORTED = """
from another_pkg import notebook_entry

@notebook_entry
def broken():
    return None
"""


STAR_IMPORT = """
from pkg import *

@notebook_entry
def star():
    return None
"""

LOCAL_NOTEBOOK_ENTRY = """
def notebook_entry(f):
    return f

@notebook_entry
def local_func():
    return None
"""

RELATIVE_IMPORT = """
from . import notebook_entry

@notebook_entry
def relative_func():
    return None
"""


def test_analyze_python_file_extracts_signatures_and_entrypoints(
    tmp_path: Path,
) -> None:
    target = tmp_path / "sample.py"
    target.write_text(SAMPLE, encoding="utf-8")

    ir = analyze_python_file(target)

    assert isinstance(ir, BaseModel)
    assert isinstance(ir.functions[0], BaseModel)
    assert ir.import_aliases["entry"] == "astronote.notebook_entry"
    assert ir.entrypoints == ["run", "via_alias", "via_module"]
    assert [fn.name for fn in ir.functions] == ["run", "via_alias", "via_module"]
    assert ir.functions[0].signature.args[0].annotation == "int"
    assert ir.functions[0].signature.args[1].default == "x"
    assert ir.functions[1].decorators[0].via_alias == "entry"
    assert ir.functions[1].decorators[0].name is None
    assert ir.functions[1].decorators[0].save_to is None
    assert ir.functions[2].decorators[0].resolved_name == "astronote.notebook_entry"


def test_analyze_python_file_marks_unsupported_reexport(tmp_path: Path) -> None:
    target = tmp_path / "unsupported.py"
    target.write_text(UNSUPPORTED, encoding="utf-8")

    ir = analyze_python_file(target)

    assert ir.entrypoints == []
    assert len(ir.unsupported) == 1
    assert "unsupported re-export" in ir.unsupported[0].message


def test_resolve_parameters_applies_json_then_cli_override(tmp_path: Path) -> None:
    target = tmp_path / "sample.py"
    target.write_text(SAMPLE, encoding="utf-8")
    params = tmp_path / "params.json"
    params.write_text(json.dumps({"alpha": 10, "beta": "from_json"}), encoding="utf-8")

    ir = analyze_python_file(target)
    resolved = resolve_parameters(
        ir,
        entrypoint="run",
        parameter_json=params,
        cli_overrides={"beta": "from_cli"},
    )

    assert resolved.resolved_parameters == {"alpha": 10, "beta": "from_cli"}
    assert resolved.parameter_sources == {
        "alpha": "parameter_json",
        "beta": "cli_override",
    }


def test_resolve_parameters_rejects_unknown_overrides(tmp_path: Path) -> None:
    target = tmp_path / "sample.py"
    target.write_text(SAMPLE, encoding="utf-8")
    params = tmp_path / "params.json"
    params.write_text(json.dumps({"alpha": 10, "gamma": 1}), encoding="utf-8")

    ir = analyze_python_file(target)

    with pytest.raises(ValueError, match=r"Unknown parameter override\(s\): gamma"):
        resolve_parameters(ir, entrypoint="run", parameter_json=params)


def test_analyze_python_file_star_import_recorded_as_unsupported(
    tmp_path: Path,
) -> None:
    target = tmp_path / "star.py"
    target.write_text(STAR_IMPORT, encoding="utf-8")

    ir = analyze_python_file(target)

    assert len(ir.unsupported) >= 1
    assert any("Star imports" in unsupported.message for unsupported in ir.unsupported)


def test_analyze_python_file_local_notebook_entry_not_flagged(tmp_path: Path) -> None:
    target = tmp_path / "local.py"
    target.write_text(LOCAL_NOTEBOOK_ENTRY, encoding="utf-8")

    ir = analyze_python_file(target)

    assert ir.entrypoints == []
    assert ir.unsupported == []
    local_func = next(fn for fn in ir.functions if fn.name == "local_func")
    assert local_func.decorators[0].kind == "non_entrypoint"


def test_analyze_python_file_relative_import_recorded_as_unsupported(
    tmp_path: Path,
) -> None:
    target = tmp_path / "relative.py"
    target.write_text(RELATIVE_IMPORT, encoding="utf-8")

    ir = analyze_python_file(target)

    assert len(ir.unsupported) >= 1
    assert any(
        "Relative imports" in unsupported.message for unsupported in ir.unsupported
    )


def test_resolve_parameters_uses_evaluated_signature_default(tmp_path: Path) -> None:
    source = """
from astronote import notebook_entry

@notebook_entry
def fn(x: int = 42, y: str = "hello") -> None:
    pass
"""
    target = tmp_path / "defaults.py"
    target.write_text(source, encoding="utf-8")

    ir = analyze_python_file(target)
    resolved = resolve_parameters(ir, entrypoint="fn")

    assert resolved.resolved_parameters == {"x": 42, "y": "hello"}
    assert resolved.parameter_sources == {
        "x": "signature_default",
        "y": "signature_default",
    }
