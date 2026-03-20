from __future__ import annotations

import argparse
import ast
import importlib.util
import json
import tokenize
from pathlib import Path
from typing import Any


class CliError(Exception):
    """Raised when CLI input or orchestration fails."""


class AnalysisError(CliError):
    """Raised when source analysis cannot continue."""


class EntrypointSelectionError(CliError):
    """Raised when entrypoint selection is ambiguous or invalid."""


class ParameterResolutionError(CliError):
    """Raised when parameter inputs cannot be resolved."""



def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="astronote",
        description="Analyze a Python source target and emit a notebook scaffold.",
    )
    parser.add_argument(
        "source",
        help="Python source script path or importable module path to analyze.",
    )
    parser.add_argument(
        "--parameters",
        metavar="JSON",
        help="JSON object containing base parameters for notebook execution.",
    )
    parser.add_argument(
        "--override",
        action="append",
        default=[],
        metavar="KEY=JSON",
        help="Override a parameter value with a JSON literal. Repeatable.",
    )
    parser.add_argument(
        "--entrypoint",
        help="Explicit entrypoint name to use when multiple candidates are detected.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Destination notebook path. Defaults beside the source target.",
    )
    parser.add_argument(
        "--show-analysis",
        action="store_true",
        help="Print static analysis details before notebook generation.",
    )
    return parser



def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    return build_parser().parse_args(argv)



def resolve_source_target(source: str) -> dict[str, Any]:
    source_path = Path(source)
    if source_path.exists():
        path = source_path.resolve()
        if path.suffix != ".py":
            raise AnalysisError(
                f"Failed to analyze target '{path}': expected a Python file. "
                "Next step: pass a .py script path or an importable module path as the positional argument."
            )
        return {
            "kind": "script",
            "display_name": str(path),
            "module_name": path.stem,
            "file_path": path,
        }

    spec = importlib.util.find_spec(source)
    if spec is None or spec.origin in {None, "built-in", "frozen"}:
        raise AnalysisError(
            f"Failed to analyze target '{source}': no script file or importable module was found. "
            "Detected entrypoints: none. Next step: pass a valid script path or module path."
        )

    origin = Path(spec.origin).resolve()
    return {
        "kind": "module",
        "display_name": source,
        "module_name": source,
        "file_path": origin,
    }



def _is_candidate_entrypoint(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    return not node.name.startswith("_")



def analyze_source(source: str) -> dict[str, Any]:
    target = resolve_source_target(source)
    file_path: Path = target["file_path"]
    if file_path.suffix != ".py":
        raise AnalysisError(
            f"Failed to analyze target '{file_path}': only .py source files are supported. "
            "Detected entrypoints: none. Next step: pass a .py script path or an importable module path."
        )
    try:
        with tokenize.open(str(file_path)) as fh:
            code = fh.read()
    except (OSError, SyntaxError) as exc:
        raise AnalysisError(
            f"Failed to analyze target '{file_path}': {exc}. "
            "Detected entrypoints: none. Next step: verify the file is readable and rerun the command."
        ) from exc
    except UnicodeDecodeError as exc:
        raise AnalysisError(
            f"Failed to analyze target '{file_path}': unable to decode source ({exc}). "
            "Detected entrypoints: none. Next step: ensure the file is saved with a supported encoding."
        ) from exc

    try:
        tree = ast.parse(code, filename=str(target["file_path"]))
    except SyntaxError as exc:
        raise AnalysisError(
            f"Failed to analyze target '{target['file_path']}': syntax error at line {exc.lineno}. "
            "Detected entrypoints: none. Next step: fix the Python syntax and rerun the command."
        ) from exc

    entrypoints = [
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and _is_candidate_entrypoint(node)
    ]

    return {
        **target,
        "entrypoints": entrypoints,
        "analysis": {
            "file_path": str(target["file_path"]),
            "module_name": target["module_name"],
            "entrypoints": entrypoints,
        },
    }



def render_analysis(analysis: dict[str, Any]) -> str:
    return json.dumps(analysis["analysis"], indent=2, ensure_ascii=False)



def choose_entrypoint(analysis: dict[str, Any], requested: str | None) -> str:
    entrypoints = analysis["entrypoints"]
    detected = ", ".join(entrypoints) if entrypoints else "none"
    target = analysis["file_path"]

    if requested:
        if requested not in entrypoints:
            raise EntrypointSelectionError(
                f"Failed to select an entrypoint for '{target}': '{requested}' was not detected. "
                f"Detected entrypoints: {detected}. Next step: pass --entrypoint with one of the detected names."
            )
        return requested

    if len(entrypoints) == 1:
        return entrypoints[0]

    if not entrypoints:
        raise EntrypointSelectionError(
            f"Failed to select an entrypoint for '{target}': no callable entrypoints were detected. "
            "Detected entrypoints: none. Next step: add a public top-level function or pass a different source target."
        )

    raise EntrypointSelectionError(
        f"Failed to select an entrypoint for '{target}': multiple candidates were detected. "
        f"Detected entrypoints: {detected}. Next step: pass --entrypoint NAME."
    )



def build_ir(analysis: dict[str, Any], entrypoint: str) -> dict[str, Any]:
    return {
        "source_kind": analysis["kind"],
        "source": analysis["display_name"],
        "file_path": str(analysis["file_path"]),
        "module_name": analysis["module_name"],
        "entrypoint": entrypoint,
    }



def _parameter_context(analysis: dict[str, Any] | None) -> tuple[str, str]:
    if not analysis:
        return "<unresolved>", "unknown"
    detected = ", ".join(analysis["entrypoints"]) if analysis["entrypoints"] else "none"
    return str(analysis["file_path"]), detected


def parse_base_parameters(raw: str | None, analysis: dict[str, Any] | None = None) -> dict[str, Any]:
    target, detected = _parameter_context(analysis)
    if raw is None:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ParameterResolutionError(
            f"Failed to resolve parameters for '{target}': invalid JSON passed to --parameters. "
            f"Detected entrypoints: {detected}. Next step: pass --parameters with a JSON object string."
        ) from exc
    if not isinstance(parsed, dict):
        raise ParameterResolutionError(
            f"Failed to resolve parameters for '{target}': --parameters must decode to a JSON object. "
            f"Detected entrypoints: {detected}. Next step: pass --parameters with a JSON object string."
        )
    return parsed



def _apply_override(target: dict[str, Any], key: str, value: Any, analysis: dict[str, Any] | None = None) -> None:
    current = target
    parts = key.split('.')
    for part in parts[:-1]:
        nested = current.get(part)
        if nested is None:
            nested = {}
            current[part] = nested
        if not isinstance(nested, dict):
            raise ParameterResolutionError(
                f"Failed to resolve parameters for '{_parameter_context(analysis)[0]}': override path '{key}' collides with a non-object value. "
                f"Detected entrypoints: {_parameter_context(analysis)[1]}. Next step: change --override to target an object path."
            )
        current = nested
    current[parts[-1]] = value



def resolve_parameters(raw_parameters: str | None, overrides: list[str], analysis: dict[str, Any] | None = None) -> dict[str, Any]:
    target, detected = _parameter_context(analysis)
    resolved = parse_base_parameters(raw_parameters, analysis)
    for override in overrides:
        if '=' not in override:
            raise ParameterResolutionError(
                f"Failed to resolve parameters for '{target}': override '{override}' is missing '='. "
                f"Detected entrypoints: {detected}. Next step: pass --override KEY=JSON."
            )
        key, raw_value = override.split('=', 1)
        if not key or any(segment == "" for segment in key.split('.')):
            raise ParameterResolutionError(
                f"Failed to resolve parameters for '{target}': override key '{key}' is invalid "
                "(key must be non-empty and each dot-separated segment must be non-empty). "
                f"Detected entrypoints: {detected}. Next step: pass --override KEY=JSON with a valid dot-path key."
            )
        try:
            value = json.loads(raw_value)
        except json.JSONDecodeError as exc:
            raise ParameterResolutionError(
                f"Failed to resolve parameters for '{target}': override '{override}' is not valid JSON. "
                f"Detected entrypoints: {detected}. Next step: encode the value as JSON in --override KEY=JSON."
            ) from exc
        _apply_override(resolved, key, value, analysis)
    return resolved



def default_output_path(ir: dict[str, Any]) -> Path:
    file_path = Path(ir["file_path"])
    return file_path.with_suffix(".ipynb")



def generate_notebook(ir: dict[str, Any], parameters: dict[str, Any], output_path: Path | None) -> Path:
    destination = output_path or default_output_path(ir)
    destination.parent.mkdir(parents=True, exist_ok=True)
    source_ref = ir["source"]
    notebook = {
        "cells": [
            {
                "cell_type": "markdown",
                "metadata": {},
                "source": [
                    "# astronote export\n",
                    f"- Source: `{source_ref}`\n",
                    f"- Entrypoint: `{ir['entrypoint']}`\n",
                ],
            },
            {
                "cell_type": "code",
                "execution_count": None,
                "metadata": {
                    "astronote": {
                        "ir": ir,
                        "parameters": parameters,
                    },
                },
                "outputs": [],
                "source": [
                    "import json\n",
                    f"PARAMETERS = {repr(parameters)}\n",
                    f"SOURCE = {source_ref!r}\n",
                    f"ENTRYPOINT = {ir['entrypoint']!r}\n",
                ],
            },
        ],
        "metadata": {
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3",
            },
            "language_info": {
                "name": "python",
                "version": "3.12",
            },
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    destination.write_text(json.dumps(notebook, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return destination



def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        analysis = analyze_source(args.source)
        if args.show_analysis:
            print(render_analysis(analysis))
        entrypoint = choose_entrypoint(analysis, args.entrypoint)
        ir = build_ir(analysis, entrypoint)
        parameters = resolve_parameters(args.parameters, args.override, analysis)
        output_path = generate_notebook(ir, parameters, args.output)
    except CliError as exc:
        raise SystemExit(str(exc)) from exc

    print(f"Notebook written to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
