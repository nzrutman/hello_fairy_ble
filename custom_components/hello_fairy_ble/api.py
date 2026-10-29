"""Hello Fairy BLE API for controlling fairy lights via Bluetooth Low Energy.

This module provides the HelloFairyAPI class which implements the BLE protocol
for communicating with Hello Fairy smart lights, including:
- Power control (on/off)
- Color setting (RGB/HSV)
- Brightness control
- Preset effects
- Status monitoring via notifications

Also supports guarded curtain DIY transfers, connection recovery, native
curtain controls and timestamped Curtain Studio status.
"""

from __future__ import annotations

import asyncio
import colorsys
import copy
import logging
from collections.abc import Callable, Sequence

import bleak_retry_connector
from bleak import BleakClient, BleakError
from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak.backends.device import BLEDevice
from homeassistant.util import dt as dt_util

from .animation_protocol import build_two_picture_sequence
from .const import (
    CMD_COLOR_PRESET,
    CMD_POWER,
    CMD_PREFIX,
    COMMAND_CHARACTERISTIC_UUID,
    EFFECT_PRESETS,
    MODE_COLOR,
    MODE_PRESET,
    NOTIFY_CHARACTERISTIC_UUID,
)
from .diy_controls import build_playback_commands, decode_device_info, decode_status
from .native import NativeControls
from .native_capabilities import decode_extensions
from .native_effects import decode_music_status
from .pixel_protocol import (
    PIXEL_COUNT,
    PIXEL_OFF,
    build_d0_packet,
    build_draw_mode_packet,
    build_packet,
    iter_pixel_update_packets,
    rgb_to_pixel_byte,
    row_major_frame_to_updates,
    validate_color_byte,
)

_LOGGER = logging.getLogger(__name__)

PATCH_VERSION = "2.0.0"
PIXEL_WRITE_DELAY = 0.30  # Capture: successive DA writes 298..309 ms apart.
DRAW_MODE_SETTLE_DELAY = 0.25  # Capture: D0(00) to first DA = 250.990 ms.
REQUIRED_DA_BYTES = 242  # AA DA EE 01 + 79 indexed triplets + checksum
REQUIRED_ATT_MTU = REQUIRED_DA_BYTES + 3


class HelloFairyAPI(NativeControls):
    """Hello Fairy BLE API implementation based on protocol from esphome fairy.yaml."""

    def __init__(self, ble_device: BLEDevice | None, update_callback: Callable[[], None]) -> None:
        """Initialize Hello Fairy API.

        Args:
            ble_device: The BLE device to connect to, if already discovered
            update_callback: Callback function for device state updates
        """
        self._ble_device = ble_device
        self._client: BleakClient | None = None
        self._diy_transfer_client: BleakClient | None = None
        self._verified_diy_client: BleakClient | None = None
        self._verified_diy_source: str | None = None
        # Retain a client whose teardown failed, so a later command cannot
        # silently open another connection while the old one is unaccounted for.
        self._cleanup_pending: BleakClient | None = None
        _LOGGER.info("Hello Fairy API %s loaded", PATCH_VERSION)
        self._update_callback = update_callback

        # Serialize GATT writes. This is especially important for full-frame DIY
        # uploads, which consist of many DA writes and must not be interleaved
        # with power/color/preset commands.
        self._command_lock = asyncio.Lock()
        self._init_native()
        self._last_upload: dict | None = None
        self._last_playback: dict | None = None
        self._reported_status: dict | None = None
        self._device_info: dict | None = None
        self._info_client: BleakClient | None = None
        self._info_event = asyncio.Event()
        self._status_event = asyncio.Event()
        self._ack_event = asyncio.Event()
        self._ack_event.set()
        self._expected_ack_cmd: int | None = None
        # Tracks whether this API instance has successfully entered DIY mode.
        self._in_draw_mode = False
        # Deterministic local frame buffer: the Android app uploads an entire
        # frame before its D0 finish/apply sequence. Initial state is ALL OFF.
        self._diy_frame: list[int] = [PIXEL_OFF] * PIXEL_COUNT

        # Device state
        self.state: bool | None = None
        self.brightness: int | None = None  # 0-100
        self.color: tuple[int, int, int] | None = None  # RGB (0-255)
        self.hsv: tuple[int, int, int] | None = None  # H(0-359), S(0-100), V(0-100)
        self.current_preset: int | None = None
        self.mode: int | None = None  # 1=color, 2=preset, 3=music
        self.available_effects = list(EFFECT_PRESETS.keys())

    @property
    def address(self):
        return self._ble_device.address if self._ble_device else None

    @property
    def is_discovered(self) -> bool:
        """Return True if the BLE device has been seen."""
        return self._ble_device is not None

    def set_ble_device(self, ble_device: BLEDevice) -> None:
        """Update the BLE device once it has been (re)discovered."""
        self._ble_device = ble_device

    async def _ensure_connected(self) -> None:
        """Ensure we have a connected BLE client."""
        if self._ble_device is None:
            raise ConnectionError("Hello Fairy device has not been discovered yet")
        if self._client is None or not self._client.is_connected:
            await self._connect()

    async def _disconnect_transport_locked(self) -> None:
        """Invalidate verification and release the owned client, even after setup failure."""
        client = self._client if self._client is not None else self._cleanup_pending
        self._client = None
        self._verified_diy_client = None
        self._verified_diy_source = None
        self._info_client = None
        self._reset_native_session()
        self._in_draw_mode = False
        if client is None:
            return
        self._cleanup_pending = client
        # Keep the pending reference if disconnect fails, times out or is cancelled.
        async with asyncio.timeout(10):
            await client.disconnect()
        self._cleanup_pending = None

    async def _connect(self, *, use_services_cache: bool = True) -> None:
        """Retry setup only, before the caller can issue any device commands.

        Each attempt owns cleanup. Never retry an image, ACK timeout or capacity
        rejection here. All callers already hold the command lock.
        """
        for attempt in range(1, 4):
            try:
                async with asyncio.timeout(15):
                    await self._connect_once(use_services_cache=use_services_cache)
            except (ConnectionError, TimeoutError) as err:
                # _connect_once wraps BLE/timeout failures. Programming errors,
                # failed teardown and cancellation must not be retried.
                recoverable = isinstance(err, TimeoutError) or isinstance(
                    err.__cause__, (BleakError, TimeoutError)
                )
                if (
                    not recoverable
                    or self._cleanup_pending is not None
                    or self._client is not None
                    or attempt == 3
                ):
                    _LOGGER.warning(
                        "%s connection setup stopped for %s after %d attempt(s); "
                        "cleanup_pending=%s: %s",
                        PATCH_VERSION,
                        self.address,
                        attempt,
                        self._cleanup_pending is not None,
                        err,
                    )
                    if recoverable and attempt == 3:
                        raise ConnectionError(
                            f"Hello Fairy connection setup failed after 3 attempts "
                            f"at {self.address}: {err}"
                        ) from err
                    raise
                delay = 2.0 * attempt
                _LOGGER.debug(
                    "%s connection setup attempt %d/3 failed for %s; "
                    "retrying in %.1fs before device commands: %s",
                    PATCH_VERSION,
                    attempt,
                    self.address,
                    delay,
                    err,
                )
                await asyncio.sleep(delay)
            else:
                if attempt > 1:
                    _LOGGER.debug(
                        "%s connection setup recovered for %s on attempt %d/3",
                        PATCH_VERSION,
                        self.address,
                        attempt,
                    )
                return

    async def _connect_once(self, *, use_services_cache: bool = True) -> None:
        if self._ble_device is None:
            raise ConnectionError("Hello Fairy device has not been discovered yet")
        if self._client is not None or self._cleanup_pending is not None:
            try:
                await self._disconnect_transport_locked()
            except (BleakError, TimeoutError) as err:
                raise ConnectionError(
                    f"Previous Hello Fairy connection at {self.address} could not be released; "
                    "no replacement connection or device commands attempted"
                ) from err
        self._verified_diy_client = None
        self._verified_diy_source = None
        self._info_client = None
        stage = "BLE connect"
        try:
            # Use bleak_retry_connector for robust connection handling
            self._client = await bleak_retry_connector.establish_connection(
                BleakClient,
                self._ble_device,
                self._ble_device.address,
                use_services_cache=use_services_cache,
                max_attempts=1,
            )
            # Start notifications for status updates
            stage = "notification subscription"
            subscribed_client = self._client

            async def notification(sender, data):
                # A queued reply from a released link must never grant a
                # capability or satisfy a waiter on its replacement connection.
                if self._client is subscribed_client and subscribed_client.is_connected:
                    await self._handle_notification(sender, data)

            await subscribed_client.start_notify(NOTIFY_CHARACTERISTIC_UUID, notification)
        except asyncio.CancelledError:
            if self._client is not None:
                try:
                    await self._disconnect_transport_locked()
                except Exception:
                    _LOGGER.warning(
                        "%s cancelled setup cleanup failed for %s",
                        PATCH_VERSION,
                        self.address,
                        exc_info=True,
                    )
            raise
        except Exception as err:
            cleanup_failed = False
            if self._client is not None:
                try:
                    await self._disconnect_transport_locked()
                except Exception:
                    cleanup_failed = True
                    _LOGGER.warning(
                        "%s failed setup cleanup remains pending for %s",
                        PATCH_VERSION,
                        self.address,
                        exc_info=True,
                    )
            _LOGGER.debug(
                "%s connection failed at %s for %s; no image packets sent; cleanup_pending=%s",
                PATCH_VERSION,
                stage,
                self.address,
                cleanup_failed,
            )
            if isinstance(err, (BleakError, TimeoutError)):
                raise ConnectionError(
                    f"Failed to connect to Hello Fairy device at {self.address} "
                    f"during {stage}: {err}"
                    + ("; connection cleanup remains pending" if cleanup_failed else "")
                ) from err
            raise

    @staticmethod
    def _calculate_checksum(data: Sequence[int]) -> int:
        """Calculate simple sum checksum for Hello Fairy protocol."""
        return sum(data) % 256

    async def _write_packet_locked(self, packet: bytes, *, expect_ack: bool = False) -> None:
        """Write one already-framed packet while caller holds _command_lock."""
        if self._diy_transfer_client is not None:
            if self._client is not self._diy_transfer_client or not self._client.is_connected:
                raise ConnectionError(
                    "DIY connection lost; transfer aborted without reconnect/replay"
                )
        else:
            await self._ensure_connected()
        assert self._client is not None

        if expect_ack:
            self._expected_ack_cmd = packet[1]
            self._ack_event.clear()

        try:
            _LOGGER.debug("Sending packet: %s", packet.hex(" "))
            await self._client.write_gatt_char(COMMAND_CHARACTERISTIC_UUID, packet, response=False)
            if expect_ack:
                # Wait for ACK response
                try:
                    await asyncio.wait_for(self._ack_event.wait(), timeout=5.0)
                except TimeoutError as err:
                    raise TimeoutError(
                        f"No ACK received for command 0x{packet[1]:02x} after 5 seconds"
                    ) from err
        finally:
            if expect_ack:
                self._expected_ack_cmd = None

    async def _send_command(self, command: list[int]) -> None:
        """Send an existing AA-prefixed command and wait for its ACK."""
        # Calculate and append checksum
        packet = bytes([*command, self._calculate_checksum(command)])
        async with self._command_lock:
            await self._write_packet_locked(packet, expect_ack=True)

    async def _handle_notification(self, characteristic: BleakGATTCharacteristic, data: bytearray):
        """Handle notifications from Hello Fairy device."""
        _LOGGER.debug("Received notification: %s", bytes(data).hex(" "))

        if len(data) == 4 and (
            data[0] == CMD_PREFIX and data[2] == 0 and data[3] == self._calculate_checksum(data[:3])
        ):
            # Existing controllers ACK power as AA 02 00 AC and color/preset as
            # AA 03 00 AD. Only satisfy the waiter when the ACK command matches,
            # so a delayed DIY notification cannot release an unrelated command.
            ack_cmd = data[1]
            _LOGGER.debug("Received ACK for command 0x%02x", ack_cmd)
            if self._expected_ack_cmd is None or ack_cmd == self._expected_ack_cmd:
                self._ack_event.set()
            self._update_callback()
            return

        if self._handle_native_notification(bytes(data)):
            return
        info = decode_device_info(bytes(data))
        if info is not None:
            if self._native_client is not self._client:
                self._reset_native_session()
                self._native_client = self._client
            self._device_info = info
            self._native_extensions = decode_extensions(bytes(data))
            self._info_client = self._client
            self._info_event.set()
            return
        info = self._device_info or {}
        curtain_units = self._info_client is self._client and (
            info.get("led_count"),
            info.get("columns"),
            info.get("rows"),
            info.get("diy_type"),
        ) == (400, 20, 20, 3)
        # Preserve legacy device scaling unless this exact link reported the
        # known curtain profile. Studio and the HA entity share this decoder.
        report = decode_status(bytes(data), scene_divisor=1 if curtain_units else 10)
        if report is None:
            return
        music = decode_music_status(bytes(data))
        if report.get("mode") == 3 and curtain_units and music is None:
            return
        if music is not None:
            report.update(music)
        report["received_at"] = dt_util.utcnow().isoformat()
        self._reported_status = report
        self._status_event.set()
        self.state = report["power"]
        self.mode = report["mode"]
        if "brightness_percent" in report:
            self.brightness = round(report["brightness_percent"])
        # Parse mode and color/preset data
        if self.mode == MODE_COLOR and "hue" in report:  # HSV color mode
            h, saturation, value = (
                report["hue"],
                report["saturation_raw"] / 10,
                report["brightness_raw"] / 10,
            )
            self.hsv = (h, round(saturation), round(value))
            self.color = tuple(
                round(c * 255) for c in colorsys.hsv_to_rgb(h / 360, saturation / 100, value / 100)
            )
            self.current_preset = None
        elif self.mode == MODE_PRESET:  # Preset mode
            self.current_preset = report.get("scene")
            self.color = None
            self.hsv = None
        self._update_callback()

    async def set_power(self, state: bool):
        """Turn Hello Fairy lights on/off."""
        if self.state == state:
            return

        command = [CMD_PREFIX, CMD_POWER, 0x01, 0x01 if state else 0x00]
        await self._send_command(command)

        # Update state immediately after successful ACK
        self.state = state
        self._in_draw_mode = False
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
        self._in_draw_mode = False
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
        v_pct = int(v * 100) if v > 0 else (self.brightness or 50)  # Maintain brightness
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
        self._in_draw_mode = False
        # Clear color state when in preset mode
        self.color = None
        self.hsv = None

    async def set_effect(self, effect_name: str):
        """Set effect by name."""
        if effect_name in EFFECT_PRESETS:
            await self.set_preset(EFFECT_PRESETS[effect_name])
        else:
            _LOGGER.warning("Unknown effect: %s", effect_name)

    # ---------------------------------------------------------------------
    # DIY / 20x20 curtain matrix support
    # ---------------------------------------------------------------------

    async def _enter_draw_mode_locked(self) -> None:
        """Enter drawing mode while holding the BLE command lock.

        DIY mode (D0) sends an ACK. Waiting for it is essential: the v0.1
        implementation sent D1 just 16 ms later, before the D0 ACK arrived.
        """
        if self._in_draw_mode:
            return
        await self._write_packet_locked(build_draw_mode_packet(), expect_ack=True)
        # Allow the controller to switch modes after emitting its D0 ACK.
        await asyncio.sleep(DRAW_MODE_SETTLE_DELAY)
        self._in_draw_mode = True
        _LOGGER.debug("DIY draw mode ready after D0 ACK")

    async def enter_draw_mode(self) -> None:
        """Put a 400-pixel curtain into DIY/drawing mode."""
        async with self._command_lock:
            await self._prepare_diy_locked()
            if not self.state:
                await self._write_packet_locked(bytes.fromhex("aa020101ae"), expect_ack=True)
                self.state = True
                await asyncio.sleep(0.1)
            # Explicit request resets the mode even if our cache thinks it is set.
            self._in_draw_mode = False
            await self._enter_draw_mode_locked()

    async def _read_device_info_locked(self) -> None:
        """Read GetDeviceInfo once for this exact connection."""
        assert self._client is not None
        if self._info_client is self._client:
            return
        self._info_event.clear()
        await self._write_packet_locked(build_packet(0x00, []))
        try:
            await asyncio.wait_for(self._info_event.wait(), timeout=5)
        except TimeoutError as err:
            raise RuntimeError(
                "Device capabilities could not be read; standard light controls remain available"
            ) from err

    async def _verify_diy_device_locked(self) -> None:
        """Fail closed before sending model-specific writes to another device."""
        await self._read_device_info_locked()
        info = self._device_info or {}
        if (info.get("led_count"), info.get("columns"), info.get("rows"), info.get("diy_type")) != (
            400,
            20,
            20,
            3,
        ):
            raise RuntimeError(
                "DIY blocked: only a device-reported 400-LED 20x20 DIY type 3 curtain is supported; standard light controls remain available"
            )

    def _check_diy_capacity_locked(self, *, fresh: bool) -> str:
        """Inspect the exact current connection; never infer capacity from an old client."""
        assert self._client is not None
        current_source = getattr(getattr(self._client, "_connected_scanner", None), "source", None)
        if current_source is None:
            raise RuntimeError(
                "DIY preflight: active HA adapter/proxy source unavailable; no DIY writes sent"
            )
        char = self._client.services.get_characteristic(COMMAND_CHARACTERISTIC_UUID)
        if char is None:
            raise RuntimeError("DIY preflight: command characteristic is missing")
        try:
            mtu = self._client.mtu_size
            capacity = char.max_write_without_response_size
        except (AttributeError, NotImplementedError) as err:
            raise RuntimeError(
                "DIY preflight: transport capacity unavailable; no DIY writes sent"
            ) from err
        backend = getattr(self._client, "_backend", None)
        backend_name = f"{type(backend).__module__}.{type(backend).__name__}"
        _LOGGER.debug(
            "%s DIY preflight address=%s backend=%s source=%s fresh_cache=%s connection=%s "
            "mtu=%s max_write_without_response=%s handle=0x%04x properties=%s "
            "required_value=%d required_mtu=%d",
            PATCH_VERSION,
            self.address,
            backend_name,
            current_source,
            fresh,
            "fresh" if fresh else "reused-verified",
            mtu,
            capacity,
            char.handle,
            char.properties,
            REQUIRED_DA_BYTES,
            REQUIRED_ATT_MTU,
        )
        if (
            "write-without-response" not in char.properties
            or not isinstance(mtu, int)
            or mtu < REQUIRED_ATT_MTU
            or not isinstance(capacity, int)
            or capacity < REQUIRED_DA_BYTES
        ):
            raise RuntimeError(
                f"{PATCH_VERSION}: DIY blocked before D0/DA: mtu={mtu}, "
                f"write_without_response={capacity}, properties={char.properties}; "
                f"need MTU >= {REQUIRED_ATT_MTU} and value >= {REQUIRED_DA_BYTES}. "
                "No small-packet fallback. A reported 23 may remain inconclusive; "
                "check uncached proxy negotiation logs or use a direct BLE adapter."
            )

        return current_source

    async def _prepare_diy_locked(self) -> None:
        """Verify a new connection once; reuse that exact live connection thereafter."""
        await self._ensure_connected()
        await self._verify_diy_device_locked()
        assert self._client is not None
        current_source = getattr(getattr(self._client, "_connected_scanner", None), "source", None)
        if self._verified_diy_client is self._client:
            if current_source != self._verified_diy_source:
                self._verified_diy_client = None
                self._verified_diy_source = None
                raise RuntimeError(
                    "DIY preflight: verified connection changed source; no DIY writes sent"
                )
            # No cache refresh, reconnect or CCCD subscription for a healthy
            # already-verified link. Public capacity and source are still checked.
            self._check_diy_capacity_locked(fresh=False)
            return
        if current_source is None:
            raise RuntimeError(
                "DIY preflight: active HA adapter/proxy source unavailable; no DIY writes sent"
            )
        clear_cache = getattr(self._client, "clear_cache", None)
        if not callable(clear_cache):
            raise RuntimeError(
                f"{PATCH_VERSION}: fresh DIY capacity cannot be verified: "
                "this HA BLE client has no clear_cache operation. No DIY writes sent."
            )
        if not await clear_cache():
            raise RuntimeError("DIY preflight: BLE cache clear failed; no DIY writes sent")
        original_source = current_source
        await self._disconnect_transport_locked()
        await self._connect(use_services_cache=False)
        assert self._client is not None
        current_source = getattr(getattr(self._client, "_connected_scanner", None), "source", None)
        if current_source != original_source:
            raise RuntimeError(
                "DIY preflight: HA changed adapter/proxy during refresh; capacity unverified, no DIY writes sent"
            )
        await self._verify_diy_device_locked()
        self._check_diy_capacity_locked(fresh=True)
        self._verified_diy_client = self._client
        self._verified_diy_source = current_source

    async def _upload_frame_locked(self, frame: Sequence[int]) -> None:
        """Send one guarded six-packet experiment; no automatic replay."""
        updates = row_major_frame_to_updates(frame)
        updates.sort(key=lambda p: p[0] * 20 + p[1])
        packets = list(iter_pixel_update_packets(updates))
        if [len(p) for p in packets] != [242, 242, 242, 242, 242, 20]:
            raise RuntimeError("DIY framing invariant failed before any device writes")
        await self._prepare_diy_locked()
        assert self._client is not None
        self._diy_transfer_client = self._client
        started = asyncio.get_running_loop().time()
        stage = "power"
        try:
            if not self.state:
                await self._write_packet_locked(bytes.fromhex("aa 02 01 01 ae"), expect_ack=True)
                self.state = True
                await asyncio.sleep(0.1)
            stage = "D0(03)/D0(00)"
            await self._write_packet_locked(build_d0_packet(0x03))
            await asyncio.sleep(0.0165)  # Capture: 16.482 ms between initialization writes.
            await self._write_packet_locked(build_d0_packet(0x00))
            await asyncio.sleep(DRAW_MODE_SETTLE_DELAY)
            for number, packet in enumerate(packets, 1):
                stage = f"DA {number}/6"
                _LOGGER.debug(
                    "DIY DA %d/6 bytes=%d first_index=%d elapsed=%.3fs",
                    number,
                    len(packet),
                    (number - 1) * 79,
                    asyncio.get_running_loop().time() - started,
                )
                await self._write_packet_locked(packet)
                if number < len(packets):
                    await asyncio.sleep(PIXEL_WRITE_DELAY)
            stage = "processing wait"
            await asyncio.sleep(1.20)
            stage = "D0(04)"
            await self._write_packet_locked(build_d0_packet(0x04))
            await asyncio.sleep(0.02)
            stage = "D0(01)"
            await self._write_packet_locked(build_d0_packet(0x01))
            await asyncio.sleep(0.20)
        except BaseException:
            self._verified_diy_client = None
            self._verified_diy_source = None
            _LOGGER.warning(
                "%s DIY aborted at %s; device image unknown; no retry/apply recovery",
                PATCH_VERSION,
                stage,
            )
            raise
        finally:
            self._diy_transfer_client = None
            self._in_draw_mode = False
        self._diy_frame = list(frame)
        self._last_upload = {
            "kind": "picture",
            "frames": [list(frame)],
            "sent_at": dt_util.utcnow().isoformat(),
            "source": "last_upload",
        }
        self._last_playback = None
        _LOGGER.debug(
            "%s six DA packets and finalization transmitted in %.3fs. "
            "Transport completion only; physical confirmation required.",
            PATCH_VERSION,
            asyncio.get_running_loop().time() - started,
        )

    async def set_two_picture_animation(self, frames: Sequence[Sequence[int]]) -> None:
        """Experimental two-slot upload; never reconnect or replay after writes start."""
        frames = tuple(tuple(frame) for frame in frames)
        sequence = build_two_picture_sequence(frames)  # Validate everything first.
        async with self._command_lock:
            await self._prepare_diy_locked()
            assert self._client is not None
            self._diy_transfer_client = self._client
            stage = "power"
            try:
                if not self.state:
                    await self._write_packet_locked(
                        bytes.fromhex("aa 02 01 01 ae"), expect_ack=True
                    )
                    self.state = True
                    await asyncio.sleep(0.1)
                for stage, packet, delay in sequence:
                    _LOGGER.debug(
                        "%s two-picture address=%s stage=%s bytes=%d",
                        PATCH_VERSION,
                        self.address,
                        stage,
                        len(packet),
                    )
                    await self._write_packet_locked(packet)
                    await asyncio.sleep(delay)
            except BaseException:
                self._verified_diy_client = None
                self._verified_diy_source = None
                _LOGGER.warning(
                    "%s two-picture aborted at %s for %s; no replay or playback recovery",
                    PATCH_VERSION,
                    stage,
                    self.address,
                )
                raise
            finally:
                self._diy_transfer_client = None
                self._in_draw_mode = False
            self._last_upload = {
                "kind": "animation",
                "frames": [list(f) for f in frames],
                "sent_at": dt_util.utcnow().isoformat(),
                "source": "last_upload",
            }
            self._last_playback = None
            _LOGGER.debug(
                "%s two-picture sequence transmitted for %s; native playback is experimental; "
                "physical confirmation required",
                PATCH_VERSION,
                self.address,
            )

    async def clear_pixels(self) -> None:
        """Upload one complete all-off frame after capacity preflight."""
        await self.set_frame([PIXEL_OFF] * PIXEL_COUNT)

    async def set_pixel(self, x: int, y: int, color_byte: int) -> None:
        await self.set_pixels([(x, y, color_byte)])

    async def set_pixel_rgb(self, x: int, y: int, r: int, g: int, b: int) -> None:
        await self.set_pixel(x, y, rgb_to_pixel_byte(r, g, b))

    async def set_pixels(
        self, updates: Sequence[tuple[int, int, int]], *, enter_draw_mode: bool = True
    ) -> None:
        """Serialize frame edits and only commit the local frame after transfer."""
        checked = []
        for x, y, color in updates:
            if (
                not isinstance(x, int)
                or not isinstance(y, int)
                or not 0 <= x < 20
                or not 0 <= y < 20
            ):
                raise ValueError("pixel position must be integer coordinates within 20x20")
            checked.append((x, y, validate_color_byte(color)))
        if not checked:
            return
        async with self._command_lock:
            revised = self._diy_frame.copy()
            for x, y, color in checked:
                revised[y * 20 + x] = color
            await self._upload_frame_locked(revised)

    async def set_frame(self, pixels: Sequence[int]) -> None:
        if len(pixels) != PIXEL_COUNT:
            raise ValueError(f"frame must contain exactly {PIXEL_COUNT} pixels")
        revised = [validate_color_byte(p) for p in pixels]
        async with self._command_lock:
            await self._upload_frame_locked(revised)

    @property
    def studio_snapshot(self) -> dict:
        """Uploaded pixels are history, never a claim about live device pixels."""
        return copy.deepcopy(
            {
                "connected": bool(self._client is not None and self._client.is_connected),
                "reported": self._reported_status,
                "last_upload": self._last_upload,
                "last_playback": self._last_playback,
                "pixel_readback": False,
                "native": self._native_snapshot(),
                "device_info": self._device_info,
                "diy_supported": self._device_info is not None
                and (
                    self._device_info.get("led_count"),
                    self._device_info.get("columns"),
                    self._device_info.get("rows"),
                    self._device_info.get("diy_type"),
                )
                == (400, 20, 20, 3),
            }
        )

    async def request_status(self) -> dict:
        """App GetDeviceStatusCmd (AA 01 00 AB); bounded, no image mutation."""
        async with self._command_lock:
            await self._ensure_connected()
            try:
                await self._read_device_info_locked()
            except RuntimeError:
                _LOGGER.debug("Device info unavailable; using legacy status scaling")
            self._status_event.clear()
            await self._write_packet_locked(build_packet(0x01, []))
            try:
                await asyncio.wait_for(self._status_event.wait(), timeout=5)
            except TimeoutError as err:
                raise TimeoutError(
                    "Curtain did not return a fresh status report; pixel readback is not supported by this integration"
                ) from err
            return copy.deepcopy(self._reported_status)

    async def set_diy_playback(self, kind: str, movement: str, speed: int, brightness: int) -> None:
        """APK Set_Picture_Parameter/DC controls; no frame re-upload or replay."""
        packets = build_playback_commands(kind, movement, speed, brightness)
        async with self._command_lock:
            if self._last_upload is None or self._last_upload["kind"] != kind:
                raise ValueError("Send this design first before applying its playback controls")
            await self._prepare_diy_locked()
            self._diy_transfer_client = self._client
            try:
                for packet in packets:
                    await self._write_packet_locked(packet)
                    await asyncio.sleep(0.20)
            except BaseException:
                self._verified_diy_client = None
                self._verified_diy_source = None
                self._last_playback = None
                raise
            finally:
                self._diy_transfer_client = None
            self._last_playback = {
                "kind": kind,
                "movement": movement,
                "speed": speed,
                "brightness": brightness,
                "sent_at": dt_util.utcnow().isoformat(),
                "source": "last_command",
            }

    def get_available_effects(self) -> list:
        """Get list of available effects."""
        return list(EFFECT_PRESETS.keys())

    async def disconnect(self) -> None:
        """Disconnect from the device."""
        async with self._command_lock:
            await self._disconnect_transport_locked()
