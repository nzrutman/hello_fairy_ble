"""Public regression tests against real HA and Bleak imports (ha-integration-dev skill).
https://github.com/tonylofgren/aurora-smart-home
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from bleak import BleakError
from bleak.backends.device import BLEDevice

from custom_components.hello_fairy_ble.api import (
    CACHE_REFRESH_SETTLE_DELAY,
    UNCACHED_CONNECT_TIMEOUT,
    HelloFairyAPI,
    HelloFairyConnectionPool,
)
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


def _make_bluez_client(api, *, acquired_mtu=512, acquire_exc=None):
    characteristic = SimpleNamespace(
        handle=9,
        properties=["write-without-response", "write"],
        max_write_without_response_size=509,
    )

    class Backend:
        def __init__(self):
            self._mtu_size = None

        async def _acquire(self):
            if acquire_exc is not None:
                raise acquire_exc
            self._mtu_size = acquired_mtu

    backend = Backend()
    backend._acquire_mtu = AsyncMock(side_effect=backend._acquire)

    class Client:
        def __init__(self):
            self.is_connected = True
            self._backend = backend
            self._connected_scanner = SimpleNamespace(source="local-hci0")
            self.services = SimpleNamespace(get_characteristic=lambda _: characteristic)
            self.clear_cache = AsyncMock(return_value=True)
            self.start_notify = AsyncMock()
            self.disconnect = AsyncMock(side_effect=self._disconnect)
            self.write_gatt_char = AsyncMock(side_effect=self._write)

        @property
        def mtu_size(self):
            return 23 if backend._mtu_size is None else backend._mtu_size

        async def _disconnect(self):
            self.is_connected = False

        async def _write(self, uuid, packet, response):
            if packet[:3] == b"\xaa\x00\x00":
                await api._handle_notification(None, bytearray(INFO_PACKET))

    return Client(), backend


async def test_bluez_acquire_mtu_unblocks_fresh_diy_and_caches_once(api):
    initial, _ = _make_bluez_client(api)
    fresh, fresh_backend = _make_bluez_client(api)
    api._client = initial
    api.state = True
    with (
        patch("bleak_retry_connector.establish_connection", AsyncMock(return_value=fresh)),
        patch("custom_components.hello_fairy_ble.api.asyncio.sleep", AsyncMock()),
    ):
        await api.set_frame([0] * 400)
        fresh_backend._acquire_mtu.assert_awaited_once()
        await api.set_frame([255] * 400)
    fresh_backend._acquire_mtu.assert_awaited_once()
    assert api.studio_snapshot["last_upload"]["frames"] == [[255] * 400]


async def test_bluez_acquire_mtu_reused_verified_client(api):
    bluez_client, backend = _make_bluez_client(api)
    api._client = bluez_client
    api.state = True
    api._verified_diy_client = bluez_client
    api._verified_diy_source = "local-hci0"
    api._info_client = bluez_client
    api._device_info = CAPABILITIES.copy()
    assert bluez_client.mtu_size == 23
    with patch("custom_components.hello_fairy_ble.api.asyncio.sleep", AsyncMock()):
        await api.set_frame([0] * 400)
    backend._acquire_mtu.assert_awaited_once()
    assert bluez_client.mtu_size == 512
    assert api.studio_snapshot["last_upload"]["kind"] == "picture"


async def test_bluez_acquire_mtu_low_real_mtu_still_blocks(api):
    bluez_client, backend = _make_bluez_client(api, acquired_mtu=23)
    api._client = bluez_client
    api.state = True
    api._verified_diy_client = bluez_client
    api._verified_diy_source = "local-hci0"
    api._info_client = bluez_client
    api._device_info = CAPABILITIES.copy()
    with pytest.raises(RuntimeError, match="blocked before D0/DA"):
        await api.set_frame([0] * 400)
    backend._acquire_mtu.assert_awaited_once()
    bluez_client.write_gatt_char.assert_not_awaited()


@pytest.mark.parametrize("acquire_exc", [BleakError("dbus failed"), TimeoutError("timed out")])
async def test_bluez_acquire_mtu_error_still_fails_closed(api, acquire_exc):
    bluez_client, backend = _make_bluez_client(api, acquire_exc=acquire_exc)
    api._client = bluez_client
    api.state = True
    api._verified_diy_client = bluez_client
    api._verified_diy_source = "local-hci0"
    api._info_client = bluez_client
    api._device_info = CAPABILITIES.copy()
    with pytest.raises(RuntimeError, match="blocked before D0/DA"):
        await api.set_frame([0] * 400)
    backend._acquire_mtu.assert_awaited_once()
    bluez_client.write_gatt_char.assert_not_awaited()


async def test_bluez_acquire_mtu_cancelled_propagates(api):
    bluez_client, _ = _make_bluez_client(api, acquire_exc=asyncio.CancelledError())
    api._client = bluez_client
    api.state = True
    api._verified_diy_client = bluez_client
    api._verified_diy_source = "local-hci0"
    api._info_client = bluez_client
    api._device_info = CAPABILITIES.copy()
    with pytest.raises(asyncio.CancelledError):
        await api.set_frame([0] * 400)
    bluez_client.write_gatt_char.assert_not_awaited()


async def test_unsupported_device_error_reports_device_profile(api, client):
    api._device_info = {
        "firmware": "5.0.0",
        "model": "TREE832",
        "led_count": 832,
        "columns": 32,
        "rows": 26,
        "diy_type": 6,
    }
    api._info_client = client
    with pytest.raises(RuntimeError, match="DIY blocked") as exc_info:
        await api.set_frame([0] * 400)
    msg = str(exc_info.value)
    assert "model=TREE832" in msg
    assert "firmware=5.0.0" in msg
    assert "led_count=832" in msg
    assert "columns=32" in msg
    assert "rows=26" in msg
    assert "diy_type=6" in msg
    assert api.address not in msg
    client.write_gatt_char.assert_not_awaited()


async def test_set_color_rgb_preserves_explicit_brightness(api, client):
    api.state = True
    await api.set_color_rgb(255, 0, 0, brightness=30)
    client.write_gatt_char.assert_awaited_once()
    assert client.write_gatt_char.await_args.args[1] == bytes.fromhex("aa030701000003e8012ccd")
    assert api.brightness == 30


async def test_set_brightness_preserves_preset_mode(api, client):
    api.state = True
    api.mode = 2
    api.current_preset = 18
    api.brightness = 50
    await api.set_brightness(30)
    client.write_gatt_char.assert_awaited_once()
    assert client.write_gatt_char.await_args.args[1] == bytes.fromhex("aa03040212012cf2")
    assert api.mode == 2
    assert api.current_preset == 18
    assert api.brightness == 30


async def test_set_preset_zero_brightness_is_not_coerced_to_50(api, client):
    api.state = True
    api.brightness = 50
    await api.set_preset(3, brightness=0)
    assert client.write_gatt_char.await_args.args[1] == bytes.fromhex("aa030402030000b6")
    assert api.brightness == 0


async def test_non_preset_status_clears_stale_current_preset(api, client):
    api.mode = 2
    api.current_preset = 18
    packet = build_packet(1, [0, 0, 0, 1, 4, 0, 0, 0])
    await api._handle_notification(None, bytearray(packet))
    assert api.mode == 4
    assert api.current_preset is None


def _make_pool_harness(pool, count):
    apis = [
        HelloFairyAPI(
            BLEDevice(f"AA:BB:CC:DD:EE:{i + 1:02X}", f"Curtain {i + 1}", {}),
            lambda: None,
            connection_pool=pool,
        )
        for i in range(count)
    ]
    by_address = {api.address: api for api in apis}
    active = set()
    peak = 0

    async def establish(client_cls, device, address, **kwargs):
        nonlocal peak
        owner = by_address[address]

        async def disconnect():
            client.is_connected = False
            active.discard(address)

        async def write(uuid, packet, response):
            if packet[1] in (2, 3):
                cmd = packet[1]
                await owner._handle_notification(None, bytearray([170, cmd, 0, (170 + cmd) & 255]))

        client = SimpleNamespace(
            is_connected=True,
            start_notify=AsyncMock(),
            disconnect=AsyncMock(side_effect=disconnect),
            write_gatt_char=AsyncMock(side_effect=write),
        )
        active.add(address)
        peak = max(peak, len(active))
        return client

    return apis, active, lambda: peak, establish


async def test_connection_pool_evicts_lru_idle_curtain_for_four_devices():
    pool = HelloFairyConnectionPool(max_connections=2)
    apis, active, get_peak, establish = _make_pool_harness(pool, 4)
    c1, c2, c3, c4 = apis

    with patch("bleak_retry_connector.establish_connection", AsyncMock(side_effect=establish)):
        await c1.set_power(True)
        await c2.set_power(True)
        assert active == {c1.address, c2.address}

        await c3.set_power(True)
        assert not c1.has_active_connection
        assert active == {c2.address, c3.address}

        await c4.set_power(True)
        assert not c2.has_active_connection
        assert active == {c3.address, c4.address}

        await c1.set_power(False)
        assert not c3.has_active_connection
        assert active == {c4.address, c1.address}

    assert get_peak() == 2


async def test_connection_pool_waits_for_busy_peer_without_interrupting_transfer():
    pool = HelloFairyConnectionPool(max_connections=2)
    apis, active, _, establish = _make_pool_harness(pool, 3)
    c1, c2, c3 = apis

    with patch("bleak_retry_connector.establish_connection", AsyncMock(side_effect=establish)):
        await c1.set_power(True)
        await c2.set_power(True)

        await c1._command_lock.acquire()
        c1._diy_transfer_client = c1._client
        await c2._command_lock.acquire()
        try:
            task = asyncio.create_task(c3.set_power(True))
            await asyncio.sleep(0.02)
            assert not task.done()
            assert c1.has_active_connection
            assert c2.has_active_connection

            c2._command_lock.release()
            await asyncio.wait_for(task, timeout=2.0)

            assert c1.has_active_connection
            assert not c2.has_active_connection
            assert c3.has_active_connection
            assert active == {c1.address, c3.address}
        finally:
            c1._diy_transfer_client = None
            if c1._command_lock.locked():
                c1._command_lock.release()
            if c2._command_lock.locked():
                c2._command_lock.release()


async def test_connection_pool_handles_disconnect_error_and_evicts_next_candidate():
    pool = HelloFairyConnectionPool(max_connections=2)
    apis, active, _, establish = _make_pool_harness(pool, 3)
    c1, c2, c3 = apis

    with patch("bleak_retry_connector.establish_connection", AsyncMock(side_effect=establish)):
        await c1.set_power(True)
        await c2.set_power(True)
        c1._client.disconnect.side_effect = BleakError("disconnect error")

        await c3.set_power(True)

    assert c1._cleanup_pending is not None
    assert not c2.has_active_connection
    assert c3.has_active_connection
    assert active == {c1.address, c3.address}


async def test_connection_pool_releases_connecting_slot_on_connect_failure():
    pool = HelloFairyConnectionPool(max_connections=2)
    apis, active, _, establish = _make_pool_harness(pool, 3)
    c1, c2, c3 = apis

    async def flaky_establish(client_cls, device, address, **kwargs):
        if address == c1.address:
            raise BleakError("boom")
        return await establish(client_cls, device, address, **kwargs)

    with (
        patch("bleak_retry_connector.establish_connection", AsyncMock(side_effect=flaky_establish)),
        patch("custom_components.hello_fairy_ble.api.asyncio.sleep", AsyncMock()),
    ):
        with pytest.raises(ConnectionError, match="3 attempts"):
            await c1._connect()
        assert len(pool._connecting) == 0

        await c2.set_power(True)
        await c3.set_power(True)

    assert active == {c2.address, c3.address}


async def test_prepare_diy_waits_for_cache_refresh_settle_and_uses_uncached_timeout(api, client):
    sleeps: list[float] = []
    timeouts: list[float | None] = []
    events: list[str] = []
    real_timeout = asyncio.timeout

    async def fake_sleep(delay):
        sleeps.append(delay)
        events.append(f"sleep:{delay}")

    def spy_timeout(delay):
        timeouts.append(delay)
        return real_timeout(delay)

    async def fake_disconnect():
        events.append("disconnect")
        api._client = None

    async def fake_establish(client_cls, device, address, **kwargs):
        events.append(f"connect:cache={kwargs.get('use_services_cache')}")
        client.is_connected = True
        return client

    api._device_info = CAPABILITIES.copy()
    api._info_client = client
    with (
        patch.object(api, "_disconnect_transport_locked", AsyncMock(side_effect=fake_disconnect)),
        patch.object(api, "_verify_diy_device_locked", AsyncMock()),
        patch(
            "custom_components.hello_fairy_ble.api.asyncio.sleep", AsyncMock(side_effect=fake_sleep)
        ),
        patch("custom_components.hello_fairy_ble.api.asyncio.timeout", side_effect=spy_timeout),
        patch("bleak_retry_connector.establish_connection", AsyncMock(side_effect=fake_establish)),
    ):
        await api._prepare_diy_locked()

    assert sleeps == [CACHE_REFRESH_SETTLE_DELAY]
    assert events == [
        "disconnect",
        f"sleep:{CACHE_REFRESH_SETTLE_DELAY}",
        "connect:cache=False",
    ]
    assert UNCACHED_CONNECT_TIMEOUT in timeouts


async def test_connect_timeout_formats_non_empty_error(api):
    with (
        patch(
            "bleak_retry_connector.establish_connection",
            AsyncMock(side_effect=TimeoutError()),
        ),
        patch("custom_components.hello_fairy_ble.api.asyncio.sleep", AsyncMock()),
    ):
        with pytest.raises(ConnectionError, match="3 attempts.*TimeoutError"):
            await api._connect()
