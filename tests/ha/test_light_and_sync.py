"""Regression tests for standard light controls and explicit status sync (2.1.0)."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest
from bleak import BleakError
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import EntityCategory
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components import hello_fairy_ble as integration
from custom_components.hello_fairy_ble.api import HelloFairyConnectionPool
from custom_components.hello_fairy_ble.button import (
    HelloFairyRefreshStatusButton,
)
from custom_components.hello_fairy_ble.button import (
    async_setup_entry as button_async_setup_entry,
)
from custom_components.hello_fairy_ble.const import DOMAIN
from custom_components.hello_fairy_ble.coordinator import (
    HelloFairyApiData,
    HelloFairyCoordinator,
)
from custom_components.hello_fairy_ble.light import HelloFairyLight

from .conftest import ADDRESS


def _make_light_coordinator(hass, *, state=True, brightness=50):
    return SimpleNamespace(
        hass=hass,
        device_address=ADDRESS,
        device_name="Test Light",
        device_discovered=True,
        last_update_success=True,
        data=HelloFairyApiData(state=state, brightness=brightness),
        set_power=AsyncMock(),
        set_brightness=AsyncMock(),
        set_color_rgb=AsyncMock(),
        set_effect=AsyncMock(),
        request_status=AsyncMock(return_value={"power": state}),
        async_request_refresh=AsyncMock(),
    )


async def test_light_turn_on_brightness_and_rgb_single_color_write(hass):
    coordinator = _make_light_coordinator(hass, state=False, brightness=None)
    light = HelloFairyLight(coordinator)
    light.hass = hass

    await light.async_turn_on(brightness=76, rgb_color=(255, 0, 0))

    coordinator.set_power.assert_not_awaited()
    coordinator.set_brightness.assert_not_awaited()
    coordinator.set_color_rgb.assert_awaited_once_with(255, 0, 0, brightness=29)
    coordinator.async_request_refresh.assert_awaited_once()


async def test_light_turn_on_rgb_preserves_current_brightness(hass):
    coordinator = _make_light_coordinator(hass, state=True, brightness=30)
    light = HelloFairyLight(coordinator)
    light.hass = hass

    await light.async_turn_on(rgb_color=(255, 0, 0))

    coordinator.set_color_rgb.assert_awaited_once_with(255, 0, 0, brightness=30)
    coordinator.set_brightness.assert_not_awaited()


async def test_light_turn_on_brightness_and_effect_single_preset_write(hass):
    coordinator = _make_light_coordinator(hass, state=False, brightness=None)
    light = HelloFairyLight(coordinator)
    light.hass = hass

    await light.async_turn_on(brightness=76, effect="Xmas")

    coordinator.set_power.assert_not_awaited()
    coordinator.set_brightness.assert_not_awaited()
    coordinator.set_effect.assert_awaited_once_with("Xmas", brightness=29)
    coordinator.async_request_refresh.assert_awaited_once()


async def test_light_turn_on_brightness_when_off_waits_after_power_on(hass):
    coordinator = _make_light_coordinator(hass, state=False, brightness=None)
    light = HelloFairyLight(coordinator)
    light.hass = hass
    order = []

    async def power(val):
        order.append(("power", val))

    async def sleep_spy(delay):
        order.append(("sleep", delay))

    async def bright(val):
        order.append(("brightness", val))

    coordinator.set_power.side_effect = power
    coordinator.set_brightness.side_effect = bright

    with patch("custom_components.hello_fairy_ble.light.asyncio.sleep", side_effect=sleep_spy):
        await light.async_turn_on(brightness=76)

    assert order == [("power", True), ("sleep", 0.1), ("brightness", 29)]


async def test_refresh_status_button_lifecycle_and_errors(hass, hass_storage):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"address": ADDRESS, "name": "Test Light"},
        state=ConfigEntryState.SETUP_IN_PROGRESS,
    )
    entry.add_to_hass(hass)
    coordinator = _make_light_coordinator(hass)
    entry.runtime_data = integration.RuntimeData(coordinator, Mock())

    added = []
    with patch(
        "custom_components.hello_fairy_ble.button.Store.async_load", AsyncMock(return_value=None)
    ):
        await button_async_setup_entry(hass, entry, added.extend)

    assert len(added) == 1
    button = added[0]
    assert isinstance(button, HelloFairyRefreshStatusButton)
    assert button.entity_category is EntityCategory.DIAGNOSTIC
    assert button.translation_key == "refresh_status"
    assert button.unique_id == f"{ADDRESS}_refresh_status"
    assert button.available is True

    coordinator.device_discovered = False
    assert button.available is False

    await button.async_press()
    coordinator.request_status.assert_awaited_once()

    coordinator.request_status.side_effect = TimeoutError("no response")
    with pytest.raises(HomeAssistantError, match="no response"):
        await button.async_press()

    coordinator.request_status.side_effect = BleakError("bleak failed")
    with pytest.raises(HomeAssistantError, match="bleak failed"):
        await button.async_press()


async def test_refresh_status_service_preserves_playlist_and_maps_errors(hass, hass_storage):
    from custom_components.hello_fairy_ble.library import async_setup_library

    from .test_library import curtain, saved

    with patch.object(integration, "async_setup_studio", AsyncMock()):
        assert await integration.async_setup(hass, {})
    library = await async_setup_library(hass)
    target = curtain(hass)
    target.request_status = AsyncMock(return_value={"power": True})
    await saved(library)

    entered = asyncio.Event()
    original_hold = library._hold

    async def hold(seconds):
        entered.set()
        await original_hold(86400)

    with patch.object(library, "_hold", hold):
        await library.command("start", {"addresses": [ADDRESS]})
        await asyncio.wait_for(entered.wait(), 1)
        try:
            await hass.services.async_call(
                DOMAIN, "refresh_status", {"address": ADDRESS}, blocking=True
            )
            target.request_status.assert_awaited_once()
            assert library.active

            with pytest.raises(ServiceValidationError):
                await hass.services.async_call(
                    DOMAIN, "refresh_status", {"address": "AA:BB:CC:DD:EE:99"}, blocking=True
                )

            target.request_status.side_effect = TimeoutError("status timeout")
            with pytest.raises(HomeAssistantError, match="status timeout"):
                await hass.services.async_call(
                    DOMAIN, "refresh_status", {"address": ADDRESS}, blocking=True
                )
        finally:
            await library.stop()


async def test_coordinators_share_hass_connection_pool_and_unregister_on_shutdown(hass):
    entry1 = MockConfigEntry(
        domain=DOMAIN,
        title="Curtain 1",
        unique_id=ADDRESS,
        data={"address": ADDRESS, "name": "Curtain 1"},
    )
    entry2 = MockConfigEntry(
        domain=DOMAIN,
        title="Curtain 2",
        unique_id="AA:BB:CC:DD:EE:02",
        data={"address": "AA:BB:CC:DD:EE:02", "name": "Curtain 2"},
    )
    entry1.add_to_hass(hass)
    entry2.add_to_hass(hass)

    with (
        patch(
            "custom_components.hello_fairy_ble.coordinator.bluetooth.async_ble_device_from_address",
            return_value=None,
        ),
        patch(
            "custom_components.hello_fairy_ble.coordinator.bluetooth.async_register_callback",
            return_value=Mock(),
        ),
    ):
        c1 = HelloFairyCoordinator(hass, entry1)
        c2 = HelloFairyCoordinator(hass, entry2)
        pool = c1._api._connection_pool
        assert isinstance(pool, HelloFairyConnectionPool)
        assert c2._api._connection_pool is pool
        assert c1._api in pool._apis
        assert c2._api in pool._apis

        await c1.async_shutdown()
        assert c1._api not in pool._apis
        assert c2._api in pool._apis
        await c2.async_shutdown()
        assert c2._api not in pool._apis
