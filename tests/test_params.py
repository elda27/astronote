from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import BaseModel

from astronote.analysis import analyze_python_file
from astronote.params import (
    LoadedParameters,
    ParameterField,
    ParameterFileError,
    ParameterResolution,
    ParameterSchema,
    build_parameter_schema,
    load_parameter_file,
    parse_cli_overrides,
    resolve_entrypoint_parameters,
)

SOURCE = """
from astronote import notebook_entry

@notebook_entry
def run(alpha: int, beta: str = "x", *values: float, debug: bool = False, **options: dict[str, str]) -> None:
    return None
"""

NON_ENTRYPOINT_SOURCE = """
def run(alpha: int) -> None:
    return None
"""


def _write_source(tmp_path: Path, source: str = SOURCE) -> Path:
    target = tmp_path / "sample.py"
    target.write_text(source, encoding="utf-8")
    return target


def test_parameter_models_are_pydantic_models() -> None:
    models = [LoadedParameters, ParameterField, ParameterResolution, ParameterSchema]

    assert all(issubclass(model, BaseModel) for model in models)


def test_build_parameter_schema_marks_required_and_variadic_fields(
    tmp_path: Path,
) -> None:
    target = _write_source(tmp_path)
    static_ir = analyze_python_file(target)

    schema = build_parameter_schema(static_ir.functions[0].signature, entrypoint="run")

    assert schema.as_dict() == {
        "entrypoint": "run",
        "fields": [
            {
                "name": "alpha",
                "kind": "positional",
                "type": "int",
                "required": True,
                "default": None,
            },
            {
                "name": "beta",
                "kind": "positional",
                "type": "str",
                "required": False,
                "default": "x",
            },
            {
                "name": "values",
                "kind": "vararg",
                "type": "float",
                "required": False,
                "default": None,
            },
            {
                "name": "debug",
                "kind": "kwonly",
                "type": "bool",
                "required": False,
                "default": False,
            },
            {
                "name": "options",
                "kind": "kwarg",
                "type": "dict[str, str]",
                "required": False,
                "default": None,
            },
        ],
    }


def test_load_parameter_file_returns_empty_values_without_file(tmp_path: Path) -> None:
    target = _write_source(tmp_path)
    static_ir = analyze_python_file(target)

    loaded = load_parameter_file(static_ir, entrypoint="run")

    assert isinstance(loaded, LoadedParameters)
    assert loaded.values == {}
    assert loaded.source_path is None
    assert loaded.parameter_schema.entrypoint == "run"


def test_load_parameter_file_rejects_non_object_json(tmp_path: Path) -> None:
    target = _write_source(tmp_path)
    params = tmp_path / "params.json"
    params.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
    static_ir = analyze_python_file(target)

    with pytest.raises(ParameterFileError, match="decode to an object"):
        load_parameter_file(static_ir, entrypoint="run", parameter_file=params)


def test_load_parameter_file_rejects_non_entrypoint_function(tmp_path: Path) -> None:
    target = _write_source(tmp_path, NON_ENTRYPOINT_SOURCE)
    static_ir = analyze_python_file(target)

    with pytest.raises(ParameterFileError, match="not marked as an entrypoint"):
        load_parameter_file(static_ir, entrypoint="run")


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        (["alpha"], "must use KEY=JSON syntax"),
        (["=1"], "must not be empty"),
        (["alpha=oops"], "not valid JSON"),
    ],
)
def test_parse_cli_overrides_rejects_invalid_input(
    overrides: list[str], message: str
) -> None:
    with pytest.raises(ParameterFileError) as exc_info:
        parse_cli_overrides(overrides)

    assert message in str(exc_info.value)


def test_resolve_entrypoint_parameters_returns_resolution_metadata(
    tmp_path: Path,
) -> None:
    target = _write_source(tmp_path)
    params = tmp_path / "params.json"
    params.write_text(json.dumps({"alpha": 10}), encoding="utf-8")
    static_ir = analyze_python_file(target)

    resolution = resolve_entrypoint_parameters(
        static_ir,
        entrypoint="run",
        parameter_file=params,
        cli_overrides={"beta": "from_cli"},
    )

    assert isinstance(resolution, ParameterResolution)
    assert resolution.parameter_file == str(params)
    assert resolution.cli_overrides == {"beta": "from_cli"}
    assert resolution.parameter_schema.entrypoint == "run"
    assert resolution.resolved_ir.resolved_parameters == {
        "alpha": 10,
        "beta": "from_cli",
        "debug": False,
    }
    assert resolution.resolved_ir.parameter_sources == {
        "alpha": "parameter_json",
        "beta": "cli_override",
        "debug": "signature_default",
    }
