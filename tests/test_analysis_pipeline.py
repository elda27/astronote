from __future__ import annotations

import json
from pathlib import Path

from astronote.analysis import analyze_python_file, resolve_parameters


SAMPLE = '''
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
'''

UNSUPPORTED = '''
from another_pkg import notebook_entry

@notebook_entry
def broken():
    return None
'''


def test_analyze_python_file_extracts_signatures_and_entrypoints(tmp_path: Path) -> None:
    target = tmp_path / "sample.py"
    target.write_text(SAMPLE, encoding="utf-8")

    ir = analyze_python_file(target)

    assert ir.import_aliases["entry"] == "astronote.notebook_entry"
    assert ir.entrypoints == ["run", "via_alias", "via_module"]
    assert [fn.name for fn in ir.functions] == ["run", "via_alias", "via_module"]
    assert ir.functions[0].signature.args[0].annotation == "int"
    assert ir.functions[0].signature.args[1].default == "'x'"
    assert ir.functions[1].decorators[0].via_alias == "entry"
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
    assert resolved.parameter_sources == {"alpha": "parameter_json", "beta": "cli_override"}
