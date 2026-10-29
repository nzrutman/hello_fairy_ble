"""APK-derived framing and strict native-effect notification validation.

Generated with aurora@aurora-smart-home (ha-integration-dev skill)
https://github.com/tonylofgren/aurora-smart-home
"""

import pytest

from custom_components.hello_fairy_ble.native_effects import (
    build_music_command,
    build_scene_speed_command,
    build_scene_speed_query,
    decode_music_status,
    decode_scene_speed,
)
from custom_components.hello_fairy_ble.pixel_protocol import build_packet


def test_native_music_exact_wire_bytes_and_forced_auto():
    # 03 music; mode 2 manual; sensitivity 50; 100%=1000; hue360; saturation25%=250.
    command = build_music_command(2, 50, 100, 360, 25, False)
    assert command[:12] == bytes.fromhex("aa030903203203e8016800fa")
    assert command[-1] == sum(command[:-1]) & 255
    assert build_music_command(1, 50, 100, 0, 100, False)[4] == 0x11


@pytest.mark.parametrize(
    "position,value",
    [
        (0, 0),
        (0, 5),
        (0, True),
        (1, 0),
        (1, 101),
        (2, 0),
        (2, 101),
        (3, -1),
        (3, 361),
        (4, 101),
        (4, 1.0),
        (5, 1),
    ],
)
def test_music_invalid_fields_fail_before_transport(position, value):
    fields = [2, 50, 100, 0, 100, False]
    fields[position] = value
    with pytest.raises(ValueError):
        build_music_command(*fields)


def test_scene_speed_query_and_exact_reply():
    assert build_scene_speed_query() == bytes.fromhex("aa0c00b6")
    assert build_scene_speed_command(100) == bytes.fromhex("aa0c01641b")
    assert decode_scene_speed(build_packet(0x0C, [0])) == 0
    assert decode_scene_speed(build_packet(0x0C, [100])) == 100


@pytest.mark.parametrize("speed", [-1, 101, True, 5.0, None])
def test_bad_scene_speed(speed):
    with pytest.raises(ValueError):
        build_scene_speed_command(speed)


@pytest.mark.parametrize(
    "data",
    [
        b"",
        b"\xaa\x0c\x01\x64\x00",
        build_packet(0x0C, []),
        build_packet(0x0C, [101]),
        build_packet(0x0C, [50, 0]),
        build_packet(0x03, [50]),
    ],
)
def test_scene_speed_never_confuses_ack_malformed_other_command(data):
    assert decode_scene_speed(data) is None


def test_music_readback_preserves_device_values_and_distinguishes_phone():
    music = bytes.fromhex("21500320007803e8")
    report = decode_music_status(build_packet(1, bytes([0, 0, 0, 1, 3]) + music))
    assert report == {
        "music_mode": 2,
        "microphone": "device",
        "auto_color": True,
        "sensitivity": 80,
        "brightness_raw": 800,
        "brightness_percent": 80,
        "hue": 120,
        "saturation_raw": 1000,
    }
    phone = bytes([0x61]) + music[1:]
    report = decode_music_status(build_packet(1, bytes([0, 0, 0, 1, 3]) + phone))
    assert report["microphone"] == "phone"


@pytest.mark.parametrize(
    "music",
    [
        "01500320007803e8",
        "22500320007803e8",
        "21ff0320007803e8",
        "2150ffff007803e8",
        "21500320ffff03e8",
        "215003200078ffff",
    ],
)
def test_bad_music_status_rejected(music):
    assert (
        decode_music_status(build_packet(1, bytes([0, 0, 0, 1, 3]) + bytes.fromhex(music))) is None
    )


def test_music_status_exact_length_checksum_and_status_type():
    music = bytes.fromhex("21500320007803e8")
    packet = build_packet(1, bytes([0, 0, 0, 1, 3]) + music)
    assert decode_music_status(packet[:-1]) is None
    assert decode_music_status(packet[:-1] + bytes([packet[-1] ^ 1])) is None
    assert decode_music_status(build_packet(3, packet[3:-1])) is None
    assert decode_music_status(build_packet(1, packet[3:-1] + b"\x00")) is None
