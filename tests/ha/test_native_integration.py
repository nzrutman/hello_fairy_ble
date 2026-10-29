"""Native capabilities and actions against the real HA websocket/service boundary.

Generated with aurora@aurora-smart-home (ha-integration-dev skill)
https://github.com/tonylofgren/aurora-smart-home
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest
import voluptuous as vol
from bleak import BleakError
from homeassistant.exceptions import HomeAssistantError
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.hello_fairy_ble import RuntimeData
from custom_components.hello_fairy_ble.const import DOMAIN
from custom_components.hello_fairy_ble.native_capabilities import decode_extensions
from custom_components.hello_fairy_ble.native_service import async_setup_native, perform_native
from custom_components.hello_fairy_ble.pixel_protocol import build_packet

from .conftest import ADDRESS, CAPABILITIES, INFO_PACKET, STATUS_PACKET

MUSIC = {
    "mode": 2,
    "auto_color": False,
    "sensitivity": 50,
    "brightness": 80,
    "hue": 120,
    "saturation": 100,
}
MUSIC_STATUS = build_packet(1, bytes([0, 0, 0, 1, 3]) + bytes.fromhex("20320320007803e8"))


def entry_with_native(hass):
    entry = MockConfigEntry(
        domain=DOMAIN, title="Curtain", unique_id=ADDRESS, data={"address": ADDRESS}
    )
    entry.add_to_hass(hass)
    coordinator = SimpleNamespace(
        device_address=ADDRESS,
        studio_snapshot={"native": {"music_supported": True}},
        inspect_native=AsyncMock(),
        set_native=AsyncMock(return_value={"sent": True}),
    )
    entry.runtime_data = RuntimeData(coordinator, Mock())
    return coordinator


async def test_native_registration_never_discovers_or_sends(hass):
    coordinator = entry_with_native(hass)
    await async_setup_native(hass)
    coordinator.inspect_native.assert_not_awaited()
    coordinator.set_native.assert_not_awaited()


@pytest.mark.parametrize("admin", [True, False])
async def test_native_websocket_admin_boundary(
    hass,
    hass_ws_client,
    hass_read_only_access_token,
    admin,
):
    assert await async_setup_component(hass, "http", {})
    coordinator = entry_with_native(hass)
    await async_setup_native(hass)
    kwargs = {} if admin else {"access_token": hass_read_only_access_token}
    ws = await hass_ws_client(hass, **kwargs)
    await ws.send_json_auto_id(
        {"type": f"{DOMAIN}/studio/native", "address": ADDRESS, "action": "inspect"}
    )
    result = await ws.receive_json()
    assert result["success"] is admin
    if admin:
        coordinator.inspect_native.assert_awaited_once()
        assert result["result"] == coordinator.studio_snapshot
    else:
        assert result["error"]["code"] == "unauthorized"
        coordinator.inspect_native.assert_not_awaited()


async def test_native_websocket_ble_failure_is_structured_and_not_retried(hass, hass_ws_client):
    assert await async_setup_component(hass, "http", {})
    coordinator = entry_with_native(hass)
    coordinator.set_native.side_effect = BleakError("Bluetooth GATT Error handle=12 error=133")
    await async_setup_native(hass)
    ws = await hass_ws_client(hass)
    with patch("custom_components.hello_fairy_ble.native_service.async_stop_playlist", AsyncMock()):
        await ws.send_json_auto_id(
            {
                "type": f"{DOMAIN}/studio/native",
                "address": ADDRESS,
                "action": "music",
                "payload": MUSIC,
            }
        )
        result = await ws.receive_json()
    assert result["success"] is False
    assert result["error"] == {
        "code": "native_failed",
        "message": "Bluetooth GATT Error handle=12 error=133",
    }
    coordinator.set_native.assert_awaited_once()
    coordinator.inspect_native.assert_not_awaited()


async def test_native_service_ble_failure_becomes_ha_error_without_retry(hass):
    coordinator = entry_with_native(hass)
    coordinator.set_native.side_effect = BleakError("Bluetooth GATT Error handle=12 error=133")
    await async_setup_native(hass)
    with patch("custom_components.hello_fairy_ble.native_service.async_stop_playlist", AsyncMock()):
        with pytest.raises(HomeAssistantError, match="Bluetooth GATT Error handle=12 error=133"):
            await hass.services.async_call(
                DOMAIN,
                "native_control",
                {
                    "address": ADDRESS,
                    "action": "music",
                    "payload": MUSIC,
                },
                blocking=True,
            )
    coordinator.set_native.assert_awaited_once()
    coordinator.inspect_native.assert_not_awaited()


@pytest.mark.parametrize(
    "action,payload",
    [
        ("music", {**MUSIC, "mode": True}),
        ("music", {**MUSIC, "mode": 5}),
        ("music", {**MUSIC, "sensitivity": 0}),
        ("music", {**MUSIC, "brightness": 0}),
        ("music", {**MUSIC, "unknown": True}),
        ("scene_speed", {"speed": 101}),
        ("scene_speed", {"speed": True}),
        ("unsupported", {}),
    ],
)
async def test_native_invalid_service_input_before_stop_or_transport(hass, action, payload):
    coordinator = entry_with_native(hass)
    with patch(
        "custom_components.hello_fairy_ble.native_service.async_stop_playlist", AsyncMock()
    ) as stop:
        with pytest.raises((ValueError, vol.Invalid)):
            await perform_native(hass, ADDRESS, action, payload)
    stop.assert_not_awaited()
    coordinator.inspect_native.assert_not_awaited()
    coordinator.set_native.assert_not_awaited()


def test_captured_music_capability_and_absent_loop():
    assert decode_extensions(INFO_PACKET) == {"music_mode": 3}


@pytest.mark.parametrize(
    "extensions,count",
    [
        ([8], 1),
        ([8, 3, 255], 2),
        ([8, 3, 7], 1),
        ([8, 3], 2),
        ([11, 4, 1, 2], 1),
        ([8, 3, 10, 1, 2], 2),
    ],
)
def test_extension_list_unknown_truncated_trailing_fails_closed(extensions, count):
    payload = bytearray(INFO_PACKET[3:-1][:28])
    payload[27] = count
    assert decode_extensions(build_packet(0, payload + bytes(extensions))) == {}


async def test_native_wrong_profile_only_safe_info_allowed(api, client):
    api._device_info = {**CAPABILITIES, "firmware": "9.9.9"}
    api._info_client = client
    api._native_client = client
    with pytest.raises(ValueError, match="profile"):
        await api.inspect_native()
    client.write_gatt_char.assert_not_awaited()


async def test_direct_native_api_validation_precedes_connection(api, client):
    with patch.object(api, "_ensure_connected", AsyncMock()) as connect:
        with pytest.raises((ValueError, vol.Invalid)):
            await api.set_native("music", {**MUSIC, "mode": True})
    connect.assert_not_awaited()
    client.write_gatt_char.assert_not_awaited()


async def test_unadvertised_music_blocked_and_legacy_power_kept(api, verified):
    api._native_client = verified
    with pytest.raises(ValueError, match="music|Music|advertis|support"):
        await api.set_native("music", MUSIC)
    verified.write_gatt_char.assert_not_awaited()
    api.state = False
    await api.set_power(True)
    assert verified.write_gatt_char.await_args.args[1] == bytes.fromhex("aa020101ae")


async def test_music_ack_then_fresh_status_one_command(api, client):
    packets = []

    async def write(uuid, packet, response):
        packets.append(packet)
        reply = {0: INFO_PACKET, 1: MUSIC_STATUS, 3: build_packet(3, [])}.get(packet[1])
        if reply:
            await api._handle_notification(None, bytearray(reply))

    client.write_gatt_char.side_effect = write
    result = await api.set_native("music", MUSIC)
    assert [p[1] for p in packets] == [0, 3, 1]
    assert result["reported"]["microphone"] == "device"
    assert result["reported"]["music_mode"] == 2
    assert result["native"]["last_command"]["source"] == "last_command"
    assert all(len(p) <= 20 for p in packets)


async def test_music_write_failure_not_replayed(api, client):
    await api._handle_notification(None, bytearray(INFO_PACKET))
    client.write_gatt_char.side_effect = BleakError("radio failed")
    with patch("bleak_retry_connector.establish_connection", AsyncMock()) as connect:
        with pytest.raises(BleakError):
            await api.set_native("music", MUSIC)
    assert client.write_gatt_char.await_count == 1
    connect.assert_not_awaited()


async def test_wrong_music_mode_readback_not_success_or_replayed(api, client):
    await api._handle_notification(None, bytearray(INFO_PACKET))

    async def write(uuid, packet, response):
        if packet[1] == 3:
            await api._handle_notification(None, bytearray(build_packet(3, [])))
        elif packet[1] == 1:
            # Valid music status from another selected mode is not confirmation.
            wrong = bytearray(MUSIC_STATUS[3:-1])
            wrong[5] = 0x30
            await api._handle_notification(None, bytearray(build_packet(1, wrong)))

    client.write_gatt_char.side_effect = write
    with pytest.raises(ValueError, match="music|Music|readback|report"):
        await api.set_native("music", MUSIC)
    assert [c.args[1][1] for c in client.write_gatt_char.await_args_list] == [3, 1]


async def test_scene_speed_requires_query_reply_then_reads_back(api, client):
    await api._handle_notification(None, bytearray(INFO_PACKET))
    with pytest.raises(ValueError, match="speed|Speed|inspect|discover"):
        await api.set_native("scene_speed", {"speed": 70})
    client.write_gatt_char.assert_not_awaited()
    speed = 50

    async def write(uuid, packet, response):
        nonlocal speed
        if packet[1] == 1:
            scene = bytearray(STATUS_PACKET[3:-1])
            scene[5] = 41
            await api._handle_notification(None, bytearray(build_packet(1, scene)))
        if packet[1] == 12:
            if packet[2]:
                speed = packet[3]
            else:
                await api._handle_notification(None, bytearray(build_packet(12, [speed])))

    client.write_gatt_char.side_effect = write
    original = asyncio.wait_for
    with patch(
        "custom_components.hello_fairy_ble.native.asyncio.wait_for",
        lambda coro, timeout: original(coro, timeout=0.001),
    ):
        snapshot = await api.inspect_native()
    assert snapshot["native"]["scene_speed_supported"] is True
    result = await api.set_native("scene_speed", {"speed": 70})
    assert result["native"]["scene_speed"] == 70
    assert [
        c.args[1].hex() for c in client.write_gatt_char.await_args_list if c.args[1][1] in (1, 12)
    ] == [
        "aa0c00b6",
        "aa0100ab",
        "aa0c0146fd",
        "aa0c00b6",
    ]


async def test_speed_ignores_unsolicited_reply_and_resets_at_disconnect(api, client):
    await api._handle_notification(None, bytearray(INFO_PACKET))
    await api._handle_notification(None, bytearray(build_packet(12, [50])))
    assert api.studio_snapshot["native"]["scene_speed_supported"] is False
    api._native_speed = 50
    assert api.studio_snapshot["native"]["music_supported"] is True
    await api.disconnect()
    snapshot = api.studio_snapshot["native"]
    assert snapshot["music_supported"] is False
    assert snapshot["scene_speed_supported"] is False
    assert api._native_extensions == {}


async def test_previous_connection_notification_cannot_grant_current_capability(api, client):
    replacement = SimpleNamespace(
        is_connected=True,
        start_notify=AsyncMock(),
        disconnect=AsyncMock(),
    )
    api._client = None
    with patch(
        "bleak_retry_connector.establish_connection", AsyncMock(side_effect=[client, replacement])
    ):
        await api._connect_once()
        old_callback = client.start_notify.await_args.args[1]
        await api._connect_once()
        current_callback = replacement.start_notify.await_args.args[1]
    await old_callback(None, bytearray(INFO_PACKET))
    assert api._info_client is None
    assert api.studio_snapshot["native"]["music_supported"] is False
    await current_callback(None, bytearray(INFO_PACKET))
    assert api._info_client is replacement
    assert api.studio_snapshot["native"]["music_supported"] is True


async def test_malformed_music_report_never_confirms_selection(api, client):
    await api._handle_notification(None, bytearray(INFO_PACKET))
    await api._handle_notification(None, bytearray(build_packet(1, [0, 0, 0, 1, 3])))
    assert not api._status_event.is_set()
    assert api.studio_snapshot["reported"] is None


async def test_scene_query_timeout_does_not_write_or_claim_support(api, client):
    await api._handle_notification(None, bytearray(INFO_PACKET))
    original = asyncio.wait_for
    with patch(
        "custom_components.hello_fairy_ble.native.asyncio.wait_for",
        lambda coro, timeout: original(coro, timeout=0.001),
    ):
        snapshot = await api.inspect_native()
    assert snapshot["native"]["scene_speed_supported"] is False
    # Other newly added read-only discovery may run as well; no speed setter.
    assert all(
        not (c.args[1][1] == 12 and c.args[1][2]) for c in client.write_gatt_char.await_args_list
    )


async def test_native_readback_timeout_explains_single_attempt(api, client):
    await api._handle_notification(None, bytearray(INFO_PACKET))

    async def write(uuid, packet, response):
        if packet[1] == 3:
            await api._handle_notification(None, bytearray(build_packet(3, [])))
        # ACK is delivered; fresh status intentionally never arrives.

    client.write_gatt_char.side_effect = write
    original = asyncio.wait_for
    with patch(
        "custom_components.hello_fairy_ble.native.asyncio.wait_for",
        lambda coro, timeout: original(coro, timeout=0.001),
    ):
        with pytest.raises(
            TimeoutError, match="did not return fresh status.*No command was retried"
        ):
            await api.set_native("music", MUSIC)
    assert [c.args[1][1] for c in client.write_gatt_char.await_args_list] == [3, 1]
    history = api.studio_snapshot["native"]["last_command"]
    assert history["readback_confirmed"] is False
