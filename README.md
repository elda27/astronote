# astronote

`astronote` は notebook 化したい関数を entrypoint としてマークするための最小 API を提供します。

## Usage

```python
from astronote import notebook_entry


@notebook_entry
def daily_report() -> None:
    print("build report")


@notebook_entry(name="weekly-summary")
def weekly_summary() -> None:
    print("build summary")
```

`@notebook_entry` と `@notebook_entry(...)` の両方を利用できます。各関数には将来の CLI が複数 entrypoint を識別しやすいよう、`__astronote_notebook_entries__` 属性へタプル形式でメタデータが保持されます。


## Parameter file workflow

`astronote` can read a JSON parameter file, merge CLI overrides, and record the resolved inputs in notebook metadata.

```json
{
  "run_date": "2026-03-20",
  "mode": "daily"
}
```

```bash
astronote pipelines/report.py   --entrypoint run_report   --parameter-file params/report.json   --override mode="weekly"   --show-schema
```

Generation flow:

1. `--parameter-file` loads a JSON object and matches keys against the selected entrypoint signature.
2. Signature defaults fill in missing optional arguments.
3. `--override KEY=JSON` applies last and wins over the parameter file.
4. The emitted notebook metadata stores a manifest containing the resolved parameters, source path, entrypoint, generated timestamp, tool version, and a simplified parameter schema.


## Module expansion

Use `--expand-module MODULE` to inline a local dependency directly into the generated notebook source when the source script imports sibling modules.

```bash
astronote examples/example_multiple_file.py --expand-module sub_module
```

`--expand-module` accepts module names only. The value must exactly match the import string used in the source.

For `from sub_mod import func`, pass `--expand-module sub_mod`. For `from pkg import sub_mod`, pass `--expand-module pkg.sub_mod`.

For example, `sub_module` and `.sub_module` are treated as different values.

Relative import targets such as `.sub_module` are still unsupported as direct `--expand-module` values. Rewrite them to absolute imports before passing them on the CLI.

astronote recursively expands local dependencies imported by any requested module. Repeat `--expand-module` only when the source script itself imports multiple top-level local modules that should be embedded.
