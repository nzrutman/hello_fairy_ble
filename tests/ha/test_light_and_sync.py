"""Regression tests for standard light controls and explicit status sync (2.1.0)."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest
from bleak import BleakError
from bleak.backends.device import BLEDevice
from homeassistant.components.number import NumberMode
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
from custom_components.hello_fairy_ble.number import (
    HelloFairyPresetNumber,
    HelloFairySpeedNumber,
)
from custom_components.hello_fairy_ble.number import (
    async_setup_entry as number_async_setup_entry,
)
from custom_components.hello_fairy_ble.pixel_protocol import build_packet

from .conftest import ADDRESS, INFO_PACKET, STATUS_PACKET


def _make_light_coordinator(hass, *, state=True, brightness=50, current_speed=None):
    return SimpleNamespace(
        hass=hass,
        device_address=ADDRESS,
        device_name="Test Light",
        device_discovered=True,
        last_update_success=True,
        data=HelloFairyApiData(state=state, brightness=brightness, current_speed=current_speed),
        set_power=AsyncMock(),
        set_brightness=AsyncMock(),
        set_color_rgb=AsyncMock(),
        set_effect=AsyncMock(),
        set_speed=AsyncMock(),
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


async def test_coordinator_requests_connectable_devices_and_wires_refresh_callback(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Curtain 1",
        unique_id=ADDRESS,
        data={"address": ADDRESS, "name": "Curtain 1"},
    )
    entry.add_to_hass(hass)
    initial = object()
    refreshed = object()

    with (
        patch(
            "custom_components.hello_fairy_ble.coordinator.bluetooth.async_ble_device_from_address",
            side_effect=[initial, refreshed],
        ) as lookup,
        patch(
            "custom_components.hello_fairy_ble.coordinator.bluetooth.async_register_callback",
            return_value=Mock(),
        ) as register,
    ):
        coordinator = HelloFairyCoordinator(hass, entry)
        assert lookup.call_args_list[0].kwargs.get("connectable") is True
        matcher = register.call_args.args[2]
        assert matcher["address"] == ADDRESS
        assert matcher["connectable"] is True
        assert coordinator._api._ble_device_callback is not None
        assert coordinator._api._ble_device_callback() is refreshed
        assert lookup.call_args_list[1].kwargs.get("connectable") is True
        await coordinator.async_shutdown()


async def test_speed_number_entity_lifecycle_zero_value_and_validation(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"address": ADDRESS, "name": "Test Light"},
        state=ConfigEntryState.SETUP_IN_PROGRESS,
    )
    entry.add_to_hass(hass)
    coordinator = _make_light_coordinator(hass)
    entry.runtime_data = integration.RuntimeData(coordinator, Mock())

    added = []
    await number_async_setup_entry(hass, entry, added.extend)

    assert len(added) == 2
    assert isinstance(added[0], HelloFairyPresetNumber)
    speed_entity = added[1]
    assert isinstance(speed_entity, HelloFairySpeedNumber)
    speed_entity.hass = hass
    assert speed_entity.translation_key == "speed"
    assert speed_entity.icon == "mdi:speedometer"
    assert speed_entity.mode == NumberMode.SLIDER
    assert speed_entity.native_min_value == 0
    assert speed_entity.native_max_value == 100
    assert speed_entity.native_step == 1
    assert speed_entity.unique_id == f"{ADDRESS}_speed"
    assert speed_entity.entity_registry_enabled_default is True

    assert speed_entity.native_value is None
    coordinator.data.current_speed = 0
    assert speed_entity.native_value == 0.0
    coordinator.data.current_speed = 75
    assert speed_entity.native_value == 75.0

    assert speed_entity.available is True
    coordinator.device_discovered = False
    assert speed_entity.available is False
    coordinator.device_discovered = True
    saved_data = coordinator.data
    coordinator.data = None
    assert speed_entity.available is False
    coordinator.data = saved_data

    with patch(
        "custom_components.hello_fairy_ble.number.async_stop_playlist", AsyncMock()
    ) as stop_mock:
        await speed_entity.async_set_native_value(0)
        stop_mock.assert_awaited_once()
        coordinator.set_speed.assert_awaited_once_with(0)
        coordinator.async_request_refresh.assert_awaited_once()

        stop_mock.reset_mock()
        coordinator.set_speed.reset_mock()
        coordinator.async_request_refresh.reset_mock()

        await speed_entity.async_set_native_value(-1)
        await speed_entity.async_set_native_value(101)
        stop_mock.assert_not_awaited()
        coordinator.set_speed.assert_not_awaited()
        coordinator.async_request_refresh.assert_not_awaited()


async def test_coordinator_set_speed_and_native_sync_push_data(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Curtain 1",
        unique_id=ADDRESS,
        state=ConfigEntryState.SETUP_IN_PROGRESS,
        data={"address": ADDRESS, "name": "Curtain 1"},
    )
    entry.add_to_hass(hass)
    device = BLEDevice(ADDRESS, "Curtain 1", {})
    characteristic = SimpleNamespace(
        handle=9,
        properties=["write-without-response", "write"],
        max_write_without_response_size=509,
    )
    speed = 35
    fake_client = SimpleNamespace(
        is_connected=True,
        mtu_size=512,
        services=SimpleNamespace(get_characteristic=lambda _: characteristic),
        start_notify=AsyncMock(),
        disconnect=AsyncMock(),
    )

    with (
        patch(
            "custom_components.hello_fairy_ble.coordinator.bluetooth.async_ble_device_from_address",
            return_value=device,
        ),
        patch(
            "custom_components.hello_fairy_ble.coordinator.bluetooth.async_register_callback",
            return_value=Mock(),
        ),
    ):
        coordinator = HelloFairyCoordinator(hass, entry)

        async def write(uuid, packet, response):
            nonlocal speed
            if packet[:3] == b"\xaa\x00\x00":
                await coordinator._api._handle_notification(None, bytearray(INFO_PACKET))
            elif packet[:3] == b"\xaa\x01\x00":
                scene = bytearray(STATUS_PACKET[3:-1])
                scene[5] = 41
                await coordinator._api._handle_notification(None, bytearray(build_packet(1, scene)))
            elif packet[1] == 2:
                await coordinator._api._handle_notification(None, bytearray([170, 2, 0, 172]))
            elif packet[1] == 0x0C:
                if packet[2]:
                    speed = packet[3]
                else:
                    await coordinator._api._handle_notification(
                        None, bytearray(build_packet(0x0C, [speed]))
                    )

        fake_client.write_gatt_char = AsyncMock(side_effect=write)
        coordinator._api._client = fake_client
        coordinator._api.state = True
        notifications = []
        unsub = coordinator.async_add_listener(
            lambda: notifications.append(coordinator.data.current_speed)
        )

        try:
            await coordinator.async_config_entry_first_refresh()
            assert coordinator.data.current_speed is None

            await coordinator.set_speed(0)
            assert coordinator.data.current_speed == 0
            assert notifications[-1] == 0

            speed = 42
            original_wait_for = asyncio.wait_for
            with patch(
                "custom_components.hello_fairy_ble.native.asyncio.wait_for",
                lambda coro, timeout: original_wait_for(coro, timeout=0.001),
            ):
                await coordinator.inspect_native()
            assert coordinator.data.current_speed == 42
            assert notifications[-1] == 42

            await coordinator.set_native("scene_speed", {"speed": 70})
            assert coordinator.data.current_speed == 70
            assert notifications[-1] == 70
        finally:
            unsub()
            await coordinator.async_shutdown()
