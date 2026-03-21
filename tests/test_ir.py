from pydantic import BaseModel

from astronote._model import FrozenModel
from astronote.ir import (
    DecoratorIR,
    FunctionArgIR,
    FunctionSignatureIR,
    ResolvedIR,
    SourceLocation,
    StaticFunction,
    StaticFunctionIR,
    StaticIR,
    UnsupportedCase,
)


def test_ir_models_are_frozen_pydantic_models() -> None:
    models = [
        DecoratorIR,
        FunctionArgIR,
        FunctionSignatureIR,
        ResolvedIR,
        SourceLocation,
        StaticFunction,
        StaticFunctionIR,
        StaticIR,
        UnsupportedCase,
    ]

    assert all(issubclass(model, BaseModel) for model in models)
    assert all(issubclass(model, FrozenModel) for model in models)
    assert StaticIR.Function is StaticFunction


def test_resolved_ir_wraps_nested_static_models() -> None:
    location = SourceLocation(
        path="sample.py",
        lineno=3,
        end_lineno=5,
        col_offset=0,
        end_col_offset=12,
    )
    signature = FunctionSignatureIR(
        args=[
            FunctionArgIR(
                name="alpha",
                kind="positional",
                annotation="int",
            )
        ],
        return_annotation="None",
    )
    function = StaticIR.Function(
        name="run",
        signature=signature,
        location=location,
        decorators=[
            DecoratorIR(
                raw="notebook_entry",
                kind="entrypoint",
                resolved_name="astronote.notebook_entry",
            )
        ],
        is_entrypoint=True,
    )
    unsupported = UnsupportedCase(
        message="Star imports are unsupported.", location=location
    )
    static_ir = StaticIR(
        module_path="sample.py",
        import_aliases={"entry": "astronote.notebook_entry"},
        functions=[function],
        entrypoints=["run"],
        unsupported=[unsupported],
    )

    resolved = ResolvedIR(
        static_ir=static_ir,
        entrypoint_name="run",
        signature=signature,
        resolved_parameters={"alpha": 1},
        parameter_sources={"alpha": "cli_override"},
    )

    assert resolved.static_ir.functions[0].location.path == "sample.py"
    assert resolved.static_ir.unsupported == [unsupported]
    assert resolved.resolved_parameters == {"alpha": 1}
    assert resolved.parameter_sources == {"alpha": "cli_override"}
