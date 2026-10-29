"""Hello Fairy BLE integration with built-in Curtain Studio v2.0.0.

Generated with aurora@aurora-smart-home (ha-integration-dev skill)
https://github.com/tonylofgren/aurora-smart-home
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from functools import wraps
from typing import Any

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from bleak import BleakError
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError

from .const import DOMAIN
from .coordinator import HelloFairyCoordinator
from .diy_controls import build_playback_commands
from .pixel_protocol import (
    MATRIX_HEIGHT,
    MATRIX_WIDTH,
    PIXEL_COUNT,
    PIXEL_OFF,
    rgb_to_pixel_byte,
    split_virtual_frame,
    validate_color_byte,
)
from .studio import async_register_studio_panel, async_remove_studio_if_unused, async_setup_studio

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

PLATFORMS: list[Platform] = [Platform.LIGHT, Platform.NUMBER, Platform.BUTTON]

SERVICE_ENTER_DRAW_MODE = "enter_draw_mode"
SERVICE_CLEAR_MATRIX = "clear_matrix"
SERVICE_SET_PIXEL = "set_pixel"
SERVICE_SET_FRAME = "set_frame"
SERVICE_SET_VIRTUAL_FRAME = "set_virtual_frame"
SERVICE_TEST_PATTERN = "test_pattern"

ATTR_ADDRESS = "address"
ATTR_ADDRESSES = "addresses"
ATTR_X = "x"
ATTR_Y = "y"
ATTR_RGB = "rgb"
ATTR_COLOR_BYTE = "color_byte"
ATTR_PIXELS = "pixels"

ADDRESS_SCHEMA = vol.Schema({vol.Required(ATTR_ADDRESS): cv.string})
SET_PIXEL_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_ADDRESS): cv.string,
        vol.Required(ATTR_X): vol.All(vol.Coerce(int), vol.Range(min=0, max=19)),
        vol.Required(ATTR_Y): vol.All(vol.Coerce(int), vol.Range(min=0, max=19)),
        vol.Optional(ATTR_RGB): vol.All(cv.ensure_list, vol.Length(min=3, max=3)),
        vol.Optional(ATTR_COLOR_BYTE): vol.All(vol.Coerce(int), vol.Range(min=0, max=255)),
    }
)
SET_FRAME_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_ADDRESS): cv.string,
        vol.Required(ATTR_PIXELS): cv.ensure_list,
    }
)
SET_VIRTUAL_FRAME_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_ADDRESSES): vol.All(cv.ensure_list, vol.Length(min=1, max=8)),
        vol.Required(ATTR_PIXELS): cv.ensure_list,
    }
)
TWO_PICTURE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_ADDRESS): cv.string,
        vol.Required("frames"): vol.All(cv.ensure_list, vol.Length(min=2, max=2)),
        vol.Required("experimental"): True,
    }
)
PLAYBACK_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_ADDRESS): cv.string,
        vol.Required("kind"): cv.string,
        vol.Required("movement"): cv.string,
        vol.Required("speed"): vol.All(vol.Coerce(int), vol.Range(min=0, max=100)),
        vol.Required("brightness"): vol.All(vol.Coerce(int), vol.Range(min=0, max=100)),
    }
)
TEST_PATTERN_SCHEMA = vol.Schema({vol.Required(ATTR_ADDRESS): cv.string})


@dataclass
class RuntimeData:
    """Class to hold Hello Fairy runtime data."""

    coordinator: HelloFairyCoordinator
    cancel_update_listener: Callable


def _normalize_address(address: str) -> str:
    return address.strip().upper()


def _coordinator_for_address(hass: HomeAssistant, address: str) -> HelloFairyCoordinator:
    wanted = _normalize_address(address)
    for entry in hass.config_entries.async_entries(DOMAIN):
        runtime = getattr(entry, "runtime_data", None)
        if isinstance(runtime, RuntimeData):
            coordinator = runtime.coordinator
            if _normalize_address(coordinator.device_address) == wanted:
                return coordinator
    raise ValueError(
        f"Hello Fairy device {address!r} is not configured. Add it in Settings > Devices & services first."
    )


def _normalize_color(value: Any) -> int:
    """Convert service input to the controller's one-byte DIY color."""
    if isinstance(value, bool):
        raise ValueError("boolean is not a valid pixel color")

    if isinstance(value, int):
        return validate_color_byte(value)

    if isinstance(value, (list, tuple)) and len(value) == 3:
        if any(type(v) is not int or not 0 <= v <= 255 for v in value):
            raise ValueError("RGB channels must be integers 0..255")
        r, g, b = value
        return rgb_to_pixel_byte(r, g, b)

    if isinstance(value, str):
        text = value.strip().lower()
        named = {
            "off": PIXEL_OFF,
            "black": PIXEL_OFF,
            "white": 0xFF,
            "red": rgb_to_pixel_byte(255, 0, 0),
            "green": rgb_to_pixel_byte(0, 255, 0),
            "blue": rgb_to_pixel_byte(0, 0, 255),
            "yellow": rgb_to_pixel_byte(255, 255, 0),
            "orange": rgb_to_pixel_byte(255, 128, 0),
            "purple": rgb_to_pixel_byte(128, 0, 255),
            "pink": rgb_to_pixel_byte(255, 0, 128),
        }
        if text in named:
            return named[text]

        if text.startswith("#"):
            text = text[1:]
        if len(text) == 6:
            try:
                r = int(text[0:2], 16)
                g = int(text[2:4], 16)
                b = int(text[4:6], 16)
            except ValueError as err:
                raise ValueError(f"invalid hex RGB color: {value!r}") from err
            return rgb_to_pixel_byte(r, g, b)

    raise ValueError(
        "pixel colors must be a supported device byte (0..180, 254, 255), [r,g,b], #RRGGBB, or a basic color name"
    )


def _normalize_frame(values: list[Any], expected: int) -> list[int]:
    if not isinstance(values, (list, tuple)):
        raise ValueError("pixels must be a list of colors")
    if len(values) != expected:
        raise ValueError(f"expected {expected} pixels, got {len(values)}")
    return [_normalize_color(value) for value in values]


def _service_handler(handler):
    """Turn expected validation/transport errors into normal HA action errors."""

    @wraps(handler)
    async def wrapped(call):
        try:
            return await handler(call)
        except ValueError as err:
            raise ServiceValidationError(str(err)) from err
        except (ConnectionError, TimeoutError, RuntimeError, BleakError) as err:
            raise HomeAssistantError(str(err)) from err

    return wrapped


async def _stop_playlist(hass: HomeAssistant) -> None:
    """Prevent background playback from overwriting a deliberate Studio action."""
    if hass.services.has_service(DOMAIN, "stop_playlist"):
        await hass.services.async_call(DOMAIN, "stop_playlist", {}, blocking=True)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up domain-level DIY services."""

    @_service_handler
    async def handle_enter_draw_mode(call: ServiceCall) -> None:
        coordinator = _coordinator_for_address(hass, call.data[ATTR_ADDRESS])
        await _stop_playlist(hass)
        await coordinator.enter_draw_mode()

    @_service_handler
    async def handle_clear_matrix(call: ServiceCall) -> None:
        coordinator = _coordinator_for_address(hass, call.data[ATTR_ADDRESS])
        await _stop_playlist(hass)
        await coordinator.clear_pixels()

    @_service_handler
    async def handle_set_pixel(call: ServiceCall) -> None:
        coordinator = _coordinator_for_address(hass, call.data[ATTR_ADDRESS])
        has_rgb = ATTR_RGB in call.data
        has_byte = ATTR_COLOR_BYTE in call.data
        if has_rgb == has_byte:
            raise ValueError("provide exactly one of rgb or color_byte")

        if has_rgb:
            rgb = call.data[ATTR_RGB]
            color = _normalize_color(rgb)
        else:
            color = validate_color_byte(call.data[ATTR_COLOR_BYTE])

        await _stop_playlist(hass)
        await coordinator.set_pixel(call.data[ATTR_X], call.data[ATTR_Y], color)

    @_service_handler
    async def handle_set_frame(call: ServiceCall) -> None:
        coordinator = _coordinator_for_address(hass, call.data[ATTR_ADDRESS])
        pixels = _normalize_frame(call.data[ATTR_PIXELS], PIXEL_COUNT)
        await _stop_playlist(hass)
        await coordinator.set_frame(pixels)

    @_service_handler
    async def handle_two_picture_animation(call: ServiceCall) -> None:
        if call.data.get("experimental") is not True:
            raise ValueError("experimental must be true for capture-derived playback")
        values = call.data["frames"]
        if not isinstance(values, list) or len(values) != 2:
            raise ValueError("exactly two pictures are required")
        frames = [_normalize_frame(frame, PIXEL_COUNT) for frame in values]
        coordinator = _coordinator_for_address(hass, call.data[ATTR_ADDRESS])
        await _stop_playlist(hass)
        await coordinator.set_two_picture_animation(frames)

    @_service_handler
    async def handle_diy_playback(call: ServiceCall) -> None:
        data = call.data
        build_playback_commands(data["kind"], data["movement"], data["speed"], data["brightness"])
        coordinator = _coordinator_for_address(hass, data[ATTR_ADDRESS])
        await _stop_playlist(hass)
        await coordinator.set_diy_playback(
            data["kind"], data["movement"], data["speed"], data["brightness"]
        )

    @_service_handler
    async def handle_set_virtual_frame(call: ServiceCall) -> None:
        addresses = [_normalize_address(a) for a in call.data[ATTR_ADDRESSES]]
        if len(set(addresses)) != len(addresses):
            raise ValueError("addresses must be unique and ordered left-to-right")

        coordinators = [_coordinator_for_address(hass, a) for a in addresses]
        virtual_pixel_count = PIXEL_COUNT * len(coordinators)
        pixels = _normalize_frame(call.data[ATTR_PIXELS], virtual_pixel_count)
        frames = split_virtual_frame(pixels, len(coordinators))

        await _stop_playlist(hass)
        for coordinator, frame in zip(coordinators, frames, strict=True):
            await coordinator.set_frame(frame)

    @_service_handler
    async def handle_test_pattern(call: ServiceCall) -> None:
        coordinator = _coordinator_for_address(hass, call.data[ATTR_ADDRESS])
        pixels = [PIXEL_OFF] * PIXEL_COUNT

        # Border plus four distinctive corner colors. This is intentionally
        # simple and makes orientation/mirroring obvious on the physical curtain.
        for y in range(MATRIX_HEIGHT):
            for x in range(MATRIX_WIDTH):
                if x in (0, MATRIX_WIDTH - 1) or y in (0, MATRIX_HEIGHT - 1):
                    pixels[y * MATRIX_WIDTH + x] = 0xFF

        pixels[0] = rgb_to_pixel_byte(255, 0, 0)  # top-left red
        pixels[MATRIX_WIDTH - 1] = rgb_to_pixel_byte(0, 255, 0)  # top-right green
        pixels[(MATRIX_HEIGHT - 1) * MATRIX_WIDTH] = rgb_to_pixel_byte(
            0, 0, 255
        )  # bottom-left blue
        pixels[-1] = 0xFF  # bottom-right white
        await _stop_playlist(hass)
        await coordinator.set_frame(pixels)

    hass.services.async_register(
        DOMAIN, SERVICE_ENTER_DRAW_MODE, handle_enter_draw_mode, schema=ADDRESS_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_CLEAR_MATRIX, handle_clear_matrix, schema=ADDRESS_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_SET_PIXEL, handle_set_pixel, schema=SET_PIXEL_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_SET_FRAME, handle_set_frame, schema=SET_FRAME_SCHEMA
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_VIRTUAL_FRAME,
        handle_set_virtual_frame,
        schema=SET_VIRTUAL_FRAME_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_TEST_PATTERN, handle_test_pattern, schema=TEST_PATTERN_SCHEMA
    )

    hass.services.async_register(
        DOMAIN,
        "set_two_picture_animation",
        handle_two_picture_animation,
        schema=TWO_PICTURE_SCHEMA,
    )

    hass.services.async_register(
        DOMAIN, "set_diy_playback", handle_diy_playback, schema=PLAYBACK_SCHEMA
    )

    await async_setup_studio(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Set up Hello Fairy integration from a config entry."""

    coordinator = HelloFairyCoordinator(hass, config_entry)
    await coordinator.async_config_entry_first_refresh()

    cancel_update_listener = config_entry.add_update_listener(_async_update_listener)
    config_entry.runtime_data = RuntimeData(coordinator, cancel_update_listener)

    try:
        await hass.config_entries.async_forward_entry_setups(config_entry, PLATFORMS)
    except BaseException:
        cancel_update_listener()
        config_entry.runtime_data = None
        await coordinator.async_shutdown()
        raise
    try:
        await async_register_studio_panel(hass)
    except Exception:
        _LOGGER.exception(
            "Curtain Studio could not register; standard light controls remain available"
        )
    _LOGGER.info(
        "Hello Fairy integration 2.0.0 loaded; experimental two-picture playback; connection retries and static protocol preserved"
    )
    return True


async def _async_update_listener(hass: HomeAssistant, config_entry: ConfigEntry):
    await hass.config_entries.async_reload(config_entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Unload entities, release BLE connection, and remove the last panel."""
    if not await hass.config_entries.async_unload_platforms(config_entry, PLATFORMS):
        return False
    await _stop_playlist(hass)
    runtime = config_entry.runtime_data
    runtime.cancel_update_listener()
    try:
        await runtime.coordinator.async_shutdown()
    finally:
        config_entry.runtime_data = None
        async_remove_studio_if_unused(hass)
    return True
