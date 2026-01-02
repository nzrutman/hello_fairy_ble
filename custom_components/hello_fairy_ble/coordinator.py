"""Hello Fairy BLE coordinator for data updates."""

import logging
from dataclasses import dataclass
from datetime import timedelta

from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .api import HelloFairyAPI
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


@dataclass
class HelloFairyApiData:
    """Class to hold Hello Fairy API data."""

    state: bool | None = None
    brightness: int | None = None  # 0-100
    color: tuple[int, int, int] | None = None  # RGB (0-255)
    hsv: tuple[int, int, int] | None = None  # H(0-359), S(0-100), V(0-100)
    current_preset: int | None = None
    mode: int | None = None  # 1=color, 2=preset
    available_effects: list[str] | None = None


class HelloFairyCoordinator(DataUpdateCoordinator[HelloFairyApiData]):
    """Hello Fairy coordinator."""

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        """Initialize coordinator."""

        # Set variables from values entered in config flow setup
        self.device_name = config_entry.data[CONF_NAME]
        self.device_address = config_entry.data[CONF_ADDRESS]

        # Get connection to bluetooth device
        ble_device = bluetooth.async_ble_device_from_address(
            hass, self.device_address, connectable=False
        )
        assert ble_device
        self._api = HelloFairyAPI(ble_device, self._async_push_data)

        # Initialize DataUpdateCoordinator
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN} ({config_entry.unique_id})",
            # Hello Fairy pushes data via notifications, so use longer interval
            update_interval=timedelta(seconds=60),
            config_entry=config_entry,
        )

    @callback
    def _async_push_data(self) -> None:
        """Handle pushed data from device notifications."""
        # This callback is triggered when the device pushes new data
        # It should trigger a coordinator refresh
        self.async_set_updated_data(
            HelloFairyApiData(
                state=self._api.state,
                brightness=self._api.brightness,
                color=self._api.color,
                hsv=self._api.hsv,
                current_preset=self._api.current_preset,
                mode=self._api.mode,
                available_effects=self._api.available_effects,
            )
        )

    async def _async_update_data(self) -> HelloFairyApiData:
        """Fetch data from API endpoint."""
        # This method handles periodic updates when push notifications aren't received
        return HelloFairyApiData(
            state=self._api.state,
            brightness=self._api.brightness,
            color=self._api.color,
            hsv=self._api.hsv,
            current_preset=self._api.current_preset,
            mode=self._api.mode,
            available_effects=self._api.available_effects,
        )

    async def set_power(self, state: bool):
        """Set power state."""
        await self._api.set_power(state)

    async def set_brightness(self, brightness: int):
        """Set brightness (0-100)."""
        await self._api.set_brightness(brightness)

    async def set_color_rgb(self, r: int, g: int, b: int):
        """Set color using RGB values."""
        await self._api.set_color_rgb(r, g, b)

    async def set_color_hsv(self, h: int, s: int, v: int):
        """Set color using HSV values."""
        await self._api.set_color_hsv(h, s, v)

    async def set_preset(self, preset: int):
        """Set preset effect."""
        await self._api.set_preset(preset)

    async def set_effect(self, effect_name: str):
        """Set effect by name."""
        await self._api.set_effect(effect_name)
