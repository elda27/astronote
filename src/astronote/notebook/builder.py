from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any


GENERATED_CELL_METADATA_KEY = "astronote"
GENERATED_NOTEBOOK_VERSION = 1


def _read_field(value: Any, *names: str, default: Any = None) -> Any:
    for name in names:
        if isinstance(value, dict) and name in value:
            return value[name]
        if hasattr(value, name):
            return getattr(value, name)
    return default


def _normalize_lines(source: str | list[str]) -> list[str]:
    if isinstance(source, list):
        return source
    if not source:
        return []
    lines = source.splitlines(keepends=True)
    if lines:
        return lines
    return [source]


@dataclass(frozen=True)
class _ResolvedNotebookConfig:
    script_path: str | None
    parameter_path: str | None
    source_import: str | None
    entrypoint_call: str
    parameters_source: str | None
    generated_at: str | None
    read_only: bool
    script_first: bool
    kernel_name: str
    kernel_display_name: str
    language: str
    language_version: str | None
    extra_metadata: dict[str, Any]
    markdown_cells: list[str]

    @classmethod
    def from_resolved_ir(cls, resolved_ir: Any) -> _ResolvedNotebookConfig:
        notebook = _read_field(resolved_ir, "notebook", default={}) or {}
        metadata = _read_field(notebook, "metadata", default={}) or {}
        execution = _read_field(resolved_ir, "execution", default={}) or {}

        entrypoint_call = _read_field(
            execution,
            "entrypoint_call",
            "entrypoint",
            default=None,
        ) or _read_field(
            resolved_ir,
            "entrypoint_call",
            "entrypoint",
            default="main()",
        )

        markdown_cells = _read_field(notebook, "markdown_cells", default=[]) or []
        return cls(
            script_path=_read_field(
                resolved_ir,
                "script_path",
                "source_script",
                default=None,
            ),
            parameter_path=_read_field(
                resolved_ir,
                "parameter_path",
                "params_path",
                default=None,
            ),
            source_import=_read_field(
                execution,
                "source_import",
                "import_source",
                default=None,
            ) or _read_field(resolved_ir, "source_import", default=None),
            entrypoint_call=entrypoint_call,
            parameters_source=_read_field(
                resolved_ir,
                "parameters_source",
                "parameter_source",
                default=None,
            ),
            generated_at=_read_field(
                resolved_ir,
                "generated_at",
                "generated_at_utc",
                default=None,
            ),
            read_only=bool(_read_field(notebook, "read_only", default=False)),
            script_first=bool(_read_field(notebook, "script_first", default=True)),
            kernel_name=_read_field(metadata, "kernel_name", default="python3"),
            kernel_display_name=_read_field(
                metadata,
                "kernel_display_name",
                default="Python 3",
            ),
            language=_read_field(metadata, "language", default="python"),
            language_version=_read_field(metadata, "language_version", default=None),
            extra_metadata=_read_field(metadata, "extra", default={}) or {},
            markdown_cells=[str(cell) for cell in markdown_cells],
        )


class NotebookBuilder:
    def __init__(
        self,
        *,
        generated_cell_metadata_key: str = GENERATED_CELL_METADATA_KEY,
        notebook_format: int = 4,
        notebook_minor_format: int = 5,
    ) -> None:
        self.generated_cell_metadata_key = generated_cell_metadata_key
        self.notebook_format = notebook_format
        self.notebook_minor_format = notebook_minor_format

    def build(self, resolved_ir: Any) -> dict[str, Any]:
        config = _ResolvedNotebookConfig.from_resolved_ir(resolved_ir)
        metadata = self._build_metadata(config)
        cells = self._build_cells(config)
        return {
            "cells": cells,
            "metadata": metadata,
            "nbformat": self.notebook_format,
            "nbformat_minor": self.notebook_minor_format,
        }

    def build_json(self, resolved_ir: Any, *, indent: int = 2) -> str:
        return json.dumps(
            self.build(resolved_ir),
            ensure_ascii=False,
            indent=indent,
        ) + "\n"

    def _build_metadata(self, config: _ResolvedNotebookConfig) -> dict[str, Any]:
        metadata: dict[str, Any] = {
            "kernelspec": {
                "name": config.kernel_name,
                "display_name": config.kernel_display_name,
                "language": config.language,
            },
            "language_info": {
                "name": config.language,
            },
            self.generated_cell_metadata_key: {
                "generated": True,
                "version": GENERATED_NOTEBOOK_VERSION,
                "script_first": config.script_first,
                "read_only": config.read_only,
                "source_script": config.script_path,
                "parameter_file": config.parameter_path,
            },
        }
        if config.language_version:
            metadata["language_info"]["version"] = config.language_version
        if config.extra_metadata:
            metadata[self.generated_cell_metadata_key]["extra"] = config.extra_metadata
        return metadata

    def _build_cells(self, config: _ResolvedNotebookConfig) -> list[dict[str, Any]]:
        cells: list[dict[str, Any]] = []

        for index, markdown_source in enumerate(config.markdown_cells):
            cells.append(
                self._markdown_cell(
                    markdown_source,
                    cell_id=f"markdown-{index}",
                    cell_role="context",
                )
            )

        if config.script_first and config.script_path:
            cells.append(
                self._markdown_cell(
                    f"> Generated from `{config.script_path}`.\n",
                    cell_id="script-reference",
                    cell_role="script_reference",
                )
            )

        parameter_source = config.parameters_source
        if parameter_source is None and config.parameter_path:
            parameter_source = f"# Parameters loaded from {config.parameter_path}\n"
        if parameter_source is not None:
            cells.append(
                self._code_cell(
                    parameter_source,
                    cell_id="parameters",
                    cell_role="parameters",
                )
            )

        if config.source_import:
            cells.append(
                self._code_cell(
                    config.source_import,
                    cell_id="source-import",
                    cell_role="source_import",
                )
            )

        cells.append(
            self._code_cell(
                config.entrypoint_call,
                cell_id="entrypoint",
                cell_role="entrypoint",
            )
        )
        cells.append(
            self._code_cell(
                self._generated_metadata_source(config),
                cell_id="generated-metadata",
                cell_role="generated_metadata",
            )
        )
        return cells

    def _generated_metadata_source(self, config: _ResolvedNotebookConfig) -> str:
        lines = [
            "# Generated by Astronote",
            f"SCRIPT_FIRST = {config.script_first!r}",
            f"READ_ONLY = {config.read_only!r}",
            f"SOURCE_SCRIPT = {config.script_path!r}",
            f"PARAMETER_FILE = {config.parameter_path!r}",
            f"GENERATED_AT = {config.generated_at!r}",
        ]
        return "\n".join(lines) + "\n"

    def _base_metadata(self, *, cell_id: str, cell_role: str) -> dict[str, Any]:
        return {
            self.generated_cell_metadata_key: {
                "generated": True,
                "cell_id": cell_id,
                "role": cell_role,
            }
        }

    def _code_cell(self, source: str | list[str], *, cell_id: str, cell_role: str) -> dict[str, Any]:
        return {
            "cell_type": "code",
            "execution_count": None,
            "metadata": self._base_metadata(cell_id=cell_id, cell_role=cell_role),
            "outputs": [],
            "source": _normalize_lines(source),
        }

    def _markdown_cell(self, source: str | list[str], *, cell_id: str, cell_role: str) -> dict[str, Any]:
        return {
            "cell_type": "markdown",
            "metadata": self._base_metadata(cell_id=cell_id, cell_role=cell_role),
            "source": _normalize_lines(source),
        }


def build_notebook_json(resolved_ir: Any, *, indent: int = 2) -> str:
    return NotebookBuilder().build_json(resolved_ir, indent=indent)
