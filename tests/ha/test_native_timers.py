"""Native timer framing, strict readback and timezone rollover regression tests.

Generated with aurora@aurora-smart-home (ha-integration-dev skill)
https://github.com/tonylofgren/aurora-smart-home
"""

import pytest

from custom_components.hello_fairy_ble.native_timers import (
    build_clock_sync,
    build_countdown,
    build_timer_query,
    build_timer_write,
    decode_countdown,
    decode_timer_bank,
    local_timer,
)
from custom_components.hello_fairy_ble.pixel_protocol import build_packet


def test_clock_matches_original_android_capture_record_494():
    assert build_clock_sync(0x6ACF985B, 180).hex() == "aa05076acf985b0100b497"
    assert build_clock_sync(0x6ACF985B, -330)[7:10] == bytes((0, 1, 74))
    assert build_clock_sync(0x6ACF985B, 0)[7:10] == bytes((1, 0, 0))


@pytest.mark.parametrize("timestamp,offset", [(True, 180), (-1, 0), (2**31, 0), (0, 841), (0, 1.5)])
def test_clock_rejects_unsupported_fields(timestamp, offset):
    with pytest.raises(ValueError):
        build_clock_sync(timestamp, offset)


def test_countdown_target_and_cancellation():
    assert build_countdown(3600, False) == build_packet(4, [0, 0, 14, 16, 0])
    assert build_countdown(0, True) == build_packet(4, [0, 0, 0, 0, 1])
    assert decode_countdown(build_countdown(86400, True)) == {
        "countdown_seconds": 86400,
        "power": True,
    }
    assert decode_countdown(build_packet(4, [0, 0, 0, 10])) == {"countdown_seconds": 10}
    assert decode_countdown(build_packet(4, [0, 0, 0, 10, 2])) is None
    assert decode_countdown(build_packet(4, [0, 0, 0, 10])[:-1] + b"\x00") is None


@pytest.mark.parametrize("seconds,power", [(True, True), (-1, False), (86401, False), (1, 1)])
def test_countdown_rejects_invalid_fields(seconds, power):
    with pytest.raises(ValueError):
        build_countdown(seconds, power)


def test_timer_bank_read_requires_complete_valid_reply():
    assert build_timer_query(1).hex() == "aa0600b0"
    assert build_timer_query(2).hex() == "aa0700b1"
    reply = build_packet(7, [3, 18, 0, 0x4B, 0, 0, 0, 0x50, 0, 0, 0, 0x60, 0, 0, 0, 0x70])
    timers = decode_timer_bank(reply)
    assert timers[0] == {
        "slot": 4,
        "number": 4,
        "hour": 18,
        "minute": 0,
        "weekdays": [1],
        "repeat": True,
        "power": True,
        "enabled": True,
        "exists": True,
        "executed": False,
    }
    assert (
        decode_timer_bank(
            build_timer_write(
                slot=4,
                hour=18,
                minute=0,
                power=True,
                enabled=True,
                weekdays=[1],
                utc_offset_minutes=480,
            )
        )
        is None
    )
    assert decode_timer_bank(reply[:-1]) is None
    assert decode_timer_bank(reply[:-1] + bytes((reply[-1] ^ 1,))) is None
    assert decode_timer_bank(build_packet(6, [0, 24, 0, 8] * 4)) is None
    assert decode_timer_bank(build_packet(6, [0, 0, 60, 8] * 4)) is None
    assert decode_timer_bank(build_packet(6, [0, 0, 0, 4] * 4)) is None


def test_timer_local_sunday_rolls_forward_to_monday_on_wire():
    packet = build_timer_write(
        slot=7, hour=23, minute=30, power=False, enabled=True, weekdays=[7], utc_offset_minutes=180
    )
    assert packet == build_packet(6, [3, 4, 30, 0x7A])
    bank = decode_timer_bank(build_packet(7, list(packet[3:7]) * 4))
    local = local_timer(bank[0], 180)
    assert (local["hour"], local["minute"], local["weekdays"]) == (23, 30, [7])
    assert bank[0]["hour"] == 4


def test_timer_fractional_offset_and_backward_weekday_rollover():
    packet = build_timer_write(
        slot=2,
        hour=1,
        minute=15,
        power=True,
        enabled=False,
        weekdays=[1, 3],
        utc_offset_minutes=840,
    )
    assert packet == build_packet(6, [0x85, 19, 15, 0x29])
    packet = build_timer_write(
        slot=1, hour=21, minute=45, power=True, enabled=True, weekdays=[6], utc_offset_minutes=345
    )
    assert packet[3:7] == bytes((129, 0, 0, 0x1B))
    packet = build_timer_write(
        slot=0, hour=0, minute=0, power=False, enabled=False, weekdays=[], utc_offset_minutes=-210
    )
    assert packet[3:7] == bytes((0, 11, 30, 8))


@pytest.mark.parametrize(
    "field,value",
    [
        ("slot", 8),
        ("slot", True),
        ("hour", 24),
        ("minute", -1),
        ("power", 1),
        ("enabled", "yes"),
        ("weekdays", [0]),
        ("weekdays", [1, 1]),
        ("weekdays", [True]),
        ("utc_offset_minutes", -841),
    ],
)
def test_timer_write_rejects_invalid_fields(field, value):
    kwargs = dict(
        slot=0, hour=18, minute=30, power=True, enabled=True, weekdays=[1], utc_offset_minutes=180
    )
    kwargs[field] = value
    with pytest.raises(ValueError):
        build_timer_write(**kwargs)
