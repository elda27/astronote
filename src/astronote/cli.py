import argparse
import ast
import difflib
import json
from pathlib import Path
from typing import Any

from astronote.analysis import analyze_python_file
from astronote.analysis.resolver import (
    build_import_alias_map,
    resolve_notebook_entry_decorator,
)
from astronote.config import PyprojectConfigError, load_pyproject_cli_options
from astronote.manifest import build_manifest
from astronote.notebook import NotebookBuilder
from astronote.params import (
    ParameterFileError,
    parse_cli_overrides,
    resolve_entrypoint_parameters,
)


class CliError(Exception):
    """Raised when CLI input or orchestration fails."""


class AnalysisError(CliError):
    """Raised when source analysis cannot continue."""


class EntrypointSelectionError(CliError):
    """Raised when entrypoint selection is ambiguous or invalid."""


class ParameterResolutionError(CliError):
    """Raised when parameter inputs cannot be resolved."""


class ModuleExpansionError(CliError):
    """Raised when requested module expansion cannot be resolved."""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="astronote",
        description="Analyze a Python source target and emit a notebook scaffold.",
    )
    parser.add_argument(
        "source",
        nargs="?",
        help="Python source script path to analyze.",
    )
    parser.add_argument(
        "--parameter-file",
        type=Path,
        help="Path to a JSON parameter file matched against the selected entrypoint signature.",
    )
    parser.add_argument(
        "--override",
        action="append",
        default=None,
        metavar="KEY=JSON",
        help="Override a parameter value from the parameter file. Later overrides win.",
    )
    parser.add_argument(
        "--entrypoint",
        help="Explicit entrypoint name to use when multiple candidates are detected.",
    )
    parser.add_argument(
        "--expand-module",
        nargs="+",
        default=None,
        metavar="MODULE",
        help="Expand a local module directly into the generated notebook source. Use the exact import string from the source. Local dependencies of expanded modules are embedded automatically.",
    )
    parser.add_argument(
        "--embed-file",
        nargs="+",
        default=None,
        metavar="FILE",
        help="Embed an imported local .py file directly into the generated notebook source.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Destination notebook path. Defaults beside the source target.",
    )
    parser.add_argument(
        "--show-analysis",
        action="store_true",
        default=None,
        help="Print static analysis details before notebook generation.",
    )
    parser.add_argument(
        "--show-schema",
        action="store_true",
        default=None,
        help="Print the simplified parameter schema for the selected entrypoint before notebook generation.",
    )
    return parser


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    return build_parser().parse_args(argv)


def resolve_cli_args(argv: list[str] | None = None) -> argparse.Namespace:
    args = parse_args(argv)
    pyproject_options = load_pyproject_cli_options(args.source)

    source = args.source
    if source is None and pyproject_options.source is not None:
        source = str(pyproject_options.source)

    if source is None:
        raise CliError(
            "Failed to determine a source target: pass SOURCE on the CLI or set [tool.astronote].source in pyproject.toml."
        )

    return argparse.Namespace(
        source=source,
        parameter_file=args.parameter_file or pyproject_options.parameter_file,
        override=[*pyproject_options.override, *(args.override or [])],
        entrypoint=args.entrypoint or pyproject_options.entrypoint,
        expand_module=[*pyproject_options.expand_module, *(args.expand_module or [])],
        embed_file=[*pyproject_options.embed_file, *(args.embed_file or [])],
        output=args.output or pyproject_options.output,
        show_analysis=(
            args.show_analysis
            if args.show_analysis is not None
            else pyproject_options.show_analysis or False
        ),
        show_schema=(
            args.show_schema
            if args.show_schema is not None
            else pyproject_options.show_schema or False
        ),
    )


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


def _validate_module_name(module_name: str) -> None:
    if "=" in module_name:
        raise ModuleExpansionError(
            f"Failed to expand module '{module_name}': module paths are unsupported. "
            "Next step: pass the exact imported module string, such as 'sub_mod' or '.sub_mod'."
        )

    stripped_name = module_name.lstrip(".")
    parts = stripped_name.split(".") if stripped_name else []
    if not stripped_name or any(not part or not part.isidentifier() for part in parts):
        raise ModuleExpansionError(
            f"Failed to expand module '{module_name}': expected a dotted Python module name. "
            "Next step: pass the exact import string from the source, such as 'sub_mod', 'pkg.sub_mod', or '.sub_mod'."
        )


def _split_relative_module_name(module_name: str) -> tuple[int, str]:
    stripped_name = module_name.lstrip(".")
    return len(module_name) - len(stripped_name), stripped_name


def _ordered_import_targets(source_file: Path) -> list[str]:
    source = source_file.read_text(encoding="utf-8")
    module = ast.parse(source, filename=str(source_file))
    targets: list[str] = []
    seen_targets: set[str] = set()

    for node in module.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "astronote":
                    continue
                if alias.name in seen_targets:
                    continue
                seen_targets.add(alias.name)
                targets.append(alias.name)
            continue

        if not isinstance(node, ast.ImportFrom):
            continue

        for alias in node.names:
            if alias.name == "*":
                continue
            if node.level == 0 and node.module == "astronote":
                continue
            target = _import_from_target(source_file, node, alias)
            if target in seen_targets:
                continue
            seen_targets.add(target)
            targets.append(target)

    return targets


def _import_target_names(source_file: Path) -> set[str]:
    return set(_ordered_import_targets(source_file))


def _resolve_embed_file_request(source_file: Path, file_path: str) -> Path:
    requested_path = Path(file_path)
    if requested_path.suffix != ".py":
        raise ModuleExpansionError(
            f"Failed to embed file '{file_path}': expected a .py file path. "
            "Next step: pass a local Python source file path to --embed-file."
        )

    if requested_path.is_absolute():
        resolved_path = requested_path.resolve()
        if resolved_path.is_file():
            return resolved_path
        raise ModuleExpansionError(
            f"Failed to embed file '{file_path}': expected an existing local .py file. "
            "Next step: pass a valid file path to --embed-file."
        )

    candidate_roots = [Path.cwd(), source_file.parent]
    seen_paths: set[Path] = set()
    for root in candidate_roots:
        candidate = (root / requested_path).resolve()
        if candidate in seen_paths:
            continue
        seen_paths.add(candidate)
        if candidate.is_file():
            return candidate

    raise ModuleExpansionError(
        f"Failed to embed file '{file_path}': expected an existing local .py file. "
        "Next step: pass a valid file path to --embed-file."
    )


def _matching_import_targets_for_path(
    source_file: Path,
    requested_path: Path,
) -> list[str]:
    matches: list[str] = []
    for import_target in _ordered_import_targets(source_file):
        resolved_local_module = _resolve_local_module_path(source_file, import_target)
        if resolved_local_module is None:
            continue
        module_path, _ = resolved_local_module
        if module_path == requested_path:
            matches.append(import_target)
    return matches


def _normalize_embed_file_request(source_file: Path, file_path: str) -> str:
    requested_path = _resolve_embed_file_request(source_file, file_path)
    matches = _matching_import_targets_for_path(source_file, requested_path)
    if matches:
        return matches[0]

    detected_targets = ", ".join(sorted(_import_target_names(source_file))) or "none"
    raise ModuleExpansionError(
        f"Failed to embed file '{file_path}': '{requested_path}' did not match any imported local module in '{source_file}'. "
        f"Detected import targets: {detected_targets}. Next step: pass a .py path for an imported local module."
    )


def _combine_expand_requests(
    source_file: Path,
    expand_modules: list[str],
    embed_files: list[str],
) -> list[str]:
    normalized_embed_files = [
        _normalize_embed_file_request(source_file, file_path)
        for file_path in embed_files
    ]
    return [*expand_modules, *normalized_embed_files]


def _resolve_local_module_path(
    source_file: Path,
    module_name: str,
) -> tuple[Path, bool] | None:
    for candidate_path, is_package in _module_candidate_paths(source_file, module_name):
        if candidate_path.is_file():
            return candidate_path.resolve(), is_package

    return None


def _module_candidate_paths(
    source_file: Path, module_name: str
) -> list[tuple[Path, bool]]:
    leading_dots, stripped_name = _split_relative_module_name(module_name)
    if leading_dots:
        search_root = source_file.parent
        for _ in range(leading_dots - 1):
            search_root = search_root.parent
        relative_module_path = Path(*stripped_name.split("."))
        return [
            (search_root / relative_module_path.with_suffix(".py"), False),
            (search_root / relative_module_path / "__init__.py", True),
        ]

    relative_module_path = Path(*stripped_name.split("."))
    search_roots: list[Path] = []
    seen_roots: set[Path] = set()

    for base_dir in [source_file.parent, *source_file.parent.parents]:
        for candidate_root in (base_dir, base_dir / "src"):
            resolved_root = candidate_root.resolve()
            if resolved_root in seen_roots:
                continue
            seen_roots.add(resolved_root)
            search_roots.append(resolved_root)

    candidates: list[tuple[Path, bool]] = []
    for root in search_roots:
        candidates.append((root / relative_module_path.with_suffix(".py"), False))
        candidates.append((root / relative_module_path / "__init__.py", True))
    return candidates


def _module_target_exists(source_file: Path, module_name: str) -> bool:
    return _resolve_local_module_path(source_file, module_name) is not None


def _expand_module_mismatch_message(
    source_file: Path,
    module_name: str,
    import_targets: set[str],
) -> str:
    detected_targets = ", ".join(sorted(import_targets)) if import_targets else "none"
    matches = difflib.get_close_matches(
        module_name, sorted(import_targets), n=1, cutoff=0.6
    )
    if matches:
        suggestion = matches[0]
        return (
            f"Failed to expand module '{module_name}': it did not exactly match any imported module string in '{source_file}'. "
            f"Detected import targets: {detected_targets}. Closest match: {suggestion}. "
            f"Next step: pass --expand-module {suggestion}."
        )

    return (
        f"Failed to expand module '{module_name}': it did not exactly match any imported module string in '{source_file}'. "
        f"Detected import targets: {detected_targets}. Next step: pass the exact imported module string to --expand-module."
    )


def _resolve_expand_module(
    source_file: Path, module_name: str
) -> tuple[str, Path, bool]:
    _validate_module_name(module_name)
    import_targets = _import_target_names(source_file)
    if module_name not in import_targets:
        raise ModuleExpansionError(
            _expand_module_mismatch_message(source_file, module_name, import_targets)
        )

    if module_name.startswith("."):
        raise ModuleExpansionError(
            f"Failed to expand module '{module_name}': relative import targets are not supported for notebook expansion. "
            "Next step: rewrite the source import to an absolute module string, then pass that exact string to --expand-module."
        )

    resolved_local_module = _resolve_local_module_path(source_file, module_name)
    if resolved_local_module is not None:
        module_path, is_package = resolved_local_module
        return module_name, module_path, is_package

    raise ModuleExpansionError(
        f"Failed to expand module '{module_name}': no local source file was found near '{source_file}'. "
        "Next step: keep --expand-module values as exact import strings and place the local module where that import resolves from the source file."
    )


def _resolve_expand_modules(
    source_file: Path,
    expand_modules: list[str],
) -> list[tuple[str, Path, bool]]:
    resolved_modules: list[tuple[str, Path, bool]] = []
    seen_requested_names: set[str] = set()
    emitted_paths: set[Path] = set()
    visiting_paths: set[Path] = set()
    source_file_resolved = source_file.resolve()

    def visit_module(module_name: str, module_path: Path, is_package: bool) -> None:
        if module_path == source_file_resolved or module_path in emitted_paths:
            return
        if module_path in visiting_paths:
            return

        visiting_paths.add(module_path)
        for dependency_name in _ordered_import_targets(module_path):
            resolved_dependency = _resolve_local_module_path(
                module_path, dependency_name
            )
            if resolved_dependency is None:
                continue
            dependency_path, dependency_is_package = resolved_dependency
            if dependency_path == source_file_resolved:
                continue
            visit_module(dependency_name, dependency_path, dependency_is_package)
        visiting_paths.remove(module_path)

        if module_path in emitted_paths:
            return
        emitted_paths.add(module_path)
        resolved_modules.append((module_name, module_path, is_package))

    for module_name in expand_modules:
        if module_name in seen_requested_names:
            continue
        seen_requested_names.add(module_name)

        resolved_module = _resolve_expand_module(source_file, module_name)
        visit_module(*resolved_module)

    return resolved_modules


def _line_range(node: ast.AST) -> tuple[int, int]:
    start_line = getattr(node, "lineno", None)
    end_line = getattr(node, "end_lineno", start_line)
    if not isinstance(start_line, int) or not isinstance(end_line, int):
        raise ValueError("AST node is missing line information.")
    return start_line, end_line


def _node_position(node: ast.AST) -> tuple[int, int, int, int]:
    start_line, end_line = _line_range(node)
    start_column = getattr(node, "col_offset", 0)
    end_column = getattr(node, "end_col_offset", start_column)
    if not isinstance(start_column, int) or not isinstance(end_column, int):
        raise ValueError("AST node is missing column information.")
    return (
        start_line,
        start_column,
        end_line,
        end_column,
    )


def _split_source_lines(source: str) -> list[str]:
    return source.splitlines(keepends=True)


def _import_from_target(
    source_file: Path,
    node: ast.ImportFrom,
    alias: ast.alias,
) -> str:
    prefix = "." * node.level
    if not node.module:
        return f"{prefix}{alias.name}"

    module_target = f"{prefix}{node.module}"
    nested_module_target = f"{module_target}.{alias.name}"
    if _module_target_exists(source_file, nested_module_target):
        return nested_module_target
    return module_target


def _import_target_path(
    source_file: Path,
    node: ast.Import | ast.ImportFrom,
    alias: ast.alias,
) -> Path | None:
    module_name = (
        alias.name
        if isinstance(node, ast.Import)
        else _import_from_target(source_file, node, alias)
    )
    resolved_local_module = _resolve_local_module_path(source_file, module_name)
    if resolved_local_module is None:
        return None
    return resolved_local_module[0]


def _import_binding_prefix(
    node: ast.Import | ast.ImportFrom,
    alias: ast.alias,
) -> tuple[str, ...]:
    if isinstance(node, ast.Import):
        if alias.asname is not None:
            return (alias.asname,)
        return tuple(alias.name.split("."))

    return (alias.asname or alias.name,)


def _attribute_chain_parts(node: ast.AST) -> list[str] | None:
    if isinstance(node, ast.Name):
        return [node.id]
    if isinstance(node, ast.Attribute):
        parent_parts = _attribute_chain_parts(node.value)
        if parent_parts is None:
            return None
        return [*parent_parts, node.attr]
    return None


def _build_attribute_chain(parts: list[str], template: ast.AST) -> ast.expr:
    expression: ast.expr = ast.Name(id=parts[0], ctx=ast.Load())
    for attr in parts[1:]:
        expression = ast.Attribute(value=expression, attr=attr, ctx=ast.Load())
    return ast.copy_location(expression, template)


def _expanded_import_rewrite(
    source_file: Path,
    node: ast.Import | ast.ImportFrom,
    alias: ast.alias,
) -> tuple[tuple[str, ...], tuple[str, ...]] | None:
    binding_prefix = _import_binding_prefix(node, alias)
    if isinstance(node, ast.Import):
        return binding_prefix, ()

    if node.module:
        module_target = f"{'.' * node.level}{node.module}"
        if _import_from_target(source_file, node, alias) == module_target:
            if alias.asname is None:
                return None
            return binding_prefix, (alias.name,)

    return binding_prefix, ()


def _rewrite_parts(
    parts: list[str],
    rewrite_rules: list[tuple[tuple[str, ...], tuple[str, ...]]],
) -> list[str] | None:
    for prefix, replacement in rewrite_rules:
        if tuple(parts[: len(prefix)]) != prefix:
            continue
        if len(parts) == len(prefix) and not replacement:
            continue
        return [*replacement, *parts[len(prefix) :]]
    return None


class _ExpandedImportUsageRewriter(ast.NodeTransformer):
    def __init__(
        self,
        rewrite_rules: list[tuple[tuple[str, ...], tuple[str, ...]]],
    ) -> None:
        self._rewrite_rules = sorted(
            rewrite_rules,
            key=lambda rule: len(rule[0]),
            reverse=True,
        )

    def _visit_chain_node(self, node: ast.AST) -> ast.AST:
        rewritten = self.generic_visit(node)
        parts = _attribute_chain_parts(rewritten)
        if parts is None:
            return rewritten

        rewritten_parts = _rewrite_parts(parts, self._rewrite_rules)
        if rewritten_parts is None:
            return rewritten

        return ast.fix_missing_locations(
            _build_attribute_chain(rewritten_parts, rewritten)
        )

    def visit_Name(self, node: ast.Name) -> ast.AST:
        return self._visit_chain_node(node)

    def visit_Attribute(self, node: ast.Attribute) -> ast.AST:
        return self._visit_chain_node(node)


def _used_names(module: ast.Module) -> set[str]:
    return {
        candidate.id
        for candidate in ast.walk(module)
        if isinstance(candidate, ast.Name)
    }


def _strip_main_guards_and_entrypoint_decorators(module: ast.Module) -> None:
    filtered_body: list[ast.stmt] = []
    alias_map = build_import_alias_map(module)

    for node in module.body:
        if isinstance(node, ast.If) and _is_main_guard(node):
            continue

        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            node.decorator_list = [
                decorator
                for decorator in node.decorator_list
                if resolve_notebook_entry_decorator(decorator, alias_map).kind
                != "entrypoint"
            ]

        filtered_body.append(node)

    module.body = filtered_body


def _strip_expanded_imports(
    source_file: Path,
    module: ast.Module,
    expanded_module_paths: set[Path],
) -> list[tuple[tuple[str, ...], tuple[str, ...]]]:
    rewrite_rules: list[tuple[tuple[str, ...], tuple[str, ...]]] = []
    filtered_body: list[ast.stmt] = []

    for node in module.body:
        if isinstance(node, ast.Import):
            retained_aliases: list[ast.alias] = []
            for alias in node.names:
                if (
                    _import_target_path(source_file, node, alias)
                    in expanded_module_paths
                ):
                    rewrite_rule = _expanded_import_rewrite(source_file, node, alias)
                    if rewrite_rule is not None:
                        rewrite_rules.append(rewrite_rule)
                    continue
                retained_aliases.append(alias)

            if retained_aliases:
                node.names = retained_aliases
                filtered_body.append(node)
            continue

        if isinstance(node, ast.ImportFrom):
            retained_aliases = []
            for alias in node.names:
                if (
                    node.level == 0
                    and node.module == "astronote"
                    and alias.name == "notebook_entry"
                ):
                    continue

                if (
                    alias.name != "*"
                    and _import_target_path(source_file, node, alias)
                    in expanded_module_paths
                ):
                    rewrite_rule = _expanded_import_rewrite(source_file, node, alias)
                    if rewrite_rule is not None:
                        rewrite_rules.append(rewrite_rule)
                    continue

                retained_aliases.append(alias)

            if retained_aliases:
                node.names = retained_aliases
                filtered_body.append(node)
            continue

        filtered_body.append(node)

    module.body = filtered_body
    return rewrite_rules


def _strip_unused_astronote_imports(module: ast.Module) -> None:
    used_names = _used_names(module)
    filtered_body: list[ast.stmt] = []

    for node in module.body:
        if (
            isinstance(node, ast.ImportFrom)
            and node.level == 0
            and node.module == "astronote"
        ):
            retained_aliases = [
                alias for alias in node.names if alias.name != "notebook_entry"
            ]
            if retained_aliases:
                node.names = retained_aliases
                filtered_body.append(node)
            continue

        if isinstance(node, ast.Import):
            retained_aliases = []
            for alias in node.names:
                if alias.name != "astronote":
                    retained_aliases.append(alias)
                    continue

                local_name = alias.asname or alias.name
                if local_name in used_names:
                    retained_aliases.append(alias)

            if retained_aliases:
                node.names = retained_aliases
                filtered_body.append(node)
            continue

        filtered_body.append(node)

    module.body = filtered_body


def _render_transformed_module(module: ast.Module) -> str:
    ast.fix_missing_locations(module)
    rendered = ast.unparse(module)
    if not rendered.strip():
        return ""
    return rendered + "\n"


def _annotated_embedded_source(file_path: Path, rendered_source: str) -> str:
    if not rendered_source.strip():
        return ""
    return f"# Embedded from: {file_path}\n\n{rendered_source}"


def _source_for_notebook_with_expansions(
    file_path: Path,
    expanded_module_paths: set[Path],
) -> str:
    source = file_path.read_text(encoding="utf-8")
    module = ast.parse(source, filename=str(file_path))

    _strip_main_guards_and_entrypoint_decorators(module)
    rewrite_rules = _strip_expanded_imports(file_path, module, expanded_module_paths)
    if rewrite_rules:
        module = _ExpandedImportUsageRewriter(rewrite_rules).visit(module)
    _strip_unused_astronote_imports(module)

    return _render_transformed_module(module)


def _name_positions(node: ast.AST) -> set[tuple[int, int, int, int]]:
    return {
        _node_position(candidate)
        for candidate in ast.walk(node)
        if isinstance(candidate, ast.Name)
    }


def _is_name_only_used_in_removed_decorators(
    module: ast.Module,
    name: str,
    removed_name_positions: set[tuple[int, int, int, int]],
) -> bool:
    for candidate in ast.walk(module):
        if not isinstance(candidate, ast.Name) or candidate.id != name:
            continue
        if _node_position(candidate) not in removed_name_positions:
            return False
    return True


def _apply_line_edits(
    source: str,
    edits: list[tuple[int, int, list[str]]],
) -> str:
    lines = _split_source_lines(source)
    rendered: list[str] = []
    next_line = 1

    for start_line, end_line, replacement in sorted(edits):
        if start_line < next_line:
            continue
        rendered.extend(lines[next_line - 1 : start_line - 1])
        rendered.extend(replacement)
        next_line = end_line + 1

    rendered.extend(lines[next_line - 1 :])

    while rendered and not rendered[0].strip():
        rendered.pop(0)

    transformed_source = "".join(rendered)
    return (
        transformed_source
        if transformed_source.endswith("\n")
        else transformed_source + "\n"
    )


def _is_main_guard(node: ast.If) -> bool:
    if not isinstance(node.test, ast.Compare):
        return False
    if len(node.test.ops) != 1 or not isinstance(node.test.ops[0], ast.Eq):
        return False
    if len(node.test.comparators) != 1:
        return False

    left = node.test.left
    right = node.test.comparators[0]
    return (
        isinstance(left, ast.Name)
        and left.id == "__name__"
        and isinstance(right, ast.Constant)
        and right.value == "__main__"
    ) or (
        isinstance(right, ast.Name)
        and right.id == "__name__"
        and isinstance(left, ast.Constant)
        and left.value == "__main__"
    )


def _source_for_notebook(
    file_path: Path,
    expanded_module_paths: set[Path] | None = None,
) -> str:
    expanded_module_paths = expanded_module_paths or set()
    if expanded_module_paths:
        return _source_for_notebook_with_expansions(file_path, expanded_module_paths)

    source = file_path.read_text(encoding="utf-8")
    module = ast.parse(source, filename=str(file_path))
    alias_map = build_import_alias_map(module)
    edits: list[tuple[int, int, list[str]]] = []
    removed_name_positions: set[tuple[int, int, int, int]] = set()

    for node in module.body:
        if isinstance(node, ast.If) and _is_main_guard(node):
            start_line, end_line = _line_range(node)
            edits.append((start_line, end_line, []))
            continue

        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue

        for decorator in node.decorator_list:
            resolution = resolve_notebook_entry_decorator(decorator, alias_map)
            if resolution.kind != "entrypoint":
                continue
            start_line, end_line = _line_range(decorator)
            edits.append((start_line, end_line, []))
            removed_name_positions.update(_name_positions(decorator))

    for node in module.body:
        if isinstance(node, ast.ImportFrom):
            if not (node.level == 0 and node.module == "astronote"):
                continue

            retained_aliases = [
                alias for alias in node.names if alias.name != "notebook_entry"
            ]
            if len(retained_aliases) == len(node.names):
                continue

            start_line, end_line = _line_range(node)
            if retained_aliases:
                replacement = (
                    ast.unparse(
                        ast.ImportFrom(
                            module=node.module, names=retained_aliases, level=node.level
                        )
                    )
                    + "\n"
                )
                edits.append((start_line, end_line, _split_source_lines(replacement)))
            else:
                edits.append((start_line, end_line, []))
            continue

        if not isinstance(node, ast.Import):
            continue

        removable_aliases: list[ast.alias] = []
        for alias in node.names:
            if alias.name == "astronote":
                local_name = alias.asname or alias.name
                if _is_name_only_used_in_removed_decorators(
                    module,
                    local_name,
                    removed_name_positions,
                ):
                    removable_aliases.append(alias)

        if not removable_aliases:
            continue

        retained_aliases = [
            alias for alias in node.names if alias not in removable_aliases
        ]
        start_line, end_line = _line_range(node)
        if retained_aliases:
            replacement = ast.unparse(ast.Import(names=retained_aliases)) + "\n"
            edits.append((start_line, end_line, _split_source_lines(replacement)))
        else:
            edits.append((start_line, end_line, []))

    if not edits:
        return source if source.endswith("\n") else source + "\n"

    return _apply_line_edits(source, edits)


def _expanded_sources_for_notebook(
    source_file: Path,
    expand_modules: list[str],
) -> list[str] | None:
    resolved_modules = _resolve_expand_modules(source_file, expand_modules)
    if not resolved_modules:
        return None

    expanded_module_paths = {module_path for _, module_path, _ in resolved_modules}
    rendered_segments = [
        _annotated_embedded_source(
            module_path,
            _source_for_notebook(module_path, expanded_module_paths),
        )
        for _, module_path, _ in resolved_modules
    ]
    rendered_segments.append(
        _annotated_embedded_source(
            source_file,
            _source_for_notebook(source_file, expanded_module_paths),
        )
    )

    non_empty_segments = [segment for segment in rendered_segments if segment.strip()]
    if not non_empty_segments:
        return None
    return non_empty_segments


def build_notebook_payload(
    analysis: dict[str, Any],
    entrypoint: str,
    parameter_file: Path | None,
    overrides: list[str],
    *,
    expand_modules: list[str] | None = None,
    embed_files: list[str] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
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
    expansion_requests = _combine_expand_requests(
        analysis["file_path"],
        expand_modules or [],
        embed_files or [],
    )
    source_definitions = _expanded_sources_for_notebook(
        analysis["file_path"],
        expansion_requests,
    )
    assignment_lines = [f"{name} = {parameters[name]!r}" for name in parameters]
    parameters_source: str | None = "\n".join(assignment_lines)
    if parameters_source:
        parameters_source += "\n"
    else:
        parameters_source = None
    entrypoint_call = (
        f"{entrypoint}(**{parameters!r})\n" if parameters else f"{entrypoint}()\n"
    )

    execution_payload: dict[str, Any] = {
        "entrypoint_call": entrypoint_call,
    }
    if source_definitions:
        execution_payload["source_definitions"] = source_definitions
    else:
        execution_payload["source_definition"] = _source_for_notebook(
            analysis["file_path"]
        )

    resolved_notebook_ir = {
        "script_path": str(analysis["file_path"]),
        "parameter_path": str(parameter_file) if parameter_file else None,
        "parameters_source": parameters_source,
        "generated_at": manifest.generated_at,
        "execution": execution_payload,
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


def generate_notebook(
    analysis: dict[str, Any],
    entrypoint: str,
    parameter_file: Path | None,
    overrides: list[str],
    output_path: Path | None,
    *,
    expand_modules: list[str] | None = None,
    embed_files: list[str] | None = None,
) -> Path:
    destination = output_path or default_output_path(analysis["file_path"])
    destination.parent.mkdir(parents=True, exist_ok=True)
    notebook, _ = build_notebook_payload(
        analysis,
        entrypoint,
        parameter_file,
        overrides,
        expand_modules=expand_modules,
        embed_files=embed_files,
    )
    destination.write_text(
        json.dumps(notebook, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return destination


def main(argv: list[str] | None = None) -> int:
    try:
        args = resolve_cli_args(argv)
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
            print(
                json.dumps(
                    resolution.parameter_schema.as_dict(), indent=2, ensure_ascii=False
                )
            )
        output_path = generate_notebook(
            analysis,
            entrypoint,
            args.parameter_file,
            args.override,
            args.output,
            expand_modules=args.expand_module,
            embed_files=args.embed_file,
        )
    except CliError as exc:
        raise SystemExit(str(exc)) from exc
    except ParameterFileError as exc:
        raise SystemExit(str(exc)) from exc
    except PyprojectConfigError as exc:
        raise SystemExit(str(exc)) from exc

    print(f"Notebook written to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


if __name__ == "__main__":
    raise SystemExit(main())
