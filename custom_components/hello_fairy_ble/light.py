"""Hello Fairy Light platform."""

from __future__ import annotations

import asyncio
import logging

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_EFFECT,
    ATTR_RGB_COLOR,
    ColorMode,
    LightEntity,
    LightEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, EFFECT_PRESETS
from .coordinator import HelloFairyCoordinator
from .library import async_stop_playlist

_LOGGER = logging.getLogger(__name__)


def brightness_scale(
    brightness_pct: int, from_min: int, from_max: int, to_min: int, to_max: int
) -> int:
    """Scale brightness between different ranges."""
    return int(to_min + (brightness_pct - from_min) * (to_max - to_min) / (from_max - from_min))


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
):
    """Set up Hello Fairy Light."""
    coordinator: HelloFairyCoordinator = config_entry.runtime_data.coordinator

    async_add_entities([HelloFairyLight(coordinator)], True)


class HelloFairyLight(CoordinatorEntity[HelloFairyCoordinator], LightEntity):
    """Hello Fairy Bluetooth Light Entity."""

    _attr_supported_color_modes = {ColorMode.RGB}
    _attr_color_mode = ColorMode.RGB
    _attr_supported_features = LightEntityFeature.EFFECT

    def __init__(self, coordinator: HelloFairyCoordinator) -> None:
        """Initialize Hello Fairy light entity."""
        super().__init__(coordinator)
        self._attr_name = coordinator.device_name
        self._attr_unique_id = coordinator.device_address
        self._attr_device_info = DeviceInfo(
            manufacturer="Hello Fairy",
            model=coordinator.device_name,
            serial_number=coordinator.device_address,
            identifiers={(DOMAIN, coordinator.device_address)},
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()

    @property
    def available(self) -> bool:
        """Return True if the BLE device has been discovered."""
        return super().available and self.coordinator.device_discovered

    @property
    def brightness(self) -> int | None:
        """Return the current brightness (0-255)."""
        if self.coordinator.data.brightness is not None:
            # Convert from Hello Fairy range (0-100) to HA range (0-255)
            return brightness_scale(self.coordinator.data.brightness, 0, 100, 0, 255)
        return None

    @property
    def is_on(self) -> bool | None:
        """Return true if light is on."""
        return self.coordinator.data.state

    @property
    def rgb_color(self) -> tuple[int, int, int] | None:
        """Return the current RGB color."""
        return self.coordinator.data.color

    @property
    def effect_list(self) -> list[str] | None:
        """Return list of available effects."""
        return self.coordinator.data.available_effects

    @property
    def effect(self) -> str | None:
        """Return current effect."""
        if self.coordinator.data.mode == 2 and self.coordinator.data.current_preset:
            # Find effect name by preset number
            preset_num = self.coordinator.data.current_preset
            for effect_name, preset_value in EFFECT_PRESETS.items():
                if preset_value == preset_num:
                    return effect_name
        return None

    async def async_turn_on(self, **kwargs):
        """Turn device on."""
        await async_stop_playlist(self.hass)
        data = getattr(self.coordinator, "data", None)
        brightness_100 = (
            brightness_scale(kwargs.get(ATTR_BRIGHTNESS, 255), 0, 255, 0, 100)
            if ATTR_BRIGHTNESS in kwargs
            else None
        )

        if ATTR_EFFECT in kwargs:
            effect_name = kwargs[ATTR_EFFECT]
            if effect_name not in EFFECT_PRESETS:
                await self.coordinator.set_power(True)
            await self.coordinator.set_effect(effect_name, brightness=brightness_100)
        elif ATTR_RGB_COLOR in kwargs:
            red, green, blue = kwargs[ATTR_RGB_COLOR]
            current_brightness = data.brightness if data is not None else None
            target_brightness = brightness_100 if brightness_100 is not None else current_brightness
            await self.coordinator.set_color_rgb(red, green, blue, brightness=target_brightness)
        elif brightness_100 is not None:
            was_on = bool(data is not None and data.state)
            await self.coordinator.set_power(True)
            if not was_on:
                await asyncio.sleep(0.1)
            await self.coordinator.set_brightness(brightness_100)
        else:
            await self.coordinator.set_power(True)

        # Update state
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs):
        """Turn device off."""
        await async_stop_playlist(self.hass)
        await self.coordinator.set_power(False)
        await self.coordinator.async_request_refresh()
