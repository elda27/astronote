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


