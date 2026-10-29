"""Diagnostics must not leak artwork or access the radio (ha-integration-dev skill).
https://github.com/tonylofgren/aurora-smart-home
"""

import json
from types import SimpleNamespace
from unittest.mock import Mock

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.hello_fairy_ble import RuntimeData
from custom_components.hello_fairy_ble.const import DOMAIN
from custom_components.hello_fairy_ble.diagnostics import async_get_config_entry_diagnostics


async def test_unloaded_diagnostics_are_json_serializable(hass):
    entry = MockConfigEntry(domain=DOMAIN)
    result = await async_get_config_entry_diagnostics(hass, entry)
    assert not result["loaded"]
    json.dumps(result)


async def test_allowlist_excludes_names_addresses_pixels_and_text(hass):
    entry = MockConfigEntry(
        domain=DOMAIN, data={"address": "AA:BB:CC:DD:EE:01", "name": "Private curtain"}
    )
    client = object()
    coordinator = SimpleNamespace(
        studio_snapshot={
            "device_info": {
                "firmware": "4.6.0",
                "model": "25025",
                "led_count": 400,
                "columns": 20,
                "rows": 20,
                "diy_type": 3,
            },
            "diy_supported": True,
            "reported": {
                "power": True,
                "mode": 2,
                "scene": 201,
                "brightness_percent": 75,
                "source": "AA:BB:CC:DD:EE:01",
            },
            "last_upload": {"kind": "picture", "frames": [[0] * 400], "name": "Private message"},
            "address": "AA:BB:CC:DD:EE:01",
        },
        _api=SimpleNamespace(_client=client, _verified_diy_client=client),
    )
    entry.runtime_data = RuntimeData(coordinator, Mock())
    result = await async_get_config_entry_diagnostics(hass, entry)
    text = json.dumps(result)
    assert "AA:BB" not in text
    assert "Private" not in text
    assert "frames" not in text
    assert result["reported"]["brightness_percent"] == 75
    assert result["transport"]["capacity_verified_on_current_client"]
