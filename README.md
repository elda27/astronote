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
source = "examples/example_single_file.py"
parameter_file = "examples/params.json"
override = ['beta="from_pyproject"']
entrypoint = "run"
expand_module = ["sub_mod"]
embed_file = ["examples/sub_mod.py"]
output = "dist/example_single_file.ipynb"
show_analysis = true
show_schema = true
```

With that configuration, `astronote` can be run without repeating those options on the command line.


