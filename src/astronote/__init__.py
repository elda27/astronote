from __future__ import annotations

from astronote.decorators import NOTEBOOK_ENTRY_ATTR, notebook_entry

__version__ = "0.1.0"

__all__ = ["__version__", "NOTEBOOK_ENTRY_ATTR", "main", "notebook_entry"]


def main(argv: list[str] | None = None) -> int:
    from astronote.cli import main as cli_main

    return cli_main(argv)
