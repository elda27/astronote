import importlib.metadata

from astronote.decorators import NOTEBOOK_ENTRY_ATTR, notebook_entry

try:
    __version__ = importlib.metadata.version("astronote")
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.0.0"

__all__ = ["__version__", "NOTEBOOK_ENTRY_ATTR", "main", "notebook_entry"]


def main(argv: list[str] | None = None) -> int:
    from astronote.cli import main as cli_main

    return cli_main(argv)
    return cli_main(argv)
    return cli_main(argv)
