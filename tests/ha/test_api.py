"""Public regression tests against real HA and Bleak imports (ha-integration-dev skill).
https://github.com/tonylofgren/aurora-smart-home
"""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from bleak import BleakError

from custom_components.hello_fairy_ble.diy_controls import decode_device_info, decode_status
from custom_components.hello_fairy_ble.pixel_protocol import build_packet, validate_color_byte

from .conftest import CAPABILITIES, INFO_PACKET, STATUS_PACKET


@pytest.mark.parametrize(
    "method,args,initial_power,expected",
    [
        ("set_power", (True,), False, "aa020101ae"),
        ("set_power", (False,), True, "aa020100ad"),
        ("set_color_hsv", (120, 100, 50), True, "aa030701007803e801f40d"),
        ("set_preset", (3,), True, "aa0304020301f4ab"),
    ],
)
async def test_existing_controls_keep_wire_commands(
    api, client, method, args, initial_power, expected
):
    api.state = initial_power
    api.brightness = 50
    await getattr(api, method)(*args)
    client.write_gatt_char.assert_awaited_once()
    call = client.write_gatt_char.await_args
    assert call.args[1] == bytes.fromhex(expected)
    assert call.kwargs["response"] is False


@pytest.mark.parametrize("raw,percent", [(0, 0), (25, 25), (100, 100)])
async def test_curtain_brightness_uses_one_decoder(api, verified, raw, percent):
    packet = build_packet(1, [0, 0, 0, 1, 2, 201, raw >> 8, raw & 255])
    await api._handle_notification(None, bytearray(packet))
    assert api.brightness == percent
    assert api.studio_snapshot["reported"]["brightness_percent"] == percent


async def test_legacy_brightness_stays_compatible(api, client):
    packet = build_packet(1, [0, 0, 0, 1, 2, 10, 1, 244])  # legacy raw 500 -> 50%
    await api._handle_notification(None, bytearray(packet))
    assert api.brightness == 50
    assert api.studio_snapshot["reported"]["brightness_percent"] == 50


async def test_info_packet_is_not_power_status(api, client):
    api.state = True
    await api._handle_notification(None, bytearray(INFO_PACKET))
    assert api.state is True
    assert api.studio_snapshot["reported"] is None
    assert api.studio_snapshot["diy_supported"] is True
    assert not api._status_event.is_set()


@pytest.mark.parametrize(
    "changes", [{"led_count": 900}, {"columns": 30}, {"rows": 30}, {"diy_type": 6}]
)
async def test_unsupported_device_never_gets_diy_or_power(api, client, changes):
    api._device_info = {**CAPABILITIES, **changes}
    api._info_client = client
    with pytest.raises(RuntimeError, match="DIY blocked"):
        await api.set_frame([0] * 400)
    client.write_gatt_char.assert_not_awaited()


async def test_fresh_capability_query_is_read_only(api, client):
    await api._verify_diy_device_locked()
    assert client.write_gatt_char.await_args.args[1] == bytes.fromhex("aa0000aa")
    assert api._device_info == CAPABILITIES


async def test_capabilities_missing_fail_before_diy(api, client):
    client.write_gatt_char.side_effect = None
    original = asyncio.wait_for
    with patch(
        "custom_components.hello_fairy_ble.api.asyncio.wait_for",
        lambda coro, timeout: original(coro, timeout=0.001),
    ):
        with pytest.raises(RuntimeError, match="capabilities"):
            await api._verify_diy_device_locked()
    assert [c.args[1][1] for c in client.write_gatt_char.await_args_list] == [0]


async def test_mtu_rejection_no_device_writes(api, verified):
    verified.mtu_size = 23
    with pytest.raises(RuntimeError, match="blocked before D0/DA"):
        await api.set_frame([0] * 400)
    verified.write_gatt_char.assert_not_awaited()


async def test_static_and_two_picture_sequences_are_preserved(api, verified):
    with patch("custom_components.hello_fairy_ble.api.asyncio.sleep", AsyncMock()):
        await api.set_frame([0] * 400)
        first = [c.args[1] for c in verified.write_gatt_char.await_args_list]
        verified.write_gatt_char.reset_mock()
        await api.set_two_picture_animation([[164] * 400, [60] * 400])
    assert [p[1] for p in first] == [208, 208] + [218] * 6 + [208, 208]
    assert [len(p) for p in first if p[1] == 218] == [242] * 5 + [20]
    packets = [c.args[1] for c in verified.write_gatt_char.await_args_list]
    assert len(packets) == 20
    assert [p[3] for p in packets if p[1] == 218] == [1] * 6 + [2] * 6
    assert api.studio_snapshot["last_upload"]["source"] == "last_upload"
    assert api.studio_snapshot["pixel_readback"] is False


async def test_partial_frame_no_reconnect_or_finalization(api, verified):
    async def write(uuid, packet, response):
        if packet[1] == 218:
            raise BleakError("radio failed")

    verified.write_gatt_char.side_effect = write
    with (
        patch("custom_components.hello_fairy_ble.api.asyncio.sleep", AsyncMock()),
        patch("bleak_retry_connector.establish_connection", AsyncMock()) as connect,
    ):
        with pytest.raises(BleakError):
            await api.set_frame([0] * 400)
    connect.assert_not_awaited()
    assert [c.args[1][1] for c in verified.write_gatt_char.await_args_list] == [208, 208, 218]
    assert api.studio_snapshot["last_upload"] is None


async def test_native_settings_do_not_upload_frames(api, verified):
    api._last_upload = {"kind": "animation"}
    with patch("custom_components.hello_fairy_ble.api.asyncio.sleep", AsyncMock()):
        await api.set_diy_playback("animation", "breathe", 30, 75)
    assert [c.args[1].hex() for c in verified.write_gatt_char.await_args_list] == [
        "aad004014b1e02ea",
        "aadc010188",
    ]


async def test_status_query_reports_fresh_received_state(api, verified):
    report = await api.request_status()
    assert report["brightness_percent"] == 100
    assert api.brightness == 100
    assert report["source"] == "device_notification"
    assert verified.write_gatt_char.await_args.args[1] == bytes.fromhex("aa0100ab")


async def test_notify_retry_cleans_before_replacement(api, client):
    api._client = None
    bad, good = client, type("Good", (), {})()
    good.start_notify = AsyncMock()
    good.is_connected = True
    bad.start_notify.side_effect = BleakError("handle=12 error=133")

    async def acquire(*args, **kwargs):
        if establish.await_count == 2:
            bad.disconnect.assert_awaited_once()
            assert not bad.is_connected
            return good
        return bad

    with (
        patch(
            "bleak_retry_connector.establish_connection", AsyncMock(side_effect=acquire)
        ) as establish,
        patch("custom_components.hello_fairy_ble.api.asyncio.sleep", AsyncMock()),
    ):
        await api._connect()
    assert establish.await_count == 2
    assert api._client is good
    bad.write_gatt_char.assert_not_awaited()


async def test_three_setup_failures_stop_without_writes(api, client):
    api._client = None
    client.start_notify.side_effect = BleakError("error=133")
    with (
        patch(
            "bleak_retry_connector.establish_connection", AsyncMock(return_value=client)
        ) as establish,
        patch("custom_components.hello_fairy_ble.api.asyncio.sleep", AsyncMock()),
    ):
        with pytest.raises(ConnectionError, match="3 attempts"):
            await api._connect()
    assert establish.await_count == 3
    client.write_gatt_char.assert_not_awaited()


@pytest.mark.parametrize("color", [True, 1.5, "2", -1, 181, 253, 256])
def test_invalid_raw_colors_rejected(color):
    with pytest.raises(ValueError):
        validate_color_byte(color)


@pytest.mark.parametrize("packet", [b"", INFO_PACKET[:-1], INFO_PACKET[:-1] + b"\x00"])
def test_malformed_capabilities_rejected(packet):
    assert decode_device_info(packet) is None


def test_captured_profile_and_status_vectors():
    assert decode_device_info(INFO_PACKET) == CAPABILITIES
    assert decode_status(STATUS_PACKET)["brightness_percent"] == 100
