from __future__ import annotations

import pytest
from pydantic import ValidationError

from astronote._model import FrozenModel


class ExampleModel(FrozenModel):
    name: str


def test_frozen_model_forbids_extra_fields() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        ExampleModel(name="demo", extra="value")


def test_frozen_model_is_immutable() -> None:
    model = ExampleModel(name="demo")

    with pytest.raises(ValidationError) as exc_info:
        model.name = "changed"

    assert exc_info.value.errors()[0]["type"] == "frozen_instance"