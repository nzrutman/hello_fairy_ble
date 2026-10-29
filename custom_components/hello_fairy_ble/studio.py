"""Integration-owned Curtain Studio panel and device discovery.

Generated with aurora@aurora-smart-home (ha-integration-dev skill)
https://github.com/tonylofgren/aurora-smart-home
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import voluptuous as vol
from homeassistant.components import frontend, panel_custom, websocket_api
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant, callback

from .const import DOMAIN
from .library import async_setup_library
from .native_service import async_setup_native

VERSION = "2.0.0"
PANEL_PATH = "hello-fairy-studio"
STATIC_PATH = "/hello_fairy_ble_static"


async def async_setup_studio(hass: HomeAssistant) -> None:
    """Register bundled JS and the authenticated discovery command once per boot."""
    await hass.http.async_register_static_paths(
        [StaticPathConfig(STATIC_PATH, str(Path(__file__).parent / "frontend"), False)]
    )
    await async_setup_library(hass)
    await async_setup_native(hass)
    websocket_api.async_register_command(hass, websocket_studio_devices)
    websocket_api.async_register_command(hass, websocket_studio_read_status)


async def async_register_studio_panel(hass: HomeAssistant) -> None:
    """Register one integration panel regardless of the number of devices."""
    if frontend.async_panel_exists(hass, PANEL_PATH):
        return
    await panel_custom.async_register_panel(
        hass,
        frontend_url_path=PANEL_PATH,
        webcomponent_name="hello-fairy-studio-panel",
        sidebar_title="Curtain Studio",
        sidebar_icon="mdi:string-lights",
        module_url=f"{STATIC_PATH}/panel.js?v={VERSION}",
        embed_iframe=False,
        require_admin=True,
        config_panel_domain=DOMAIN,
        config={"version": VERSION},
    )


@callback
def async_remove_studio_if_unused(hass: HomeAssistant) -> None:
    """Remove the sidebar entry once the last integration entry is unloaded."""
    if any(
        getattr(e, "runtime_data", None) is not None
        for e in hass.config_entries.async_entries(DOMAIN)
    ):
        return
    frontend.async_remove_panel(hass, PANEL_PATH, warn_if_unknown=False)


@websocket_api.websocket_command({vol.Required("type"): "hello_fairy_ble/studio/devices"})
@websocket_api.require_admin
@callback
def websocket_studio_devices(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Return configured, loaded curtains; no manual MAC or BLE scan required."""
    curtains = []
    for entry in hass.config_entries.async_entries(DOMAIN):
        runtime = getattr(entry, "runtime_data", None)
        if runtime is None:
            continue
        coordinator = runtime.coordinator
        curtains.append(
            {
                "address": coordinator.device_address,
                "name": coordinator.device_name,
                "discovered": coordinator.device_discovered,
                "snapshot": coordinator.studio_snapshot,
            }
        )
    connection.send_result(msg["id"], {"version": VERSION, "curtains": curtains})


@websocket_api.websocket_command(
    {
        vol.Required("type"): "hello_fairy_ble/studio/read_status",
        vol.Required("address"): str,
    }
)
@websocket_api.require_admin
@websocket_api.async_response
async def websocket_studio_read_status(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Read device-reported state on demand; no full pixel readback exists here."""
    wanted = msg["address"].strip().upper()
    for entry in hass.config_entries.async_entries(DOMAIN):
        runtime = getattr(entry, "runtime_data", None)
        if runtime is not None and runtime.coordinator.device_address.upper() == wanted:
            try:
                await runtime.coordinator.request_status()
            except Exception as err:
                connection.send_error(msg["id"], "status_failed", str(err))
            else:
                connection.send_result(msg["id"], runtime.coordinator.studio_snapshot)
            return
    connection.send_error(msg["id"], "not_found", "Curtain is not configured or loaded")
