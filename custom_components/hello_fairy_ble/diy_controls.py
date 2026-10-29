"""DIY controls/status decoded from the official Android APK, SHA256 in EVIDENCE.

Generated with aurora@aurora-smart-home (ha-integration-dev skill)
https://github.com/tonylofgren/aurora-smart-home
"""

from .pixel_protocol import build_packet

# DiyGlobalPictureConfig / f8 / SetDirectionView DIY_Type==3 (captured device).
MOVEMENTS = {
    "still": 0,
    "up": 1,
    "down": 2,
    "left": 3,
    "right": 4,
    "blink": 5,
    "breathe": 6,
    "loop_up": 7,
    "loop_down": 8,
    "loop_left": 9,
    "loop_right": 10,
}


def build_playback_commands(kind: str, movement: str, speed: int, brightness: int) -> list[bytes]:
    """Set_Picture_Parameter: direction, brightness, speed, action.

    DiyPictureShowActivity.CmdS_Set_send maps dynamic blink/breathe to 0/1;
    RadioButton_init/sendDynamicPictureModel select DC 0/1. Static uses f8 IDs.
    No frame-rate conversion, generic pause command or synchronized-start claim.
    """
    if (
        not isinstance(kind, str)
        or not isinstance(movement, str)
        or kind not in ("picture", "animation")
        or movement not in MOVEMENTS
    ):
        raise ValueError("unsupported DIY design type or movement")
    if any(type(v) is not int or not 0 <= v <= 100 for v in (speed, brightness)):
        raise ValueError("speed and brightness must be integer percentages 0..100")
    if kind == "animation":
        if movement not in ("blink", "breathe"):
            raise ValueError("two-picture playback supports blink or breathe")
        direction = int(movement == "breathe")
        return [
            build_packet(0xD0, [direction, brightness, speed, 2]),
            build_packet(0xDC, [direction]),
        ]
    return [build_packet(0xD0, [MOVEMENTS[movement], brightness, speed, 1])]


def decode_status(data: bytes, *, scene_divisor: int = 1) -> dict | None:
    """GetDeviceStatusCmd only; never interpret ACKs or firmware as pixels/state."""
    if (
        len(data) < 9
        or data[:2] != b"\xaa\x01"
        or data[2] != len(data) - 4
        or sum(data[:-1]) & 255 != data[-1]
    ):
        return None
    p = data[3:-1]
    if p[3] not in (0, 1):
        return None
    mode = p[4]
    if mode == 1 and len(p) < 11 or mode == 2 and len(p) < 8:
        return None
    report = {
        "source": "device_notification",
        "power": bool(p[3]),
        "mode": mode,
        "countdown_seconds": int.from_bytes(p[:3], "big"),
        "raw": data.hex(),
    }
    if mode == 1:
        # Notification bytes 8-9: hue (0-359).
        # Bytes 10-11: saturation; bytes 12-13: brightness (0-1000).
        # Scale saturation/brightness to percent when presenting device state.
        h, s, v = (int.from_bytes(p[i : i + 2], "big") for i in (5, 7, 9))
        report.update(hue=h, saturation_raw=s, brightness_raw=v)
        if 0 <= v <= 1000:
            report["brightness_percent"] = v / 10
    elif mode == 2:
        value = int.from_bytes(p[6:8], "big")
        report.update(scene=p[5], brightness_raw=value)
        # SceneMode.handleBytes multiplies wire value by 10, then /10 for percent.
        if 0 <= value <= 100 * scene_divisor:
            report["brightness_percent"] = value / scene_divisor
    return report


def decode_device_info(data: bytes) -> dict | None:
    """APK GetDeviceInfoCmd offsets; reject unknown/truncated responses."""
    if (
        len(data) < 31
        or data[:2] != b"\xaa\x00"
        or data[2] != len(data) - 4
        or sum(data[:-1]) & 255 != data[-1]
    ):
        return None
    payload = data[3:-1]
    try:
        firmware = payload[:5].decode("ascii")
        model = payload[5:20].split(b"\x00", 1)[0].decode("ascii")
    except UnicodeDecodeError:
        return None
    return {
        "firmware": firmware,
        "model": model,
        "led_count": int.from_bytes(payload[20:22], "big"),
        "columns": payload[22],
        "rows": payload[24],
        "diy_type": payload[26],
    }
