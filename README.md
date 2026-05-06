# astronote: AST to Reprodceble Output NOTEbook
This tool allows to generate a Jupyter notebook from a Python script.
The generated notebook includes the original source code and hyperparameters used for execution, enabling reproducibility and easy sharing of results.

## Usage
A notebook entry is defined by decorating a function with `@notebook_entry`.
This marks the function as an entry point for notebook generation.
When the decorated function is executed, `astronote` captures its source code and parameters, and generates a notebook that includes this information.

```python
from astronote import notebook_entry


def func() -> str:
    return "This is a sub-function, not a notebook entry."


def calc(x: int, y: int) -> int:
    return x + y


@notebook_entry
def main(a: int = 10, b: int = 20) -> str:
    result = calc(a, b)
    return f"The result of calc({a}, {b}) is {result}"


if __name__ == "__main__":
    main()
```

And run the script with:

```bash
astronote example.py
```

you are able to find the generated notebook in the same directory as `example.py` with a name like `example.ipynb`.

To embed local helper code directly into the generated notebook instead of keeping imports, use `--expand-module` for imported module names and `--embed-file` for local `.py` paths:

```bash
astronote examples/example_multiple_file.py --expand-module sub_mod
astronote examples/example_multiple_file.py --embed-file examples/sub_mod.py
```

When `--embed-file` is used, the `.py` path must resolve to a local module that is actually imported by the source script.

## pyproject.toml Configuration
CLI options can also be provided from `[tool.astronote]` in `pyproject.toml`.
CLI arguments take precedence over `pyproject.toml`, and list-style options are merged as `pyproject.toml` first, then CLI.

```toml
[tool.astronote]
# Each variable can be defaulted here, and overridden on the CLI when needed.
# Default SOURCE when you run astronote without a positional SOURCE argument.
# If SOURCE is passed on the CLI, that CLI value is used instead.
source = "examples/example_single_file.py"
# Base parameter set (JSON) to run the entrypoint reproducibly.
parameter_file = "examples/params.json"
# Quick per-run overrides; useful for changing only a few values without editing JSON.
override = ['beta="from_pyproject"']
# Target function to execute when multiple @notebook_entry functions exist.
entrypoint = "run"
# Inline imported local modules by module name (keeps notebook self-contained).
expand_module = ["sub_mod"]
# Inline imported local modules by file path instead of module name.
embed_file = ["examples/sub_mod.py"]
# Where to save the generated notebook.
output = "dist/example_single_file.ipynb"
# Show dependency/expansion analysis to verify what was included.
show_analysis = true
# Show parameter schema/metadata to document expected inputs.
show_schema = true
```

Usage notes:

- `source` is for the "no positional SOURCE" workflow. It lets you run `astronote` with no source argument.
- CLI positional `SOURCE` overrides `[tool.astronote].source`.
- Scalar options such as `parameter_file`, `entrypoint`, and `output` use CLI values when provided, otherwise `pyproject.toml` values.
- List options (`override`, `expand_module`, `embed_file`) are merged in order: `pyproject.toml` first, then CLI values.
- `show_analysis` and `show_schema` are enabling flags: passing CLI flags turns them on; when omitted, `pyproject.toml` values are used.

With that configuration, `astronote` can be run without repeating those options on the command line.

