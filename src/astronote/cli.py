from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from astronote.analysis import analyze_python_file
from astronote.manifest import build_manifest
from astronote.notebook import NotebookBuilder
from astronote.params import ParameterFileError, parse_cli_overrides, resolve_entrypoint_parameters


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
    parser.add_argument("source", help="Python source script path to analyze.")
    parser.add_argument(
        "--parameter-file",
        type=Path,
        help="Path to a JSON parameter file matched against the selected entrypoint signature.",
    )
    parser.add_argument(
        "--override",
        action="append",
        default=[],
        metavar="KEY=JSON",
        help="Override a parameter value from the parameter file. Later overrides win.",
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
    parser.add_argument(
        "--show-schema",
        action="store_true",
        help="Print the simplified parameter schema for the selected entrypoint before notebook generation.",
    )
    return parser



def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    return build_parser().parse_args(argv)



def analyze_source(source: str) -> dict[str, Any]:
    path = Path(source)
    if not path.exists() or path.suffix != ".py":
        raise AnalysisError(
            f"Failed to analyze target '{source}': expected an existing .py source file. "
            "Next step: pass a Python script path as the positional argument."
        )
    static_ir = analyze_python_file(path)
    return {
        "kind": "script",
        "display_name": str(path.resolve()),
        "module_name": path.stem,
        "file_path": path.resolve(),
        "entrypoints": static_ir.entrypoints,
        "static_ir": static_ir,
        "analysis": {
            "file_path": str(path.resolve()),
            "module_name": path.stem,
            "entrypoints": static_ir.entrypoints,
            "unsupported": [u.message for u in static_ir.unsupported],
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
            "Detected entrypoints: none. Next step: add a public top-level function decorated with @notebook_entry."
        )

    raise EntrypointSelectionError(
        f"Failed to select an entrypoint for '{target}': multiple candidates were detected. "
        f"Detected entrypoints: {detected}. Next step: pass --entrypoint NAME."
    )



def default_output_path(file_path: Path) -> Path:
    return file_path.with_suffix(".ipynb")



def build_notebook_payload(analysis: dict[str, Any], entrypoint: str, parameter_file: Path | None, overrides: list[str]) -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        parsed_overrides = parse_cli_overrides(overrides)
        parameter_resolution = resolve_entrypoint_parameters(
            analysis["static_ir"],
            entrypoint=entrypoint,
            parameter_file=parameter_file,
            cli_overrides=parsed_overrides,
        )
    except ParameterFileError as exc:
        raise ParameterResolutionError(str(exc)) from exc

    manifest = build_manifest(str(analysis["file_path"]), parameter_resolution)
    parameters = manifest.parameters
    assignment_lines = [f"{name} = {parameters[name]!r}" for name in parameters]
    parameters_source = "\n".join(assignment_lines) + ("\n" if assignment_lines else "")

    resolved_notebook_ir = {
        "script_path": str(analysis["file_path"]),
        "parameter_path": str(parameter_file) if parameter_file else None,
        "parameters_source": parameters_source,
        "generated_at": manifest.generated_at,
        "execution": {
            "source_import": f"from {analysis['module_name']} import {entrypoint}\n",
            "entrypoint_call": f"{entrypoint}(**{parameters!r})\n",
        },
        "notebook": {
            "script_first": True,
            "read_only": False,
            "metadata": {
                "kernel_name": "python3",
                "kernel_display_name": "Python 3",
                "language": "python",
                "extra": {
                    "manifest": manifest.as_dict(),
                },
            },
        },
        "manifest": manifest.as_dict(),
    }
    notebook = NotebookBuilder().build(resolved_notebook_ir)
    return notebook, manifest.as_dict()



def generate_notebook(analysis: dict[str, Any], entrypoint: str, parameter_file: Path | None, overrides: list[str], output_path: Path | None) -> Path:
    destination = output_path or default_output_path(analysis["file_path"])
    destination.parent.mkdir(parents=True, exist_ok=True)
    notebook, _ = build_notebook_payload(analysis, entrypoint, parameter_file, overrides)
    destination.write_text(json.dumps(notebook, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return destination



def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        analysis = analyze_source(args.source)
        if args.show_analysis:
            print(render_analysis(analysis))
        entrypoint = choose_entrypoint(analysis, args.entrypoint)
        if args.show_schema:
            resolution = resolve_entrypoint_parameters(
                analysis["static_ir"],
                entrypoint=entrypoint,
                parameter_file=args.parameter_file,
                cli_overrides=parse_cli_overrides(args.override),
            )
            print(json.dumps(resolution.schema.as_dict(), indent=2, ensure_ascii=False))
        output_path = generate_notebook(analysis, entrypoint, args.parameter_file, args.override, args.output)
    except CliError as exc:
        raise SystemExit(str(exc)) from exc
    except ParameterFileError as exc:
        raise SystemExit(str(exc)) from exc

    print(f"Notebook written to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
