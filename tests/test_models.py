from pydantic import BaseModel

from astronote.analysis.resolver import DecoratorResolution
from astronote.ir import DecoratorIR, FunctionArgIR, FunctionSignatureIR, ResolvedIR, SourceLocation, StaticIR
from astronote.manifest import Manifest
from astronote.params import LoadedParameters, ParameterField, ParameterResolution, ParameterSchema


def test_public_models_are_pydantic_models() -> None:
    models = [
        DecoratorIR,
        DecoratorResolution,
        FunctionArgIR,
        FunctionSignatureIR,
        LoadedParameters,
        Manifest,
        ParameterField,
        ParameterResolution,
        ParameterSchema,
        ResolvedIR,
        SourceLocation,
        StaticIR,
        StaticIR.Function,
    ]

    assert all(issubclass(model, BaseModel) for model in models)