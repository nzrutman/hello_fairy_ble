"""Favorite design buttons backed by Studio's saved, explicit curtain targets.

Generated with aurora@aurora-smart-home (ha-integration-dev skill)
https://github.com/tonylofgren/aurora-smart-home
"""

from __future__ import annotations

import asyncio
import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.storage import Store

from .const import DOMAIN

LIBRARY_SIGNAL = f"{DOMAIN}_library_changed"
_LOGGER = logging.getLogger(__name__)


class FavoriteDesignButton(ButtonEntity):
    """Recall one named design on its stored, ordered set of curtain targets."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:star"

    def __init__(self, design_id: str, name: str, addresses: list[str]) -> None:
        self.design_id = design_id
        owner = addresses[0].replace(":", "").lower()
        self._attr_unique_id = f"{DOMAIN}_favorite_{design_id}_{owner}"
        self.update_favorite(name, addresses)

    @callback
    def update_favorite(self, name: str, addresses: list[str]) -> None:
        """Keep the button's saved targets and friendly name current."""
        self._addresses = list(addresses)
        self._attr_name = f"Favorite {name}"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, addresses[0])})

    async def async_press(self) -> None:
        """Start recall through the same serialized, guarded Studio engine."""
        await self.hass.services.async_call(
            DOMAIN,
            "show_design",
            {"design_id": self.design_id, "addresses": self._addresses},
            blocking=True,
        )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Restore favorites and track additions/removals without requiring a reload."""
    address = entry.data[CONF_ADDRESS].upper()
    buttons: dict[str, FavoriteDesignButton] = {}
    lock = asyncio.Lock()
    revision = 0

    async def reconcile(data: dict) -> None:
        async with lock:
            if (
                not isinstance(data, dict)
                or not isinstance(data.get("designs"), list)
                or not isinstance(data.get("favorites", []), list)
            ):
                return
            designs = {
                d["id"]: d
                for d in data["designs"]
                if isinstance(d, dict)
                and isinstance(d.get("id"), str)
                and isinstance(d.get("name"), str)
            }
            wanted = {
                f["design_id"]: f
                for f in data.get("favorites", [])
                if isinstance(f, dict)
                and isinstance(f.get("addresses"), list)
                and f["addresses"]
                and all(isinstance(a, str) for a in f["addresses"])
                and f["addresses"][0].upper() == address
                and isinstance(f.get("design_id"), str)
                and f["design_id"] in designs
            }
            for design_id in set(buttons) - set(wanted):
                button = buttons.pop(design_id)
                registry = er.async_get(hass)
                entity_id = registry.async_get_entity_id("button", DOMAIN, button.unique_id)
                if entity_id:
                    registry.async_remove(entity_id)
                elif button.hass is not None:
                    await button.async_remove()
            new = []
            for design_id, favorite in wanted.items():
                name = designs[design_id]["name"]
                if design_id in buttons:
                    button = buttons[design_id]
                    button.update_favorite(name, favorite["addresses"])
                    if button.hass is not None:
                        button.async_write_ha_state()
                else:
                    button = FavoriteDesignButton(design_id, name, favorite["addresses"])
                    buttons[design_id] = button
                    new.append(button)
            if new:
                async_add_entities(new)

    @callback
    def updated(data: dict) -> None:
        nonlocal revision
        revision += 1
        entry.async_create_background_task(hass, reconcile(data), "Update Studio favorites")

    entry.async_on_unload(async_dispatcher_connect(hass, LIBRARY_SIGNAL, updated))
    before = revision
    try:
        stored = await Store(hass, 1, f"{DOMAIN}.studio_library").async_load()
    except (OSError, HomeAssistantError) as err:
        _LOGGER.warning("Favorite buttons unavailable; standard controls remain: %s", err)
        return
    if revision == before and isinstance(stored, dict):
        await reconcile(stored)
