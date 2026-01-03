"""Hello Fairy BLE API for controlling fairy lights via Bluetooth Low Energy.

This module provides the HelloFairyAPI class which implements the BLE protocol
for communicating with Hello Fairy smart lights, including:
- Power control (on/off)
- Color setting (RGB/HSV)
- Brightness control
- Preset effects
- Status monitoring via notifications
"""

import asyncio
import colorsys
import logging
import contextlib
from collections.abc import Callable

import bleak_retry_connector
from bleak import BleakClient, BleakError
from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak.backends.device import BLEDevice

from .const import (
    COMMAND_CHARACTERISTIC_UUID,
    NOTIFY_CHARACTERISTIC_UUID,
    CMD_PREFIX,
    CMD_POWER,
    CMD_COLOR_PRESET,
    MODE_COLOR,
    MODE_PRESET,
    EFFECT_PRESETS,
)

_LOGGER = logging.getLogger(__name__)


class HelloFairyAPI:
    """Hello Fairy BLE API implementation based on protocol from esphome fairy.yaml."""

    def __init__(
        self, ble_device: BLEDevice, update_callback: Callable[[], None]
    ) -> None:
        """Initialize Hello Fairy API.

        Args:
            ble_device: The BLE device to connect to
            update_callback: Callback function for device state updates
        """
        self._ble_device = ble_device
        self._client = None
        self._update_callback = update_callback
        self._ack_received = True
        self._notify_only = False

        # Device state
        self.state: bool | None = None
        self.brightness: int | None = None  # 0-100
        self.color: tuple[int, int, int] | None = None  # RGB (0-255)
        self.hsv: tuple[int, int, int] | None = None  # H(0-359), S(0-100), V(0-100)
        self.current_preset: int | None = None
        self.mode: int | None = None  # 1=color, 2=preset
        self.available_effects = list(EFFECT_PRESETS.keys())

    @property
    def address(self):
        return self._ble_device.address

    async def _ensure_connected(self) -> None:
        """Ensure we have a connected BLE client."""
        if self._client is None or not self._client.is_connected:
            await self._connect()

    async def _connect(self) -> None:
        """Connect to Hello Fairy device."""
        if self._client and self._client.is_connected:
            with contextlib.suppress(BleakError, TimeoutError):
                await self._client.disconnect()

        try:
            # Use bleak_retry_connector for robust connection handling
            self._client = await bleak_retry_connector.establish_connection(
                BleakClient, self._ble_device, self._ble_device.address
            )

            # Start notifications for status updates
            await self._client.start_notify(
                NOTIFY_CHARACTERISTIC_UUID, self._handle_notification
            )
        except (BleakError, TimeoutError) as err:
            self._client = None
            raise ConnectionError(
                f"Failed to connect to Hello Fairy device at {self._ble_device.address}: {err}"
            ) from err

    def _calculate_checksum(self, data: list) -> int:
        """Calculate simple sum checksum for Hello Fairy protocol."""
        return sum(data) % 256

    async def _send_command(self, command: list):
        """Send command to Hello Fairy device."""
        await self._ensure_connected()

        # Calculate and append checksum
        checksum = self._calculate_checksum(command)
        command.append(checksum)

        _LOGGER.debug("Sending command: %s", [f"{b:02x}" for b in command])

        await self._client.write_gatt_char(
            COMMAND_CHARACTERISTIC_UUID, bytes(command), False
        )
        self._ack_received = False

        # Wait for ACK response
        timeout = 5.0  # 5 second timeout
        elapsed = 0.0
        while not self._ack_received and elapsed < timeout:
            await asyncio.sleep(0.1)
            elapsed += 0.1

        if not self._ack_received:
            raise TimeoutError(f"No ACK received for command after {timeout} seconds")

    async def _handle_notification(
        self, characteristic: BleakGATTCharacteristic, data: bytearray
    ):
        """Handle notifications from Hello Fairy device."""
        _LOGGER.debug("Received notification: %s", [f"{b:02x}" for b in data])

        if len(data) == 4:  # ACK2 or ACK3
            _LOGGER.debug("Received ACK for command %d", data[1])
            self._ack_received = True
            # Tell coordinator to update state after ACK
            self._update_callback()
            return

        if len(data) < 12:
            _LOGGER.debug("Unknown response length: %d", len(data))
            return

        # Parse status notification
        # byte 6 is power state
        power_state = data[6] == 1
        self.state = power_state

        if not power_state:
            # Device is off
            self._update_callback()
            return

        # Parse mode and color/preset data
        mode = data[7]
        self.mode = mode

        if mode == 1:  # HSV color mode
            # bytes 8-9: H (0-359)
            # bytes 10-11: S (0-1000, scale to 0-100)
            # bytes 12-13: V (100-1000, scale to 0-100)
            h = (data[8] << 8) | data[9]
            s = ((data[10] << 8) | data[11]) // 10
            v = ((data[12] << 8) | data[13]) // 10

            self.hsv = (h, s, v)
            self.brightness = v

            # Convert HSV to RGB for Home Assistant
            r, g, b = colorsys.hsv_to_rgb(h / 360, s / 100, v / 100)
            self.color = (int(r * 255), int(g * 255), int(b * 255))

            _LOGGER.debug("Color mode - HSV: (%d,%d,%d), RGB: %s", h, s, v, self.color)

        elif mode == 2:  # Preset mode
            preset = data[8]
            bright = ((data[9] << 8) | data[10]) // 10

            self.current_preset = preset
            self.brightness = bright

            _LOGGER.debug("Preset mode - preset: %d, brightness: %d", preset, bright)

        self._update_callback()

    async def set_power(self, state: bool):
        """Turn Hello Fairy lights on/off."""
        if self.state == state:
            return

        command = [CMD_PREFIX, CMD_POWER, 0x01, 0x01 if state else 0x00]
        await self._send_command(command)

        # Update state immediately after successful ACK
        self.state = state
        if not state:
            # If turning off, clear color/brightness state
            self.brightness = None
            self.color = None
            self.hsv = None
            self.current_preset = None
            self.mode = None

    async def set_color_hsv(self, h: int, s: int, v: int):
        """Set color using HSV values.

        Args:
            h: 0-359 degrees
            s: 0-100 percent
            v: 0-100 percent
        """
        if not self.state:
            await self.set_power(True)
            await asyncio.sleep(0.1)  # Wait for power on

        # Ensure we're in the right ranges
        h = max(0, min(359, h))
        s = max(0, min(100, s))
        v = max(0, min(100, v))

        command = [
            CMD_PREFIX,
            CMD_COLOR_PRESET,
            0x07,
            MODE_COLOR,
            h >> 8,
            h & 0xFF,  # H (2 bytes)
            (s * 10) >> 8,
            (s * 10) & 0xFF,  # S (2 bytes, 0-1000)
            (v * 10) >> 8,
            (v * 10) & 0xFF,  # V (2 bytes, 0-1000)
        ]

        await self._send_command(command)

        # Update state immediately after successful ACK
        self.hsv = (h, s, v)
        self.brightness = v
        self.mode = MODE_COLOR
        self.current_preset = None
        # Convert HSV to RGB for Home Assistant
        r, g, b = colorsys.hsv_to_rgb(h / 360, s / 100, v / 100)
        self.color = (int(r * 255), int(g * 255), int(b * 255))

    async def set_color_rgb(self, r: int, g: int, b: int):
        """Set color using RGB values (0-255)."""
        # Convert RGB to HSV
        h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
        h_deg = int(h * 360)
        s_pct = int(s * 100)
        v_pct = (
            int(v * 100) if v > 0 else (self.brightness or 50)
        )  # Maintain brightness

        await self.set_color_hsv(h_deg, s_pct, v_pct)

    async def set_brightness(self, brightness: int):
        """Set brightness (0-100)."""
        if not self.state:
            return

        brightness = max(0, min(100, brightness))

        if self.hsv:
            # Update current color with new brightness
            h, s, _ = self.hsv
            await self.set_color_hsv(h, s, brightness)
        else:
            # If no color set, use white
            await self.set_color_hsv(0, 0, brightness)

    async def set_preset(self, preset: int):
        """Set preset effect (1-58)."""
        if not self.state:
            await self.set_power(True)
            await asyncio.sleep(0.1)

        preset = max(1, min(58, preset))
        brightness = self.brightness or 50

        command = [
            CMD_PREFIX,
            CMD_COLOR_PRESET,
            0x04,
            MODE_PRESET,
            preset,
            (brightness * 10) >> 8,
            (brightness * 10) & 0xFF,
        ]

        await self._send_command(command)

        # Update state immediately after successful ACK
        self.current_preset = preset
        self.brightness = brightness
        self.mode = MODE_PRESET
        # Clear color state when in preset mode
        self.color = None
        self.hsv = None

    async def set_effect(self, effect_name: str):
        """Set effect by name."""
        if effect_name in EFFECT_PRESETS:
            preset_num = EFFECT_PRESETS[effect_name]
            await self.set_preset(preset_num)
        else:
            _LOGGER.warning("Unknown effect: %s", effect_name)

    async def request_status(self):
        """Request current status from device."""
        # Hello Fairy protocol doesn't seem to have explicit status request
        # Status is received via notifications
        pass

    def get_available_effects(self) -> list:
        """Get list of available effects."""
        return list(EFFECT_PRESETS.keys())

    async def disconnect(self) -> None:
        """Disconnect from the device."""
        if self._client and self._client.is_connected:
            try:
                await self._client.stop_notify(NOTIFY_CHARACTERISTIC_UUID)
                await self._client.disconnect()
            except Exception:  # Ignore in cleanup
                pass
            finally:
                self._client = None
