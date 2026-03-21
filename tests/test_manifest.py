import json
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel

import astronote.manifest as manifest_module
from astronote import __version__
from astronote.analysis import analyze_python_file
from astronote.manifest import Manifest, build_manifest
from astronote.params import resolve_entrypoint_parameters

SOURCE = """
from astronote import notebook_entry

@notebook_entry
def run(alpha: int, beta: str = "x") -> None:
    return None
"""


class FrozenDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(2026, 3, 20, 1, 2, 3, tzinfo=tz or timezone.utc)


def test_build_manifest_includes_resolution_metadata(
    monkeypatch: object, tmp_path: Path
) -> None:
    source = tmp_path / "sample.py"
    source.write_text(SOURCE, encoding="utf-8")
    params = tmp_path / "params.json"
    params.write_text(json.dumps({"alpha": 7}), encoding="utf-8")
    static_ir = analyze_python_file(source)
    resolution = resolve_entrypoint_parameters(
        static_ir,
        entrypoint="run",
        parameter_file=params,
        cli_overrides={"beta": "override"},
    )
    monkeypatch.setattr(manifest_module, "datetime", FrozenDateTime)  # type:ignore

    manifest = build_manifest(str(source.resolve()), resolution)

    assert issubclass(Manifest, BaseModel)
    assert isinstance(manifest, BaseModel)
    assert manifest.as_dict() == {
        "source_path": str(source.resolve()),
        "entrypoint": "run",
        "generated_at": "2026-03-20T01:02:03Z",
        "tool_version": __version__,
        "parameters": {"alpha": 7, "beta": "override"},
        "parameter_sources": {
            "alpha": "parameter_json",
            "beta": "cli_override",
        },
        "parameter_file": str(params),
        "parameter_schema": {
            "entrypoint": "run",
            "fields": [
                {
                    "name": "alpha",
                    "kind": "positional",
                    "type": "int",
                    "required": True,
                    "default": None,
                },
                {
                    "name": "beta",
                    "kind": "positional",
                    "type": "str",
                    "required": False,
                    "default": "x",
                },
            ],
        },
    }
