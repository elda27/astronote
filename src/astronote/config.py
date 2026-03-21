from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

from astronote._model import FrozenModel


class PyprojectConfigError(ValueError):
    """Raised when pyproject.toml contains invalid Astronote CLI settings."""


class PyprojectCliOptions(FrozenModel):
    source: Path | None = None
    parameter_file: Path | None = None
    override: list[str] = []
    entrypoint: str | None = None
    expand_module: list[str] = []
    embed_file: list[str] = []
    output: Path | None = None
    show_analysis: bool | None = None
    show_schema: bool | None = None
    config_path: Path | None = None


def load_pyproject_cli_options(source: str | None = None) -> PyprojectCliOptions:
    config_path = _find_pyproject_path(source)
    if config_path is None:
        return PyprojectCliOptions()

    payload = tomllib.loads(config_path.read_text(encoding="utf-8"))
    tool_table = payload.get("tool")
    if tool_table is None:
        return PyprojectCliOptions(config_path=config_path)
    if not isinstance(tool_table, dict):
        raise PyprojectConfigError(
            f"Failed to load '{config_path}': [tool] must be a TOML table."
        )

    astronote_table = tool_table.get("astronote")
    if astronote_table is None:
        return PyprojectCliOptions(config_path=config_path)
    if not isinstance(astronote_table, dict):
        raise PyprojectConfigError(
            f"Failed to load '{config_path}': [tool.astronote] must be a TOML table."
        )

    base_dir = config_path.parent
    return PyprojectCliOptions(
        source=_optional_path(astronote_table, "source", base_dir),
        parameter_file=_optional_path(astronote_table, "parameter_file", base_dir),
        override=_optional_str_list(astronote_table, "override"),
        entrypoint=_optional_str(astronote_table, "entrypoint"),
        expand_module=_optional_str_list(astronote_table, "expand_module"),
        embed_file=_optional_str_list(astronote_table, "embed_file"),
        output=_optional_path(astronote_table, "output", base_dir),
        show_analysis=_optional_bool(astronote_table, "show_analysis"),
        show_schema=_optional_bool(astronote_table, "show_schema"),
        config_path=config_path,
    )


def _find_pyproject_path(source: str | None) -> Path | None:
    for start_dir in _search_roots(source):
        for candidate_dir in [start_dir, *start_dir.parents]:
            candidate = candidate_dir / "pyproject.toml"
            if candidate.is_file():
                return candidate
    return None


def _search_roots(source: str | None) -> list[Path]:
    cwd = Path.cwd().resolve()
    roots = [cwd]
    if source is None:
        return roots

    source_path = Path(source)
    if not source_path.is_absolute():
        source_path = (cwd / source_path).resolve()
    else:
        source_path = source_path.resolve()
    source_root = source_path if source_path.is_dir() else source_path.parent
    if source_root not in roots:
        roots.insert(0, source_root)
    return roots


def _optional_path(table: dict[str, Any], key: str, base_dir: Path) -> Path | None:
    value = table.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise PyprojectConfigError(
            f"Failed to load [tool.astronote].{key}: expected a string path."
        )
    path = Path(value)
    if not path.is_absolute():
        path = (base_dir / path).resolve()
    return path


def _optional_str(table: dict[str, Any], key: str) -> str | None:
    value = table.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise PyprojectConfigError(
            f"Failed to load [tool.astronote].{key}: expected a string."
        )
    return value


def _optional_bool(table: dict[str, Any], key: str) -> bool | None:
    value = table.get(key)
    if value is None:
        return None
    if not isinstance(value, bool):
        raise PyprojectConfigError(
            f"Failed to load [tool.astronote].{key}: expected a boolean."
        )
    return value


def _optional_str_list(table: dict[str, Any], key: str) -> list[str]:
    value = table.get(key)
    if value is None:
        return []
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise PyprojectConfigError(
            f"Failed to load [tool.astronote].{key}: expected an array of strings."
        )
    return value
