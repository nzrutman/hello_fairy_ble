"""Validated native actions shared by Studio and Home Assistant automations.

Generated with aurora@aurora-smart-home (ha-integration-dev skill)
https://github.com/tonylofgren/aurora-smart-home
"""

import voluptuous as vol
from bleak import BleakError
from homeassistant.components import websocket_api
from homeassistant.exceptions import HomeAssistantError

from .const import DOMAIN
from .library import async_stop_playlist
from .native_validation import SCHEMAS


async def perform_native(hass, address, action, payload):
    """Validate before stopping playback or attempting a connection."""
    if action not in SCHEMAS:
        raise ValueError("Unsupported native action")
    values = SCHEMAS[action](payload)
    coordinator = next(
        (
            e.runtime_data.coordinator
            for e in hass.config_entries.async_entries(DOMAIN)
            if getattr(e, "runtime_data", None) is not None
            and e.runtime_data.coordinator.device_address.upper() == address.strip().upper()
        ),
        None,
    )
    if coordinator is None:
        raise ValueError("Curtain is not configured or loaded")
    if action == "inspect":
        await coordinator.inspect_native()
        return coordinator.studio_snapshot
    await async_stop_playlist(hass)
    return await coordinator.set_native(action, values)


async def async_setup_native(hass):
    """Register explicit actions once with the integration-owned Studio."""

    @websocket_api.websocket_command(
        {
            vol.Required("type"): f"{DOMAIN}/studio/native",
            vol.Required("address"): str,
            vol.Required("action"): str,
            vol.Optional("payload", default=dict): dict,
        }
    )
    @websocket_api.require_admin
    @websocket_api.async_response
    async def handle(hass, connection, msg):
        try:
            result = await perform_native(hass, msg["address"], msg["action"], msg["payload"])
        except (
            ValueError,
            vol.Invalid,
            OSError,
            HomeAssistantError,
            RuntimeError,
            TimeoutError,
            BleakError,
        ) as err:
            connection.send_error(msg["id"], "native_failed", str(err))
        else:
            connection.send_result(msg["id"], result)

    async def service(call):
        try:
            await perform_native(
                hass, call.data["address"], call.data["action"], call.data["payload"]
            )
        except (ValueError, vol.Invalid, OSError, RuntimeError, TimeoutError, BleakError) as err:
            raise HomeAssistantError(str(err)) from err

    websocket_api.async_register_command(hass, handle)
    hass.services.async_register(
        DOMAIN,
        "native_control",
        service,
        schema=vol.Schema(
            {
                vol.Required("address"): str,
                vol.Required("action"): vol.In(SCHEMAS),
                vol.Optional("payload", default=dict): dict,
            }
        ),
    )
