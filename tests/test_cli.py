from __future__ import annotations

import json
from pathlib import Path

import pytest

from astronote.cli import (
    AnalysisError,
    EntrypointSelectionError,
    analyze_source,
    build_parser,
    choose_entrypoint,
    generate_notebook,
)

SOURCE = """
from astronote import notebook_entry

@notebook_entry
def run(alpha: int, beta: str = "x") -> None:
    return None
"""

MULTI_SOURCE = """
from astronote import notebook_entry

@notebook_entry
def run() -> None:
    return None

@notebook_entry
def alternate() -> None:
    return None
"""


def test_cli_help_mentions_parameter_file() -> None:
    help_text = build_parser().format_help()

    assert "--parameter-file" in help_text
    assert "--show-schema" in help_text


def test_analyze_source_rejects_non_python_file(tmp_path: Path) -> None:
    target = tmp_path / "sample.txt"
    target.write_text("print('nope')\n", encoding="utf-8")

    with pytest.raises(AnalysisError, match=r"existing \.py source file"):
        analyze_source(str(target))


def test_choose_entrypoint_requires_explicit_name_when_multiple_candidates(
    tmp_path: Path,
) -> None:
    source = tmp_path / "multi.py"
    source.write_text(MULTI_SOURCE, encoding="utf-8")
    analysis = analyze_source(str(source))

    with pytest.raises(EntrypointSelectionError, match="multiple candidates"):
        choose_entrypoint(analysis, None)


def test_generate_notebook_writes_manifest_metadata(tmp_path: Path) -> None:
    source = tmp_path / "sample.py"
    source.write_text(SOURCE, encoding="utf-8")
    params = tmp_path / "params.json"
    params.write_text(json.dumps({"alpha": 7}), encoding="utf-8")
    output = tmp_path / "sample.ipynb"

    analysis = analyze_source(str(source))
    entrypoint = choose_entrypoint(analysis, None)
    generate_notebook(analysis, entrypoint, params, ['beta="override"'], output)

    notebook = json.loads(output.read_text(encoding="utf-8"))
    meta = notebook["metadata"]["astronote"]

    assert meta["manifest"]["source_path"] == str(source.resolve())
    assert meta["manifest"]["entrypoint"] == "run"
    assert meta["manifest"]["parameters"] == {"alpha": 7, "beta": "override"}
    assert meta["manifest"]["parameter_schema"]["fields"][0]["name"] == "alpha"
