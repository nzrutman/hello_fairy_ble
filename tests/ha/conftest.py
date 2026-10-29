"""Real HA fixtures; only radio I/O is simulated (ha-integration-dev skill).
https://github.com/tonylofgren/aurora-smart-home
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from bleak.backends.device import BLEDevice

pytest_plugins = "pytest_homeassistant_custom_component"

ADDRESS = "AA:BB:CC:DD:EE:01"
INFO_PACKET = bytes.fromhex(
    "aa001f342e362e30323530323500000000000000000000019014011402030207080390"
)
STATUS_PACKET = bytes.fromhex("aa01080000000102c90064e3")
CAPABILITIES = {
    "firmware": "4.6.0",
    "model": "25025",
    "led_count": 400,
    "columns": 20,
    "rows": 20,
    "diy_type": 3,
}


@pytest.fixture(autouse=True)
def custom_integrations(enable_custom_integrations):
    """Let the real HA loader see this repository's integration."""


@pytest.fixture
def api():
    from custom_components.hello_fairy_ble.api import HelloFairyAPI

    return HelloFairyAPI(BLEDevice(ADDRESS, "Test curtain", {}), lambda: None)


@pytest.fixture
def client(api):
    """No actual adapter: writes feed captured replies into the real decoder."""
    characteristic = SimpleNamespace(
        handle=9,
        properties=["write-without-response", "write"],
        max_write_without_response_size=509,
    )
    c = SimpleNamespace(
        is_connected=True,
        mtu_size=512,
        _connected_scanner=SimpleNamespace(source="test-proxy"),
        services=SimpleNamespace(get_characteristic=lambda _: characteristic),
        clear_cache=AsyncMock(return_value=True),
        start_notify=AsyncMock(),
    )

    async def disconnect():
        c.is_connected = False

    async def write(uuid, packet, response):
        if packet[:3] == b"\xaa\x00\x00":
            await api._handle_notification(None, bytearray(INFO_PACKET))
        elif packet[:3] == b"\xaa\x01\x00":
            await api._handle_notification(None, bytearray(STATUS_PACKET))
        elif packet[1] in (2, 3):
            cmd = packet[1]
            await api._handle_notification(None, bytearray([170, cmd, 0, (170 + cmd) & 255]))

    c.disconnect = AsyncMock(side_effect=disconnect)
    c.write_gatt_char = AsyncMock(side_effect=write)
    c.characteristic = characteristic
    api._client = c
    return c


@pytest.fixture
def verified(api, client):
    api.state = True
    api._verified_diy_client = client
    api._verified_diy_source = "test-proxy"
    api._info_client = client
    api._device_info = CAPABILITIES.copy()
    return client
