"""Explicit native timing commands decoded from official Hello Fairy Android APK.

Generated with aurora@aurora-smart-home (ha-integration-dev skill)
https://github.com/tonylofgren/aurora-smart-home

The caller must gate the exact verified device profile and obtain both timer
banks before editing. Native schedule times use UTC+08, as in APK pd4.E/D.
These helpers never send commands or schedule automatic clock synchronization.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from .pixel_protocol import build_packet

MAX_COUNTDOWN_SECONDS = 86400


def _integer(value: int, low: int, high: int, name: str) -> int:
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f"{name} must be an integer {low}..{high}")
    return value


def _boolean(value: bool, name: str) -> bool:
    if type(value) is not bool:
        raise ValueError(f"{name} must be a boolean")
    return value


def _offset(value: int) -> int:
    return _integer(value, -840, 840, "UTC offset minutes")


def _payload(packet: bytes, command: int, length: int) -> bytes | None:
    if (
        not isinstance(packet, bytes | bytearray)
        or len(packet) != length + 4
        or packet[:3] != bytes((0xAA, command, length))
        or sum(packet[:-1]) & 255 != packet[-1]
    ):
        return None
    return bytes(packet[3:-1])


def build_clock_sync(timestamp: int, utc_offset_minutes: int) -> bytes:
    """Cmd05: UTC Unix seconds BE4, positive flag, absolute offset BE2 minutes.

    The captured device echoed this command. Clock persistence and future DST
    handling remain unconfirmed; synchronize explicitly, never on every upload.
    """
    _integer(timestamp, 0, 0x7FFFFFFF, "timestamp")
    _offset(utc_offset_minutes)
    return build_packet(
        5,
        timestamp.to_bytes(4, "big")
        + bytes((int(utc_offset_minutes >= 0),))
        + abs(utc_offset_minutes).to_bytes(2, "big"),
    )


def build_countdown(seconds: int, power: bool) -> bytes:
    """Cmd04: seconds BE4 + target power. Zero cancels the pending countdown."""
    _integer(seconds, 0, MAX_COUNTDOWN_SECONDS, "seconds")
    _boolean(power, "power")
    return build_packet(4, seconds.to_bytes(4, "big") + bytes((int(power),)))


def decode_countdown(packet: bytes) -> dict | None:
    """Decode cmd04 echo/reply, without claiming a live ticking measurement."""
    data = _payload(packet, 4, 4)
    if data is None:
        data = _payload(packet, 4, 5)
    if data is None or len(data) == 5 and data[4] not in (0, 1):
        return None
    result = {"countdown_seconds": int.from_bytes(data[:4], "big")}
    if len(data) == 5:
        result["power"] = bool(data[4])
    return result


def build_timer_query(bank: int) -> bytes:
    """Read slots 0..3 (bank1/cmd06) or 4..7 (bank2/cmd07)."""
    _integer(bank, 1, 2, "bank")
    return build_packet(5 + bank, [])


def decode_timer_bank(packet: bytes) -> list[dict] | None:
    """Decode only a complete valid bank reply; never accept write echoes.

    ``slot`` is the bank position; ``number`` is the actual encoded slot. The
    caller must refuse editing an existing slot whose encoded number differs.
    """
    if not isinstance(packet, bytes | bytearray) or len(packet) < 2 or packet[1] not in (6, 7):
        return None
    data = _payload(packet, packet[1], 16)
    if data is None:
        return None
    timers = []
    for index in range(4):
        days, hour, minute, flags = data[index * 4 : index * 4 + 4]
        if hour > 23 or minute > 59 or flags & 4:
            return None
        repeat = bool(days & 1)
        weekdays = [day for day in range(1, 8) if days & (1 << day)]
        if repeat != bool(weekdays):
            return None
        timers.append(
            {
                "slot": (packet[1] - 6) * 4 + index,
                "number": (flags >> 4) & 7,
                "hour": hour,
                "minute": minute,
                "weekdays": weekdays,
                "repeat": repeat,
                "power": bool(flags & 1),
                "enabled": bool(flags & 2),
                "exists": bool(flags & 8),
                "executed": bool(flags & 128),
            }
        )
    return timers


def _shift(
    hour: int, minute: int, weekdays: Sequence[int], delta: int
) -> tuple[int, int, list[int]]:
    day_delta, minutes = divmod(hour * 60 + minute + delta, 1440)
    return minutes // 60, minutes % 60, sorted({(day - 1 + day_delta) % 7 + 1 for day in weekdays})


def _weekdays(values: Sequence[int]) -> list[int]:
    if not isinstance(values, list | tuple) or len(values) > 7:
        raise ValueError("weekdays must be a list of unique days 1 (Monday)..7 (Sunday)")
    days = [_integer(day, 1, 7, "weekday") for day in values]
    if len(set(days)) != len(days):
        raise ValueError("weekdays must not contain duplicates")
    return days


def build_timer_write(
    *,
    slot: int,
    hour: int,
    minute: int,
    power: bool,
    enabled: bool,
    weekdays: Sequence[int],
    utc_offset_minutes: int,
) -> bytes:
    """Replace exactly one slot using cmd06, retaining every other device slot.

    APK LightTimer uses ISO weekdays (Monday=1). Empty weekdays means one-shot.
    Conversion fixes the current UTC offset; reapply after local DST changes.
    ``executed`` is cleared for a new setting; ``exists`` is always set.
    """
    _integer(slot, 0, 7, "slot")
    _integer(hour, 0, 23, "hour")
    _integer(minute, 0, 59, "minute")
    _boolean(power, "power")
    _boolean(enabled, "enabled")
    days = _weekdays(weekdays)
    _offset(utc_offset_minutes)
    wire_hour, wire_minute, wire_days = _shift(hour, minute, days, 480 - utc_offset_minutes)
    day_mask = int(bool(wire_days)) | sum(1 << day for day in wire_days)
    flags = int(power) | int(enabled) << 1 | 8 | slot << 4
    return build_packet(6, [day_mask, wire_hour, wire_minute, flags])


def local_timer(timer: Mapping, utc_offset_minutes: int) -> dict:
    """Return a copy with current-local time/weekdays; wire data stays immutable."""
    _offset(utc_offset_minutes)
    hour = _integer(timer.get("hour"), 0, 23, "hour")
    minute = _integer(timer.get("minute"), 0, 59, "minute")
    days = _weekdays(timer.get("weekdays"))
    hour, minute, days = _shift(hour, minute, days, utc_offset_minutes - 480)
    return {**timer, "hour": hour, "minute": minute, "weekdays": days}
