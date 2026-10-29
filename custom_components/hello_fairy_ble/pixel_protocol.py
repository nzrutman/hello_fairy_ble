"""Pixel/DIY protocol helpers for 400-LED Hello Fairy curtain lights.

Protocol details are based on captures from the Hello Fairy app and the
reverse-engineering work in yamatt/curtains. These helpers are intentionally
Home-Assistant independent so packet construction can be unit-tested.
Generated with aurora@aurora-smart-home
(ha-integration-dev skill) https://github.com/tonylofgren/aurora-smart-home
"""

from __future__ import annotations

import colorsys
from collections.abc import Iterable, Sequence

HEADER = 0xAA
MATRIX_WIDTH = 20
MATRIX_HEIGHT = 20
PIXEL_COUNT = MATRIX_WIDTH * MATRIX_HEIGHT

PACKET_PIXEL_MODE = 0xD0
PACKET_PIXEL_BULK_UPDATE = 0xDA
PACKET_PIXEL_UPDATE = PACKET_PIXEL_BULK_UPDATE  # DIY writes captured from the official Android app

PIXEL_OFF = 0xFE
PIXEL_WHITE = 0xFF
MAX_PIXEL_UPDATES_PER_PACKET = 79  # Android full-frame chunk: 242-byte GATT value


def checksum(data: Iterable[int]) -> int:
    """Return Hello Fairy's additive checksum."""
    return sum(data) & 0xFF


def build_packet(packet_type: int, payload: Sequence[int]) -> bytes:
    """Build AA + type + payload length + payload + checksum packet."""
    if not 0 <= packet_type <= 0xFF:
        raise ValueError("packet_type must be 0..255")
    if len(payload) > 0xFF:
        raise ValueError("payload too large for one-byte length field")

    body = [HEADER, packet_type, len(payload), *payload]
    return bytes([*body, checksum(body)])


def build_d0_packet(action: int) -> bytes:
    """Build a D0 sub-command seen in the Android official-app trace."""
    if action not in (0x00, 0x01, 0x03, 0x04):
        raise ValueError("unsupported D0 sub-command")
    return build_packet(PACKET_PIXEL_MODE, [0x00, 0x64, 0x64, action])


def build_draw_mode_packet() -> bytes:
    """Enter the controller's DIY/drawing mode."""
    return build_d0_packet(0x00)


def build_clear_packet() -> bytes:
    """Clear the 20x20 DIY matrix."""
    return build_d0_packet(0x03)


def pixel_index(x: int, y: int) -> int:
    """Map x/y to the controller's column-major 0..399 pixel index."""
    if not 0 <= x < MATRIX_WIDTH:
        raise ValueError(f"x must be 0..{MATRIX_WIDTH - 1}")
    if not 0 <= y < MATRIX_HEIGHT:
        raise ValueError(f"y must be 0..{MATRIX_HEIGHT - 1}")
    return x * MATRIX_HEIGHT + y


def validate_color_byte(color_byte: int) -> int:
    if type(color_byte) is not int or not (0 <= color_byte <= 180 or color_byte in (254, 255)):
        raise ValueError("color byte must be an integer 0..180, 254 (off), or 255 (white)")
    return color_byte


def rgb_to_pixel_byte(r: int, g: int, b: int) -> int:
    """Approximate an RGB color using the curtain's one-byte DIY color format.

    Observed protocol behavior:
    - 0xFE = off/black
    - 0xFF = white
    - 0x00..0xB4 ~= hue 0..360 degrees compressed by a factor of 2

    The DIY protocol does not appear to carry per-pixel saturation/brightness,
    so non-white RGB colors are represented by their hue.
    """
    r = max(0, min(255, int(r)))
    g = max(0, min(255, int(g)))
    b = max(0, min(255, int(b)))

    h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)

    if v <= 0.05:
        return PIXEL_OFF
    if s <= 0.10:
        return PIXEL_WHITE

    hue_degrees = h * 360.0
    # Captures show green -> 0x3C (60), blue -> 0x78 (120), i.e. hue / 2.
    return min(0xB4, max(0, round(hue_degrees / 2.0)))


def build_pixel_update_packet(updates: Sequence[tuple[int, int, int]]) -> bytes:
    """Build one Android-app-compatible DA packet (slot 1) with up to 79 pixels.

    Official Pixel 8 Pro capture, 2026-10-14:
      AA DA 04 01 00 E2 00 6B  -> index 226, color 0x00
    DA payload = [slot (1), index_hi, index_lo, raw_color, ...].
    Full chunks require a confirmed ATT MTU of at least 245; API preflight gates them.
    """
    if not 1 <= len(updates) <= MAX_PIXEL_UPDATES_PER_PACKET:
        raise ValueError(f"one pixel packet must contain 1..{MAX_PIXEL_UPDATES_PER_PACKET} updates")

    payload: list[int] = [0x01]  # DIY canvas/slot ID observed in app capture
    for x, y, color_byte in updates:
        index = pixel_index(x, y)
        color = validate_color_byte(color_byte)
        payload.extend([(index >> 8) & 0xFF, index & 0xFF, color])

    return build_packet(PACKET_PIXEL_UPDATE, payload)


def iter_pixel_update_packets(
    updates: Sequence[tuple[int, int, int]],
) -> Iterable[bytes]:
    """Yield verified-format DA packets, batching updates 79 pixels at a time."""
    for offset in range(0, len(updates), MAX_PIXEL_UPDATES_PER_PACKET):
        batch = updates[offset : offset + MAX_PIXEL_UPDATES_PER_PACKET]
        if batch:
            yield build_pixel_update_packet(batch)


def row_major_frame_to_updates(pixels: Sequence[int]) -> list[tuple[int, int, int]]:
    """Convert 400 row-major color bytes to controller x/y updates."""
    if len(pixels) != PIXEL_COUNT:
        raise ValueError(f"frame must contain exactly {PIXEL_COUNT} pixels")

    updates: list[tuple[int, int, int]] = []
    for y in range(MATRIX_HEIGHT):
        for x in range(MATRIX_WIDTH):
            color = validate_color_byte(pixels[y * MATRIX_WIDTH + x])
            updates.append((x, y, color))
    return updates


def split_virtual_frame(pixels: Sequence[int], curtain_count: int) -> list[list[int]]:
    """Split one (20 * N) x 20 row-major canvas into N 20x20 frames.

    Curtains are ordered left-to-right. Each returned frame is row-major 20x20.
    """
    if curtain_count < 1:
        raise ValueError("curtain_count must be >= 1")

    virtual_width = MATRIX_WIDTH * curtain_count
    expected = virtual_width * MATRIX_HEIGHT
    if len(pixels) != expected:
        raise ValueError(
            f"virtual frame for {curtain_count} curtains must contain {expected} pixels"
        )

    frames = [[] for _ in range(curtain_count)]
    for y in range(MATRIX_HEIGHT):
        row_offset = y * virtual_width
        for curtain in range(curtain_count):
            start = row_offset + curtain * MATRIX_WIDTH
            end = start + MATRIX_WIDTH
            frames[curtain].extend(validate_color_byte(value) for value in pixels[start:end])
    return frames
