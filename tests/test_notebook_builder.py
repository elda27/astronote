from astronote.notebook import NotebookBuilder, build_notebook_json


def test_builder_outputs_required_cells_and_metadata() -> None:
    resolved_ir = {
        "script_path": "pipelines/example.py",
        "parameter_path": "params/dev.yaml",
        "parameters_source": "run_date = '2026-03-20'\nmode = 'dev'\n",
        "generated_at": "2026-03-20T00:00:00Z",
        "manifest": {
            "source_path": "pipelines/example.py",
            "entrypoint": "main",
            "generated_at": "2026-03-20T00:00:00Z",
            "tool_version": "0.1.0",
            "parameter_file": "params/dev.yaml",
            "parameters": {"run_date": "2026-03-20", "mode": "dev"},
            "parameter_sources": {"run_date": "parameter_json", "mode": "parameter_json"},
            "parameter_schema": {"entrypoint": "main", "fields": []},
        },
        "execution": {
            "source_import": "from pipelines.example import main\n",
            "entrypoint_call": "main(run_date=run_date, mode=mode)\n",
        },
        "notebook": {
            "script_first": True,
            "read_only": True,
            "markdown_cells": ["# Example notebook\n"],
            "metadata": {
                "kernel_name": "python3",
                "kernel_display_name": "Python 3",
                "language": "python",
                "language_version": "3.12",
                "extra": {"team": "data-platform"},
            },
        },
    }

    notebook = NotebookBuilder().build(resolved_ir)

    assert notebook["nbformat"] == 4
    assert notebook["metadata"]["astronote"] == {
        "generated": True,
        "version": 1,
        "script_first": True,
        "read_only": True,
        "source_script": "pipelines/example.py",
        "parameter_file": "params/dev.yaml",
        "manifest": resolved_ir["manifest"],
        "extra": {"team": "data-platform"},
    }

    cells = notebook["cells"]
    assert [cell["metadata"]["astronote"]["role"] for cell in cells] == [
        "context",
        "script_reference",
        "parameters",
        "source_import",
        "entrypoint",
        "generated_metadata",
    ]
    assert cells[2]["source"] == ["run_date = '2026-03-20'\n", "mode = 'dev'\n"]
    # The parameters cell must be tagged with "parameters" for Papermill compatibility.
    assert "parameters" in cells[2]["metadata"].get("tags", [])
    assert cells[3]["source"] == ["from pipelines.example import main\n"]
    assert cells[4]["source"] == ["main(run_date=run_date, mode=mode)\n"]
    assert "READ_ONLY = True" in "".join(cells[5]["source"])
    assert "MANIFEST = {'source_path': 'pipelines/example.py'" in "".join(cells[5]["source"])


def test_builder_supports_attribute_based_resolved_ir() -> None:
    class Metadata:
        kernel_name = "python3"
        kernel_display_name = "Python 3"
        language = "python"
        language_version = "3.12"

    class Notebook:
        script_first = False
        read_only = False
        metadata = Metadata()

    class Execution:
        source_import = "from demo import run\n"
        entrypoint_call = "run()\n"

    class ResolvedIR:
        script_path = "demo.py"
        parameter_path = None
        parameters_source = None
        generated_at = None
        notebook = Notebook()
        execution = Execution()

    notebook = NotebookBuilder().build(ResolvedIR())
    roles = [cell["metadata"]["astronote"]["role"] for cell in notebook["cells"]]

    assert roles == ["source_import", "entrypoint", "generated_metadata"]
    assert notebook["metadata"]["astronote"]["script_first"] is False
    assert notebook["metadata"]["astronote"]["read_only"] is False


def test_build_notebook_json_returns_ipynb_json_text() -> None:
    notebook_json = build_notebook_json(
        {
            "execution": {"entrypoint_call": "main()\n"},
            "notebook": {"read_only": True, "script_first": True},
        }
    )

    assert '"nbformat": 4' in notebook_json
    assert '"cell_type": "code"' in notebook_json
