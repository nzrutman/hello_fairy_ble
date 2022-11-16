from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.components.light import (
    ColorMode, 
    LightEntity, 
    ATTR_BRIGHTNESS, 
    ATTR_RGB_COLOR, 
    ATTR_EFFECT,
    LightEntityFeature
)
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import HelloFairyAPI
from .const import DOMAIN, EFFECT_PRESETS
from .coordinator import HelloFairyCoordinator

import logging
_LOGGER = logging.getLogger(__name__)

def brightness_scale(brightness_pct: int, from_min: int, from_max: int, to_min: int, to_max: int) -> int:
    """Scale brightness between different ranges."""
    return int(to_min + (brightness_pct - from_min) * (to_max - to_min) / (from_max - from_min))

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
):
    """Set up Hello Fairy Light."""
    # This gets the data update coordinator from hass.data as specified in your __init__.py
    coordinator: HelloFairyCoordinator = hass.data[DOMAIN][
        config_entry.entry_id
    ].coordinator

    async_add_entities([
        HelloFairyLight(coordinator)
    ], True)


class HelloFairyLight(CoordinatorEntity, LightEntity):
    """Hello Fairy Bluetooth Light Entity."""

    _attr_supported_color_modes = {ColorMode.RGB}
    _attr_color_mode = ColorMode.RGB
    _attr_supported_features = LightEntityFeature.EFFECT

    def __init__(self, coordinator: HelloFairyCoordinator):
        """Initialize."""
        super().__init__(coordinator)
        self._attr_name = coordinator.device_name
        self._attr_unique_id = f"{coordinator.device_address}"
        self._attr_device_info = DeviceInfo(
            manufacturer="Hello Fairy",
            model=coordinator.device_name,
            serial_number=coordinator.device_address,
            identifiers={(DOMAIN, coordinator.device_address)}
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()
    
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
        # Always turn on first
        await self.coordinator.set_power(True)

        # Handle brightness
        if ATTR_BRIGHTNESS in kwargs:
            brightness_255 = kwargs.get(ATTR_BRIGHTNESS, 255)
            # Convert from HA range (0-255) to Hello Fairy range (0-100)
            brightness_100 = brightness_scale(brightness_255, 0, 255, 0, 100)
            await self.coordinator.set_brightness(brightness_100)

        # Handle color
        if ATTR_RGB_COLOR in kwargs:
            red, green, blue = kwargs.get(ATTR_RGB_COLOR)
            await self.coordinator.set_color_rgb(red, green, blue)

        # Handle effect
        if ATTR_EFFECT in kwargs:
            effect_name = kwargs.get(ATTR_EFFECT)
            await self.coordinator.set_effect(effect_name)

        # Update state
        await self.coordinator.async_request_refresh()
    
    async def async_turn_off(self, **kwargs):
        """Turn device off."""
        await self.coordinator.set_power(False)
        await self.coordinator.async_request_refresh()
