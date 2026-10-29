"""Native music and scene-speed framing traced to the official Android APK.

Callers must gate music on advertised music_mode=3 and scene-speed writes on a
valid scene-speed response from the current BLE connection. These pure helpers
perform no discovery, writes, retries or support inference.

Generated with aurora@aurora-smart-home (ha-integration-dev skill)
https://github.com/tonylofgren/aurora-smart-home
"""

from .pixel_protocol import build_packet


def _integer(value: int, low: int, high: int, name: str) -> int:
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f"{name} must be an integer {low}..{high}")
    return value


def build_music_command(
    mode: int,
    sensitivity: int,
    brightness: int,
    hue: int,
    saturation: int,
    auto: bool,
) -> bytes:
    """Select the curtain microphone, never the phone microphone modes 5..8.

    Cmds.MusicMode / SetLightCmd and x03/g13: modes 1..4 use the
    device microphone; the phone path adds four and streams AppMicCmd separately.
    x03.o forces automatic colors for mode 1. Brightness and saturation use
    thousandths; UI percentages are converted here. Hue uses degrees.
    """
    _integer(mode, 1, 4, "music mode")
    _integer(sensitivity, 1, 100, "sensitivity")
    _integer(brightness, 1, 100, "brightness")
    _integer(hue, 0, 360, "hue")
    _integer(saturation, 0, 100, "saturation")
    if type(auto) is not bool:
        raise ValueError("automatic color must be a boolean")
    auto = auto or mode == 1
    payload = bytes([3, mode << 4 | int(auto), sensitivity])
    for value in (brightness * 10, hue, saturation * 10):
        payload += value.to_bytes(2, "big")
    return build_packet(0x03, payload)


def build_scene_speed_query() -> bytes:
    """Read speed using the app's empty 0x0C capability query."""
    return build_packet(0x0C, [])


def build_scene_speed_command(speed: int) -> bytes:
    """Set speed only after the caller confirms a current-connection response."""
    return build_packet(0x0C, [_integer(speed, 0, 100, "scene speed")])


def decode_scene_speed(data: bytes) -> int | None:
    """Accept an exact checksummed one-byte 0x0C response, never an ACK."""
    if (
        len(data) != 5
        or data[:3] != b"\xaa\x0c\x01"
        or sum(data[:-1]) & 255 != data[-1]
        or data[3] > 100
    ):
        return None
    return data[3]


def decode_music_status(data: bytes) -> dict | None:
    """Decode the eight-byte music body in a real 0x01 status notification.

    Raw status is distinct from a requested music selection. No audio samples
    or pixel readback are present. Unrecognized/reserved mode flags fail closed.
    """
    if len(data) != 17 or data[:3] != b"\xaa\x01\x0d" or sum(data[:-1]) & 255 != data[-1]:
        return None
    payload = data[3:-1]
    if payload[3] not in (0, 1) or payload[4] != 3:
        return None
    mode, auto = payload[5] >> 4, payload[5] & 15
    sensitivity = payload[6]
    brightness = int.from_bytes(payload[7:9], "big")
    hue = int.from_bytes(payload[9:11], "big")
    saturation = int.from_bytes(payload[11:13], "big")
    if (
        mode not in range(1, 9)
        or auto not in (0, 1)
        or sensitivity > 100
        or brightness > 1000
        or hue > 360
        or saturation > 1000
    ):
        return None
    return {
        "music_mode": mode,
        "microphone": "device" if mode <= 4 else "phone",
        "auto_color": bool(auto),
        "sensitivity": sensitivity,
        "brightness_raw": brightness,
        "brightness_percent": brightness / 10,
        "hue": hue,
        "saturation_raw": saturation,
    }
