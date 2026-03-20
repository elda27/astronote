from __future__ import annotations

from typing import Any, Callable, TypeVar

F = TypeVar("F", bound=Callable[..., Any])


def notebook_entry(func: F | None = None, **_: Any):
    """Marker decorator used by astronote static analysis.

    The decorator is intentionally runtime-noop so source files can import it
    without affecting execution.
    """

    def decorate(target: F) -> F:
        return target

    if func is None:
        return decorate
    return decorate(func)


def main() -> None:
    print("Hello from astronote!")
