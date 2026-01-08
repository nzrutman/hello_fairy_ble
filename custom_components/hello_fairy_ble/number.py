"""Number platform for Hello Fairy BLE integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import RuntimeData
from .const import DOMAIN
from .coordinator import HelloFairyCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Hello Fairy number entities from config entry."""
    data: RuntimeData = hass.data[DOMAIN][config_entry.entry_id]
    coordinator = data.coordinator

    async_add_entities([HelloFairyPresetNumber(coordinator)])


class HelloFairyPresetNumber(CoordinatorEntity[HelloFairyCoordinator], NumberEntity):
    """Number entity for Hello Fairy preset control."""

    _attr_has_entity_name = True
    _attr_translation_key = "preset"
    _attr_icon = "mdi:palette"
    _attr_mode = NumberMode.BOX
    _attr_native_min_value = 1
    _attr_native_max_value = 58
    _attr_native_step = 1

    def __init__(self, coordinator: HelloFairyCoordinator) -> None:
        """Initialize the preset number entity."""
        super().__init__(coordinator)

        self._attr_unique_id = f"{coordinator.device_address}_preset"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, coordinator.device_address)},
            "name": coordinator.device_name,
            "manufacturer": "Hello Fairy",
            "model": "BLE Fairy Lights",
            "connections": {("bluetooth", coordinator.device_address)},
        }

    @property
    def native_value(self) -> float | None:
        """Return the current preset number."""
        if self.coordinator.data and self.coordinator.data.current_preset:
            return float(self.coordinator.data.current_preset)
        return None

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return super().available and self.coordinator.data is not None

    @property
    def entity_registry_enabled_default(self) -> bool:
        """Return if entity should be enabled when first added."""
        return True

    async def async_set_native_value(self, value: float) -> None:
        """Set the preset number."""
        preset_num = int(value)
        _LOGGER.debug("Setting preset to %d", preset_num)

        # Validate preset range
        if preset_num < 1 or preset_num > 58:
            _LOGGER.warning(
                "Invalid preset number %d, must be between 1 and 58", preset_num
            )
            return

        try:
            await self.coordinator.set_preset(preset_num)
        except Exception as err:
            _LOGGER.error("Failed to set preset to %d: %s", preset_num, err)
            raise

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.async_write_ha_state()
