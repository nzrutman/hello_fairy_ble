"""Real HTTP/WebSocket boundary checks (ha-integration-dev skill).
https://github.com/tonylofgren/aurora-smart-home
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.hello_fairy_ble import RuntimeData, studio
from custom_components.hello_fairy_ble.const import DOMAIN

from .conftest import ADDRESS


async def prepare(hass):
    assert await async_setup_component(hass, "http", {})
    await studio.async_setup_studio(hass)


async def test_admin_device_list_real_websocket(hass, hass_ws_client):
    await prepare(hass)
    client = await hass_ws_client(hass)
    await client.send_json_auto_id({"type": "hello_fairy_ble/studio/devices"})
    result = await client.receive_json()
    assert result["success"] is True
    assert result["result"]["curtains"] == []


async def test_non_admin_cannot_read_devices(hass, hass_ws_client, hass_read_only_access_token):
    await prepare(hass)
    client = await hass_ws_client(hass, access_token=hass_read_only_access_token)
    await client.send_json_auto_id({"type": "hello_fairy_ble/studio/devices"})
    result = await client.receive_json()
    assert result["success"] is False
    assert result["error"]["code"] == "unauthorized"


@pytest.mark.parametrize("failure", [False, True])
async def test_status_real_websocket_result_and_timeout(hass, hass_ws_client, failure):
    await prepare(hass)
    entry = MockConfigEntry(
        domain=DOMAIN, title="Test curtain", unique_id=ADDRESS, data={"address": ADDRESS}
    )
    entry.add_to_hass(hass)
    snapshot = {"pixel_readback": False, "reported": None, "last_upload": None}
    coordinator = SimpleNamespace(
        device_address=ADDRESS,
        studio_snapshot=snapshot,
        request_status=AsyncMock(side_effect=TimeoutError("no fresh status") if failure else None),
    )
    entry.runtime_data = RuntimeData(coordinator, Mock())
    client = await hass_ws_client(hass)
    await client.send_json_auto_id(
        {"type": "hello_fairy_ble/studio/read_status", "address": ADDRESS}
    )
    result = await client.receive_json()
    if failure:
        assert result["success"] is False
        assert result["error"]["code"] == "status_failed"
    else:
        assert result["success"] is True
        assert result["result"]["pixel_readback"] is False
    coordinator.request_status.assert_awaited_once()


async def test_bundled_assets_served_by_real_ha_http(hass, hass_client):
    await prepare(hass)
    client = await hass_client()
    response = await client.get("/hello_fairy_ble_static/patterns.js")
    assert response.status == 200
    assert "makePattern" in await response.text()
    response = await client.get("/hello_fairy_ble_static/../../secrets.yaml")
    assert response.status != 200
