"""Allowlisted diagnostics without addresses, names, artwork or new BLE queries.

Generated with aurora@aurora-smart-home (ha-integration-dev skill)
https://github.com/tonylofgren/aurora-smart-home
"""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .studio import VERSION


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: ConfigEntry) -> dict:
    """Report only existing capability/status metadata; never connect to a curtain."""
    runtime = getattr(entry, "runtime_data", None)
    result = {"integration_version": VERSION, "loaded": runtime is not None}
    if runtime is None:
        return result
    coordinator = runtime.coordinator
    snapshot = coordinator.studio_snapshot
    info = snapshot.get("device_info") or {}
    reported = snapshot.get("reported") or {}
    result["device_profile"] = {
        key: info.get(key)
        for key in ("firmware", "model", "led_count", "columns", "rows", "diy_type")
    }
    result["reported"] = {
        key: reported.get(key) for key in ("power", "mode", "scene", "brightness_percent")
    }
    result["diy_supported"] = bool(snapshot.get("diy_supported"))
    result["pixel_readback"] = False
    upload = snapshot.get("last_upload") or {}
    result["last_upload_kind"] = upload.get("kind")
    api = getattr(coordinator, "_api", None)
    client = getattr(api, "_client", None)
    result["transport"] = {
        "client_type": type(client).__name__ if client is not None else None,
        "capacity_verified_on_current_client": bool(
            client is not None and getattr(api, "_verified_diy_client", None) is client
        ),
        "note": "Cached metadata only; no new BLE query or physical confirmation",
    }
    return result
