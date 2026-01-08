from __future__ import annotations

from enum import IntEnum
from dataclasses import dataclass
from typing import Callable
from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.const import CONF_ADDRESS
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .coordinator import HelloFairyCoordinator
from .const import DOMAIN

import logging

_LOGGER = logging.getLogger(__name__)
PLATFORMS: list[Platform] = [Platform.LIGHT, Platform.NUMBER]


@dataclass
class RuntimeData:
    """Class to hold Hello Fairy runtime data."""

    coordinator: HelloFairyCoordinator
    cancel_update_listener: Callable


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Set up Hello Fairy integration from a config entry."""

    hass.data.setdefault(DOMAIN, {})

    # Look for Hello Fairy device
    device_address = config_entry.data[CONF_ADDRESS]
    if not bluetooth.async_ble_device_from_address(hass, device_address, False):
        raise ConfigEntryNotReady(
            f"Could not find Hello Fairy BLE device with address {device_address}"
        )

    # Initialize the coordinator that manages data updates from the API
    coordinator = HelloFairyCoordinator(hass, config_entry)

    # Perform an initial data load from API
    await coordinator.async_config_entry_first_refresh()

    # Initialize a listener for config flow options changes
    cancel_update_listener = config_entry.add_update_listener(_async_update_listener)

    # Add the coordinator and update listener to hass data
    hass.data[DOMAIN][config_entry.entry_id] = RuntimeData(
        coordinator, cancel_update_listener
    )

    # Setup platforms (based on the list of entity types in PLATFORMS defined above)
    await hass.config_entries.async_forward_entry_setups(config_entry, PLATFORMS)

    return True


async def _async_update_listener(hass: HomeAssistant, config_entry: ConfigEntry):
    """Handle config options update."""
    # Reload the integration when the options change.
    await hass.config_entries.async_reload(config_entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    # Remove the config options update listener
    hass.data[DOMAIN][config_entry.entry_id].cancel_update_listener()

    # Unload platforms
    unload_ok = await hass.config_entries.async_unload_platforms(
        config_entry, PLATFORMS
    )

    # Remove the config entry from the hass data object
    if unload_ok:
        hass.data[DOMAIN].pop(config_entry.entry_id)

    return unload_ok
