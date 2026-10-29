"""Exercise real HA services, config entries and coordinator lifecycle.
Generated with aurora@aurora-smart-home (ha-integration-dev skill)
https://github.com/tonylofgren/aurora-smart-home
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components import hello_fairy_ble as integration
from custom_components.hello_fairy_ble.const import DOMAIN
from custom_components.hello_fairy_ble.coordinator import HelloFairyCoordinator

from .conftest import ADDRESS


@pytest.fixture
def entry(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Test curtain",
        unique_id=ADDRESS,
        state=ConfigEntryState.SETUP_IN_PROGRESS,
        data={"address": ADDRESS, "name": "Test curtain"},
    )
    entry.add_to_hass(hass)
    return entry


async def test_no_radio_at_startup_and_actual_coordinator(hass, entry):
    with (
        patch(
            "custom_components.hello_fairy_ble.coordinator.bluetooth.async_ble_device_from_address",
            return_value=None,
        ),
        patch(
            "custom_components.hello_fairy_ble.coordinator.bluetooth.async_register_callback",
            return_value=Mock(),
        ),
        patch("bleak_retry_connector.establish_connection", AsyncMock()) as connect,
    ):
        coordinator = HelloFairyCoordinator(hass, entry)
        await coordinator.async_config_entry_first_refresh()
        assert coordinator.data.state is None
        assert not coordinator.device_discovered
        connect.assert_not_awaited()
        await coordinator.async_shutdown()


async def test_real_entry_runtime_and_unload(hass, entry):
    coordinator = SimpleNamespace(
        async_config_entry_first_refresh=AsyncMock(), async_shutdown=AsyncMock()
    )
    with (
        patch.object(integration, "HelloFairyCoordinator", return_value=coordinator),
        patch.object(hass.config_entries, "async_forward_entry_setups", AsyncMock()) as forward,
        patch.object(hass.config_entries, "async_unload_platforms", AsyncMock(return_value=True)),
        patch.object(integration, "async_register_studio_panel", AsyncMock()),
        patch.object(integration, "async_remove_studio_if_unused", Mock()),
    ):
        assert await integration.async_setup_entry(hass, entry)
        assert entry.runtime_data.coordinator is coordinator
        assert [p.value for p in forward.await_args.args[1]] == ["light", "number", "button"]
        assert await integration.async_unload_entry(hass, entry)
        assert entry.runtime_data is None
        coordinator.async_shutdown.assert_awaited_once()


async def test_failed_platform_setup_releases_connection(hass, entry):
    coordinator = SimpleNamespace(
        async_config_entry_first_refresh=AsyncMock(), async_shutdown=AsyncMock()
    )
    with (
        patch.object(integration, "HelloFairyCoordinator", return_value=coordinator),
        patch.object(
            hass.config_entries,
            "async_forward_entry_setups",
            AsyncMock(side_effect=RuntimeError("setup failed")),
        ),
    ):
        with pytest.raises(RuntimeError, match="setup failed"):
            await integration.async_setup_entry(hass, entry)
    assert entry.runtime_data is None
    coordinator.async_shutdown.assert_awaited_once()


async def test_failed_unload_keeps_runtime(hass, entry):
    runtime = integration.RuntimeData(SimpleNamespace(async_shutdown=AsyncMock()), Mock())
    entry.runtime_data = runtime
    with patch.object(hass.config_entries, "async_unload_platforms", AsyncMock(return_value=False)):
        assert not await integration.async_unload_entry(hass, entry)
    assert entry.runtime_data is runtime
    runtime.cancel_update_listener.assert_not_called()


async def setup_services(hass):
    with patch.object(integration, "async_setup_studio", AsyncMock()):
        assert await integration.async_setup(hass, {})


@pytest.mark.parametrize("pixels", [[0] * 399, [True] * 400, [181] * 400])
async def test_real_service_rejects_invalid_frames(hass, pixels):
    await setup_services(hass)
    target = SimpleNamespace(set_frame=AsyncMock())
    with patch.object(integration, "_coordinator_for_address", return_value=target):
        with pytest.raises(ServiceValidationError):
            await hass.services.async_call(
                DOMAIN, "set_frame", {"address": ADDRESS, "pixels": pixels}, blocking=True
            )
    target.set_frame.assert_not_awaited()


async def test_service_transport_errors_are_normal_ha_errors(hass):
    await setup_services(hass)
    target = SimpleNamespace(set_frame=AsyncMock(side_effect=ConnectionError("radio unavailable")))
    with patch.object(integration, "_coordinator_for_address", return_value=target):
        with pytest.raises(HomeAssistantError, match="radio unavailable"):
            await hass.services.async_call(
                DOMAIN, "set_frame", {"address": ADDRESS, "pixels": [0] * 400}, blocking=True
            )


async def test_virtual_frame_stops_at_first_failure(hass):
    await setup_services(hass)
    first = SimpleNamespace(set_frame=AsyncMock(side_effect=ConnectionError("first failed")))
    second = SimpleNamespace(set_frame=AsyncMock())
    with patch.object(integration, "_coordinator_for_address", side_effect=[first, second]):
        with pytest.raises(HomeAssistantError):
            await hass.services.async_call(
                DOMAIN,
                "set_virtual_frame",
                {"addresses": [ADDRESS, "AA:BB:CC:DD:EE:02"], "pixels": [0] * 800},
                blocking=True,
            )
    second.set_frame.assert_not_awaited()


async def test_duplicate_virtual_addresses_rejected(hass):
    await setup_services(hass)
    with pytest.raises(ServiceValidationError, match="unique"):
        await hass.services.async_call(
            DOMAIN,
            "set_virtual_frame",
            {"addresses": [ADDRESS, ADDRESS], "pixels": [0] * 800},
            blocking=True,
        )


@pytest.mark.parametrize(
    "kind,movement", [("animation", "left"), ("unknown", "still"), ("picture", "unknown")]
)
async def test_real_playback_schema_and_handler(hass, kind, movement):
    await setup_services(hass)
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            "set_diy_playback",
            {
                "address": ADDRESS,
                "kind": kind,
                "movement": movement,
                "speed": 50,
                "brightness": 100,
            },
            blocking=True,
        )


@pytest.mark.parametrize(
    "service,payload",
    [
        ("set_frame", {"address": ADDRESS, "pixels": [0] * 399}),
        ("set_frame", {"address": ADDRESS, "pixels": [181] * 400}),
        ("set_pixel", {"address": ADDRESS, "x": 0, "y": 0}),
        ("set_pixel", {"address": ADDRESS, "x": 0, "y": 0, "rgb": [255, 0, 0], "color_byte": 0}),
        ("set_pixel", {"address": ADDRESS, "x": 0, "y": 0, "color_byte": 181}),
        (
            "set_two_picture_animation",
            {"address": ADDRESS, "experimental": True, "frames": [[0] * 400, [0] * 399]},
        ),
        (
            "set_diy_playback",
            {
                "address": ADDRESS,
                "kind": "animation",
                "movement": "left",
                "speed": 50,
                "brightness": 100,
            },
        ),
        ("set_virtual_frame", {"addresses": [ADDRESS], "pixels": [0] * 399}),
        ("set_virtual_frame", {"addresses": [ADDRESS, ADDRESS], "pixels": [0] * 800}),
        ("set_virtual_frame", {"addresses": [ADDRESS, "AA:BB:CC:DD:EE:02"], "pixels": [0] * 800}),
        *[
            (service, {"address": "AA:BB:CC:DD:EE:02", **payload})
            for service, payload in [
                ("enter_draw_mode", {}),
                ("clear_matrix", {}),
                ("test_pattern", {}),
                ("set_frame", {"pixels": [0] * 400}),
                ("set_pixel", {"x": 0, "y": 0, "color_byte": 0}),
                (
                    "set_two_picture_animation",
                    {"experimental": True, "frames": [[0] * 400, [0] * 400]},
                ),
                (
                    "set_diy_playback",
                    {"kind": "picture", "movement": "still", "speed": 50, "brightness": 100},
                ),
            ]
        ],
    ],
)
async def test_invalid_service_preserves_running_playlist(hass, hass_storage, service, payload):
    from custom_components.hello_fairy_ble.library import async_setup_library

    from .test_library import curtain, saved

    await setup_services(hass)
    library = await async_setup_library(hass)
    target = curtain(hass)
    for name in ("set_pixel", "clear_pixels", "enter_draw_mode"):
        setattr(target, name, AsyncMock())
    await saved(library)
    entered = asyncio.Event()
    original_hold = library._hold

    async def hold(seconds):
        entered.set()
        await original_hold(86400)

    with patch.object(library, "_hold", hold):
        await library.command("start", {"addresses": [ADDRESS]})
        await asyncio.wait_for(entered.wait(), 1)
        task = library._task
        writes = [
            getattr(target, name)
            for name in (
                "set_pixel",
                "clear_pixels",
                "enter_draw_mode",
                "set_frame",
                "set_two_picture_animation",
                "set_diy_playback",
            )
        ]
        for write in writes:
            write.reset_mock()
        try:
            with pytest.raises(ServiceValidationError):
                await hass.services.async_call(DOMAIN, service, payload, blocking=True)
            assert library.active
            assert library._task is task
            assert library.status["state"] == "holding"
            assert not library._stop.is_set()
            for write in writes:
                write.assert_not_awaited()
        finally:
            await library.stop()


async def test_valid_service_stops_playlist_before_manual_write(hass, hass_storage):
    from custom_components.hello_fairy_ble.library import async_setup_library

    from .test_library import curtain, saved

    await setup_services(hass)
    library = await async_setup_library(hass)
    target = curtain(hass)
    await saved(library)
    entered = asyncio.Event()
    original_hold = library._hold

    async def hold(seconds):
        entered.set()
        await original_hold(86400)

    async def manual_write(pixels):
        assert not library.active
        assert pixels == [255] * 400

    with patch.object(library, "_hold", hold):
        await library.command("start", {"addresses": [ADDRESS]})
        await asyncio.wait_for(entered.wait(), 1)
        target.set_frame.reset_mock()
        target.set_frame.side_effect = manual_write
        try:
            await hass.services.async_call(
                DOMAIN, "set_frame", {"address": ADDRESS, "pixels": [255] * 400}, blocking=True
            )
            target.set_frame.assert_awaited_once()
            assert not library.active
        finally:
            await library.stop()
