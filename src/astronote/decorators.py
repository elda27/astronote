from collections.abc import Callable
from typing import Any, TypeVar, overload

F = TypeVar("F", bound=Callable[..., Any])

NOTEBOOK_ENTRY_ATTR = "__astronote_notebook_entries__"


@overload
def notebook_entry(func: F, /) -> F: ...


@overload
def notebook_entry(
    *, name: str | None = None, save_to: str | None = None
) -> Callable[[F], F]: ...


def notebook_entry(
    func: F | None = None,
    /,
    *,
    name: str | None = None,
    save_to: str | None = None,
) -> F | Callable[[F], F]:
    """Mark a function as an Astronote notebook entrypoint.

    The decorator stores lightweight metadata on the decorated function so
    AST-based tooling and future CLI features can identify one or more
    notebook entrypoints without changing runtime behavior.
    """

    def decorate(target: F) -> F:
        entries = list(getattr(target, NOTEBOOK_ENTRY_ATTR, ()))
        entries.append({"name": name, "save_to": save_to})
        setattr(target, NOTEBOOK_ENTRY_ATTR, tuple(entries))
        return target

    if func is not None:
        return decorate(func)

    return decorate
