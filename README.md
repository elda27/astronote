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
