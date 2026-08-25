import numpy as np
from app.body_shape import AnthropometricBodyService
from app.schemas import BodyMeasurements


def test_completion_keeps_height_independent_from_weight():
    base = dict(height=162, bust=84, waist=66, hip=92, shoulder=38)
    light = AnthropometricBodyService.complete(BodyMeasurements(weight=52, **base), np.zeros(19))
    heavy = AnthropometricBodyService.complete(BodyMeasurements(weight=82, **base), np.zeros(19))
    assert light["height"] == heavy["height"] == 162
    assert heavy["thigh"] > light["thigh"]
    assert heavy["knee"] > light["knee"]


def test_optional_measurements_are_preserved():
    body = BodyMeasurements(height=168, weight=60, bust=88, waist=70, hip=96, shoulder=39, thigh=59, knee=39)
    completed = AnthropometricBodyService.complete(body, np.zeros(19))
    assert completed["thigh"] == 59
    assert completed["knee"] == 39

