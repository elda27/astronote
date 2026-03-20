from __future__ import annotations

import astronote
from astronote.decorators import NOTEBOOK_ENTRY_ATTR, notebook_entry


def test_notebook_entry_records_default_metadata() -> None:
    @notebook_entry
    def run() -> str:
        return "ok"

    assert run() == "ok"
    assert getattr(run, NOTEBOOK_ENTRY_ATTR) == ({"name": None},)


def test_notebook_entry_records_explicit_name_without_wrapping_callable() -> None:
    def run() -> str:
        return "ok"

    decorated = notebook_entry(name="daily")(run)

    assert decorated is run
    assert getattr(run, NOTEBOOK_ENTRY_ATTR) == ({"name": "daily"},)


def test_notebook_entry_appends_multiple_entry_definitions() -> None:
    @notebook_entry(name="weekly")
    @notebook_entry
    def run() -> None:
        return None

    assert getattr(run, NOTEBOOK_ENTRY_ATTR) == (
        {"name": None},
        {"name": "weekly"},
    )


def test_package_root_reexports_decorator_api() -> None:
    assert astronote.NOTEBOOK_ENTRY_ATTR == NOTEBOOK_ENTRY_ATTR
    assert astronote.notebook_entry is notebook_entry
