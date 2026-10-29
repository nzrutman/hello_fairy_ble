"""Per-curtain installation transforms, applied only at the transport boundary.

Generated with aurora@aurora-smart-home (ha-integration-dev skill)
https://github.com/tonylofgren/aurora-smart-home
"""

from __future__ import annotations

from .pixel_protocol import PIXEL_COUNT, validate_color_byte


def validate_orientation(value: dict | None = None) -> dict:
    """Normalize one installation correction: clockwise rotation, then flips."""
    if value is None:
        value = {}
    if not isinstance(value, dict):
        raise ValueError("Curtain orientation must be an object")
    rotation = value.get("rotation", 0)
    flip_h, flip_v = value.get("flip_h", False), value.get("flip_v", False)
    if type(rotation) is not int or rotation not in (0, 90, 180, 270):
        raise ValueError("Curtain rotation must be 0, 90, 180 or 270 degrees")
    if type(flip_h) is not bool or type(flip_v) is not bool:
        raise ValueError("Curtain flip settings must be true or false")
    return {"rotation": rotation, "flip_h": flip_h, "flip_v": flip_v}


def transform_frame(frame: list[int], orientation: dict | None = None) -> list[int]:
    """Transform a row-major 20x20 tile without changing device index framing."""
    if len(frame) != PIXEL_COUNT:
        raise ValueError("Orientation requires a complete 20×20 curtain frame")
    for color in frame:
        validate_color_byte(color)
    correction = validate_orientation(orientation)
    turns = correction["rotation"] // 90
    result = [254] * PIXEL_COUNT
    for i, color in enumerate(frame):
        x, y = i % 20, i // 20
        for _ in range(turns):
            x, y = 19 - y, x
        if correction["flip_h"]:
            x = 19 - x
        if correction["flip_v"]:
            y = 19 - y
        result[y * 20 + x] = color
    return result
