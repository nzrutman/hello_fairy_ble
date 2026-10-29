"""Favorite HA buttons share Studio targets (ha-integration-dev skill).
https://github.com/tonylofgren/aurora-smart-home
"""

from unittest.mock import AsyncMock, Mock, patch

from homeassistant.config_entries import ConfigEntryState
from homeassistant.helpers.dispatcher import async_dispatcher_send
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.hello_fairy_ble.button import (
    LIBRARY_SIGNAL,
    FavoriteDesignButton,
    async_setup_entry,
)
from custom_components.hello_fairy_ble.const import DOMAIN

from .conftest import ADDRESS


async def test_favorite_button_uses_stored_layout(hass):
    calls = []

    async def show(call):
        calls.append(call.data)

    hass.services.async_register(DOMAIN, "show_design", show)
    button = FavoriteDesignButton("heart", "Heart", [ADDRESS, "AA:BB:CC:DD:EE:02"])
    button.hass = hass
    await button.async_press()
    assert calls == [{"design_id": "heart", "addresses": [ADDRESS, "AA:BB:CC:DD:EE:02"]}]
    assert button.unique_id == "hello_fairy_ble_favorite_heart_aabbccddee01"


async def test_dynamic_favorites_owned_by_first_target(hass, hass_storage):
    entry = MockConfigEntry(
        domain=DOMAIN, data={"address": ADDRESS}, state=ConfigEntryState.SETUP_IN_PROGRESS
    )
    entry.add_to_hass(hass)
    add = Mock()
    with patch(
        "custom_components.hello_fairy_ble.button.Store.async_load", AsyncMock(return_value=None)
    ):
        await async_setup_entry(hass, entry, add)
    async_dispatcher_send(
        hass,
        LIBRARY_SIGNAL,
        {
            "designs": [{"id": "a", "name": "Heart"}, {"id": "b", "name": "Other"}],
            "favorites": [
                {"design_id": "a", "addresses": [ADDRESS]},
                {"design_id": "b", "addresses": ["AA:BB:CC:DD:EE:02", ADDRESS]},
            ],
        },
    )
    await hass.async_block_till_done(wait_background_tasks=True)
    add.assert_called_once()
    assert len(add.call_args.args[0]) == 1
    assert add.call_args.args[0][0].design_id == "a"


async def test_malformed_library_does_not_break_standard_entry(hass, hass_storage):
    entry = MockConfigEntry(
        domain=DOMAIN, data={"address": ADDRESS}, state=ConfigEntryState.SETUP_IN_PROGRESS
    )
    entry.add_to_hass(hass)
    add = Mock()
    bad = {
        "designs": [None, {"id": []}],
        "favorites": [None, {"design_id": [], "addresses": [None]}],
    }
    with patch(
        "custom_components.hello_fairy_ble.button.Store.async_load", AsyncMock(return_value=bad)
    ):
        await async_setup_entry(hass, entry, add)
    add.assert_not_called()
