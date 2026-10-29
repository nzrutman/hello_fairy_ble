"""Installation transforms preserve pixels and framing (ha-integration-dev skill).
https://github.com/tonylofgren/aurora-smart-home
"""

import pytest

from custom_components.hello_fairy_ble.orientation import transform_frame, validate_orientation


@pytest.mark.parametrize("rotation,index", [(0, 0), (90, 19), (180, 399), (270, 380)])
def test_corner_rotation(rotation, index):
    frame = [254] * 400
    frame[0] = 0
    result = transform_frame(frame, {"rotation": rotation})
    assert result[index] == 0
    assert result.count(0) == 1
    assert frame[0] == 0
    assert frame.count(0) == 1


@pytest.mark.parametrize("flip,index", [("flip_h", 19), ("flip_v", 380)])
def test_installation_flips(flip, index):
    frame = [254] * 400
    frame[0] = 255
    assert transform_frame(frame, {flip: True})[index] == 255


def test_rotation_then_flips_and_four_turns():
    frame = [i % 181 for i in range(400)]
    result = frame[:]
    for _ in range(4):
        result = transform_frame(result, {"rotation": 90})
    assert result == frame
    result = transform_frame(frame, {"rotation": 90, "flip_h": True})
    assert result[0] == frame[0]
    assert sorted(result) == sorted(frame)


@pytest.mark.parametrize("bad", [{"rotation": True}, {"rotation": 45}, {"flip_h": 1}, []])
def test_invalid_orientation_rejected(bad):
    with pytest.raises(ValueError):
        validate_orientation(bad)
