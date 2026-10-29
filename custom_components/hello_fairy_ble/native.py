"""Explicit, session-gated native controls; never run during setup or polling.

Generated with aurora@aurora-smart-home (ha-integration-dev skill)
https://github.com/tonylofgren/aurora-smart-home
"""

import asyncio
import copy
import logging

from homeassistant.util import dt as dt_util

from .const import COMMAND_CHARACTERISTIC_UUID, EFFECT_PRESETS
from .native_capabilities import is_researched_profile
from .native_effects import (
    build_music_command,
    build_scene_speed_command,
    build_scene_speed_query,
    decode_scene_speed,
)
from .native_text import build_text_capability_query, decode_text_capability
from .native_timers import (
    build_clock_sync,
    build_countdown,
    build_timer_query,
    build_timer_write,
    decode_timer_bank,
    local_timer,
)
from .native_validation import SCHEMAS

_LOGGER = logging.getLogger(__name__)


class NativeControls:
    """Mixin sharing the API's command lock and exact verified connection."""

    def _init_native(self):
        self._native_client = None
        self._native_font = None
        self._native_clock_expected = None
        self._native_extensions = {}
        self._native_events = {}
        self._native_pending = None
        self._native_speed = None
        self._native_history = None
        self._native_banks = {}

    def _reset_native_session(self):
        self._native_client = None
        self._native_font = None
        self._native_pending = None
        self._native_clock_expected = None
        for event in self._native_events.values():
            event.clear()
        self._native_speed = None
        self._native_banks = {}
        self._native_extensions = {}

    def _handle_native_notification(self, data: bytes) -> bool:
        speed = decode_scene_speed(data)
        if speed is not None and self._native_pending == 0x0C:
            self._native_speed = speed
            self._native_events[0x0C].set()
            return True
        font = decode_text_capability(data)
        if font is not None and self._native_pending == 0xDD:
            self._native_font = font
            self._native_events[0xDD].set()
            return True
        bank = decode_timer_bank(data)
        if bank is not None and self._native_pending == data[1]:
            self._native_banks[data[1]] = bank
            self._native_events[data[1]].set()
            return True
        if self._native_pending == 5 and data == self._native_clock_expected:
            self._native_events[5].set()
            return True
        return False

    @staticmethod
    def _native_offset():
        offset = dt_util.now().utcoffset()
        if offset is None or offset.total_seconds() % 60:
            raise ValueError("Home Assistant timezone must have a whole-minute UTC offset")
        return int(offset.total_seconds() // 60)

    def _timers_verified(self):
        return set(self._native_banks) == {6, 7} and all(
            not t["exists"] or t["number"] == t["slot"]
            for bank in self._native_banks.values()
            for t in bank
        )

    def _native_snapshot(self):
        fresh = bool(
            self._client is not None
            and self._client.is_connected
            and self._info_client is self._client
            and self._native_client is self._client
            and is_researched_profile(self._device_info)
        )
        return copy.deepcopy(
            {
                "profile_verified": fresh,
                "music_supported": fresh and self._native_extensions.get("music_mode") == 3,
                "scene_speed_supported": fresh and self._native_speed is not None,
                "scene_speed": self._native_speed if fresh else None,
                "timers_supported": fresh and self._timers_verified(),
                "timers": [
                    local_timer(t, self._native_offset())
                    for command in (6, 7)
                    for t in self._native_banks.get(command, [])
                ]
                if fresh
                else [],
                "utc_offset_minutes": self._native_offset(),
                "font_report": self._native_font if fresh else None,
                "last_command": self._native_history,
                "physical_confirmation_required": True,
                "unavailable": {
                    "pause": "App pause is used by other preset editors; support for this curtain is unproven.",
                    "scene_loop": "Captured curtain does not advertise the required loop capability.",
                    "extra_storage": "No verified storage-slot contract for this model.",
                    "native_text": "Text commands exist, but exact-model framing and support remain unconfirmed. Studio text remains available.",
                },
            }
        )

    async def _native_prepare_locked(self):
        await self._ensure_connected()
        if self._native_client is not self._client:
            self._reset_native_session()
            # A reconnect invalidates all capability grants from the old link.
            self._info_client = None
        await self._read_device_info_locked()
        if not is_researched_profile(self._device_info):
            raise ValueError(
                "New native controls require the researched 25025 / 4.6.0 / 20×20 curtain profile"
            )
        char = self._client.services.get_characteristic(COMMAND_CHARACTERISTIC_UUID)
        if char is None or "write-without-response" not in char.properties:
            raise ValueError(
                "Native controls require the command characteristic with write-without-response"
            )

    async def _native_write_locked(self, packet: bytes, *, expect_ack=False):
        # Every new native command fits the baseline ATT MTU23. Large image
        # packets continue to use the separate, existing 242-byte preflight.
        if len(packet) > 20:
            raise ValueError("Native command exceeds the safe baseline ATT payload")
        client = self._client
        self._diy_transfer_client = client
        try:
            await self._write_packet_locked(packet, expect_ack=expect_ack)
        finally:
            self._diy_transfer_client = None

    async def _native_query_locked(self, command: int, packet: bytes):
        event = self._native_events.setdefault(command, asyncio.Event())
        event.clear()
        self._native_pending = command
        try:
            await self._native_write_locked(packet)
            await asyncio.wait_for(event.wait(), timeout=3)
        except TimeoutError as err:
            raise TimeoutError(
                f"Curtain did not answer native command 0x{command:02x}. "
                "No command was retried; check the lights before sending again"
            ) from err
        finally:
            self._native_pending = None

    async def _native_read_status_locked(self):
        self._status_event.clear()
        await self._native_write_locked(bytes.fromhex("aa0100ab"))
        try:
            await asyncio.wait_for(self._status_event.wait(), timeout=5)
        except TimeoutError as err:
            raise TimeoutError(
                "Curtain did not return fresh status. No command was retried; check the lights"
            ) from err
        return self._reported_status

    async def _read_native_banks_locked(self):
        self._native_banks = {}
        for bank in (1, 2):
            await self._native_query_locked(5 + bank, build_timer_query(bank))
        if not self._timers_verified():
            self._native_banks = {}
            raise ValueError(
                "Timer slot numbering is inconsistent; schedule editing is unavailable"
            )

    async def inspect_native(self):
        """Explicit app discovery queries. No mode, clock or pixels change."""
        async with self._command_lock:
            await self._native_prepare_locked()
            self._native_speed = None
            self._native_font = None
            self._native_banks = {}
            for command, packet in (
                (0x0C, build_scene_speed_query()),
                (0xDD, build_text_capability_query()),
                (6, build_timer_query(1)),
                (7, build_timer_query(2)),
            ):
                try:
                    await self._native_query_locked(command, packet)
                except TimeoutError:
                    _LOGGER.debug(
                        "Native query 0x%02x did not answer; capability stays unavailable", command
                    )
            return self.studio_snapshot

    async def set_native(self, action: str, payload: dict):
        """One deliberate command, no write retry or optimistic readback."""
        if action not in SCHEMAS or action == "inspect":
            raise ValueError("Unsupported native action")
        payload = SCHEMAS[action](payload)
        # Complete pure validation before any radio query or write.
        packet = None
        if action == "music":
            if payload["mode"] == 1:
                payload["auto_color"] = True
            packet = build_music_command(
                **{k: v for k, v in payload.items() if k != "auto_color"},
                auto=payload["auto_color"],
            )
        elif action == "scene_speed":
            packet = build_scene_speed_command(payload["speed"])
        elif action == "clock_sync":
            packet = build_clock_sync(int(dt_util.utcnow().timestamp()), self._native_offset())
        elif action == "countdown":
            packet = build_countdown(**payload)
        elif action == "timer":
            packet = build_timer_write(**payload, utc_offset_minutes=self._native_offset())
        async with self._command_lock:
            await self._native_prepare_locked()
            if action == "music" and self._native_extensions.get("music_mode") != 3:
                raise ValueError("Curtain has not advertised its built-in microphone capability")
            if action == "scene_speed":
                if self._native_speed is None:
                    raise ValueError(
                        "Inspect native capabilities on this connection before setting scene speed"
                    )
                report = await self._native_read_status_locked()
                if report.get("mode") != 2 or report.get("scene") not in EFFECT_PRESETS.values():
                    raise ValueError(
                        "Select a built-in scene first; scene speed does not control DIY movement"
                    )
            if action == "timer":
                if not self._timers_verified():
                    raise ValueError(
                        "Inspect both timer banks on this connection before editing a schedule"
                    )
                await self._read_native_banks_locked()
                previous_timers = copy.deepcopy(self._native_banks)
            # Write once. Record an attempt separately from transport completion.
            self._native_history = {
                "action": action,
                "settings": payload,
                "attempted_at": dt_util.utcnow().isoformat(),
                "source": "last_command",
                "readback_confirmed": False,
            }
            if action == "clock_sync":
                packet = build_clock_sync(int(dt_util.utcnow().timestamp()), self._native_offset())
                self._native_clock_expected = packet
                try:
                    await self._native_query_locked(5, packet)
                finally:
                    self._native_clock_expected = None
            else:
                if action == "music":
                    self._in_draw_mode = False
                    self._last_playback = None
                await self._native_write_locked(packet, expect_ack=action == "music")
            self._native_history["sent_at"] = dt_util.utcnow().isoformat()
            if action == "music":
                report = await self._native_read_status_locked()
                expected = {
                    "mode": 3,
                    "music_mode": payload["mode"],
                    "microphone": "device",
                    "auto_color": payload["auto_color"],
                    "sensitivity": payload["sensitivity"],
                    "brightness_percent": payload["brightness"],
                    "hue": payload["hue"],
                    "saturation_raw": payload["saturation"] * 10,
                }
                if any(report.get(k) != v for k, v in expected.items()):
                    raise ValueError(
                        "Music sent once, but device settings did not match. Check the lights before sending again"
                    )
            elif action == "scene_speed":
                self._native_speed = None
                await self._native_query_locked(0x0C, build_scene_speed_query())
                if self._native_speed != payload["speed"]:
                    raise ValueError(
                        "Scene-speed readback differs; command was sent once. Check the lights"
                    )
            elif action == "countdown":
                report = await self._native_read_status_locked()
                remaining = report.get("countdown_seconds")
                if (
                    remaining is None
                    or not 0 <= payload["seconds"] - remaining <= 10
                    or payload["seconds"] > 0
                    and remaining == 0
                ):
                    raise ValueError(
                        "Countdown sent once, but remaining time did not match. Check the lights"
                    )
            elif action == "timer":
                self._native_banks = {}
                await self._read_native_banks_locked()
                timer = next(
                    t
                    for b in self._native_banks.values()
                    for t in b
                    if t["slot"] == payload["slot"]
                )
                converted = local_timer(timer, self._native_offset())
                expected = {**payload, "weekdays": sorted(payload["weekdays"]), "exists": True}
                if any(converted.get(k) != v for k, v in expected.items()):
                    raise ValueError(
                        "Schedule sent once, but slot readback did not match. Check the lights"
                    )
                for command, timers in previous_timers.items():
                    for before, after in zip(timers, self._native_banks[command], strict=True):
                        if before["slot"] == payload["slot"]:
                            continue
                        if any(before[k] != after[k] for k in before if k != "executed"):
                            raise ValueError(
                                "Schedule sent once, but another slot changed in readback. Check device schedules"
                            )
            self._native_history["readback_confirmed"] = True
            self._native_history["confirmed_at"] = dt_util.utcnow().isoformat()
            return self.studio_snapshot
