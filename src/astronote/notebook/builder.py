from __future__ import annotations

import json
import os
import re
from typing import Any

from astronote._model import FrozenModel

GENERATED_CELL_METADATA_KEY = "astronote"
GENERATED_NOTEBOOK_VERSION = 1


def _read_field(value: Any, *names: str, default: Any = None) -> Any:
    for name in names:
        if isinstance(value, dict) and name in value:
            candidate = value[name]
        elif hasattr(value, name):
            candidate = getattr(value, name)
        else:
            continue
        if candidate is not None:
            return candidate
    return default


def _module_from_path(script_path: str | None) -> str | None:
    """Convert a script path like 'myproj/train.py' to module name 'myproj.train'."""
    if not script_path:
        return None
    root, _ = os.path.splitext(script_path)
    module = root.replace(os.sep, ".").replace("/", ".").replace("\\", ".")
    return module or None


def _sanitize_cell_id(cell_id: str) -> str:
    """Produce an nbformat-compatible cell id (max 64 chars, [a-zA-Z0-9_-] only)."""
    sanitized = re.sub(r"[^a-zA-Z0-9_-]", "-", cell_id)
    sanitized = re.sub(r"-{2,}", "-", sanitized).strip("-")
    return sanitized[:64] or "cell"


def _normalize_lines(source: str | list[str]) -> list[str]:
    if isinstance(source, list):
        return source
    if not source:
        return []
    lines = source.splitlines(keepends=True)
    if lines:
        return lines
    return [source]


def _normalize_optional_source(source: Any) -> str | None:
    if source is None:
        return None
    if isinstance(source, list):
        text = "".join(str(line) for line in source)
    else:
        text = str(source)
    return text if text.strip() else None


def _normalize_source_definitions(sources: Any, source: Any = None) -> list[str]:
    if sources is not None:
        candidates = list(sources) if isinstance(sources, (list, tuple)) else [sources]
        normalized_sources = [
            normalized
            for candidate in candidates
            if (normalized := _normalize_optional_source(candidate)) is not None
        ]
        return normalized_sources

    normalized_source = _normalize_optional_source(source)
    return [normalized_source] if normalized_source is not None else []


class _ResolvedNotebookConfig(FrozenModel):
    script_path: str | None
    parameter_path: str | None
    runtime_setup_source: str | None
    source_definitions: list[str]
    source_import: str | None
    entrypoint_call: str
    parameters_source: str | None
    generated_at: str | None
    manifest: dict[str, Any]
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
            runtime_setup_source=_normalize_optional_source(
                _read_field(
                    execution,
                    "runtime_setup_source",
                    default=None,
                )
                or _read_field(resolved_ir, "runtime_setup_source", default=None)
            ),
            source_definitions=_normalize_source_definitions(
                _read_field(
                    execution,
                    "source_definitions",
                    default=None,
                )
                or _read_field(resolved_ir, "source_definitions", default=None),
                _read_field(
                    execution,
                    "source_definition",
                    default=None,
                )
                or _read_field(resolved_ir, "source_definition", default=None),
            ),
            source_import=_normalize_optional_source(
                _read_field(
                    execution,
                    "source_import",
                    "import_source",
                    default=None,
                )
                or _read_field(resolved_ir, "source_import", default=None)
            ),
            entrypoint_call=entrypoint_call,
            parameters_source=_normalize_optional_source(
                _read_field(
                    resolved_ir,
                    "parameters_source",
                    "parameter_source",
                    default=None,
                )
            ),
            generated_at=_read_field(
                resolved_ir,
                "generated_at",
                "generated_at_utc",
                default=None,
            ),
            manifest=_read_field(resolved_ir, "manifest", default={}) or {},
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
        return (
            json.dumps(
                self.build(resolved_ir),
                ensure_ascii=False,
                indent=indent,
            )
            + "\n"
        )

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
                "manifest": config.manifest,
            },
        }
        if config.language_version:
            metadata["language_info"]["version"] = config.language_version
        if config.extra_metadata:
            metadata[self.generated_cell_metadata_key]["extra"] = config.extra_metadata
        return metadata

    def _build_cells(self, config: _ResolvedNotebookConfig) -> list[dict[str, Any]]:
        cells: list[dict[str, Any]] = []
        source_module = _module_from_path(config.script_path)

        cells.append(
            self._markdown_cell(
                self._generated_header_source(config),
                cell_id="generated-header",
                cell_role="generated_header",
                source_module=source_module,
            )
        )

        for index, markdown_source in enumerate(config.markdown_cells):
            cells.append(
                self._markdown_cell(
                    markdown_source,
                    cell_id=f"markdown-{index}",
                    cell_role="context",
                    source_module=source_module,
                )
            )

        if config.runtime_setup_source:
            cells.append(
                self._code_cell(
                    config.runtime_setup_source,
                    cell_id="runtime-setup",
                    cell_role="runtime_setup",
                    source_module=source_module,
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
                    source_module=source_module,
                    tags=["parameters"],
                )
            )

        if config.source_definitions:
            multiple_source_definitions = len(config.source_definitions) > 1
            for index, source_definition in enumerate(config.source_definitions):
                cell_id = (
                    f"source-definition-{index}"
                    if multiple_source_definitions
                    else "source-definition"
                )
                cells.append(
                    self._code_cell(
                        source_definition,
                        cell_id=cell_id,
                        cell_role="source_definition",
                        source_module=source_module,
                    )
                )
        elif config.source_import:
            cells.append(
                self._code_cell(
                    config.source_import,
                    cell_id="source-import",
                    cell_role="source_import",
                    source_module=source_module,
                )
            )

        cells.append(
            self._code_cell(
                config.entrypoint_call,
                cell_id="entrypoint",
                cell_role="entrypoint",
                source_module=source_module,
            )
        )
        return cells

    def _generated_header_source(self, config: _ResolvedNotebookConfig) -> str:
        lines = ["# Generated by Astronote", ""]
        if config.script_path:
            lines.append(f"- Source: `{config.script_path}`")
        entrypoint = config.manifest.get("entrypoint")
        if entrypoint:
            lines.append(f"- Entrypoint: `{entrypoint}`")
        if config.generated_at:
            lines.append(f"- Generated at: `{config.generated_at}`")
        if config.parameter_path:
            lines.append(f"- Parameter file: `{config.parameter_path}`")
        return "\n".join(lines) + "\n"

    def _full_cell_id(
        self, cell_id: str, cell_role: str, source_module: str | None
    ) -> str:
        """Build the structured cell id encoding module identity and semantic kind.

        For indexed cells (e.g. markdown-0) the slot is appended to guarantee
        uniqueness when multiple cells share the same role.
        """
        role_slug = cell_role.replace("_", "-")
        base = (
            f"mod:{source_module}|kind:{cell_role}"
            if source_module
            else f"kind:{cell_role}"
        )
        if cell_id != role_slug and cell_id != cell_role:
            base = f"{base}|slot:{cell_id}"
        return base

    def _base_metadata(
        self, *, cell_id: str, cell_role: str, source_module: str | None = None
    ) -> dict[str, Any]:
        full_id = self._full_cell_id(cell_id, cell_role, source_module)
        astronote_meta: dict[str, Any] = {
            "generated": True,
            "cell_id": full_id,
            "role": cell_role,
        }
        if source_module:
            astronote_meta["source_module"] = source_module
        return {self.generated_cell_metadata_key: astronote_meta}

    def _code_cell(
        self,
        source: str | list[str],
        *,
        cell_id: str,
        cell_role: str,
        source_module: str | None = None,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        metadata = self._base_metadata(
            cell_id=cell_id, cell_role=cell_role, source_module=source_module
        )
        if tags:
            metadata["tags"] = tags
        nbformat_id = _sanitize_cell_id(
            self._full_cell_id(cell_id, cell_role, source_module)
        )
        return {
            "cell_type": "code",
            "id": nbformat_id,
            "execution_count": None,
            "metadata": metadata,
            "outputs": [],
            "source": _normalize_lines(source),
        }

    def _markdown_cell(
        self,
        source: str | list[str],
        *,
        cell_id: str,
        cell_role: str,
        source_module: str | None = None,
    ) -> dict[str, Any]:
        nbformat_id = _sanitize_cell_id(
            self._full_cell_id(cell_id, cell_role, source_module)
        )
        return {
            "cell_type": "markdown",
            "id": nbformat_id,
            "metadata": self._base_metadata(
                cell_id=cell_id, cell_role=cell_role, source_module=source_module
            ),
            "source": _normalize_lines(source),
        }


def build_notebook_json(resolved_ir: Any, *, indent: int = 2) -> str:
    return NotebookBuilder().build_json(resolved_ir, indent=indent)
