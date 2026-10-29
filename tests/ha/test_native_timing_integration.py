"""Native timing against real HA imports and fake radio I/O, never real BLE.

Generated with aurora@aurora-smart-home (ha-integration-dev skill)
https://github.com/tonylofgren/aurora-smart-home
"""

import asyncio
from copy import deepcopy
from datetime import UTC, datetime
from unittest.mock import patch

import pytest
import voluptuous as vol

from custom_components.hello_fairy_ble.native_timers import build_clock_sync, build_timer_write
from custom_components.hello_fairy_ble.pixel_protocol import build_packet

from .conftest import INFO_PACKET


class TimingRadio:
    """Independent tiny device-state model replying through real API decoder."""

    def __init__(self, api, client):
        self.api = api
        self.client = client
        self.slots = [bytes((0, 18, slot, 8 | slot << 4)) for slot in range(8)]
        self.packets = []
        self.countdown = 0
        self.elapsed = 0
        self.reject_schedule = False
        self.change_unrelated_slot = False
        self.mark_unrelated_executed = False
        self.clock_echo = True
        self.clock_reply = None
        self.missing_bank = None
        client.write_gatt_char.side_effect = self.write

    async def notify(self, packet):
        await self.api._handle_notification(None, bytearray(packet))

    async def write(self, uuid, packet, response):
        assert response is False
        self.packets.append(bytes(packet))
        command = packet[1]
        if command == 0:
            await self.notify(INFO_PACKET)
        elif command == 12:
            await self.notify(build_packet(12, [50]))
        elif command == 221:
            await self.notify(build_packet(221, [1]))
        elif command in (6, 7) and packet[2] == 0:
            if command != self.missing_bank:
                offset = (command - 6) * 4
                await self.notify(build_packet(command, b"".join(self.slots[offset : offset + 4])))
        elif command == 6 and packet[2] == 4:
            if not self.reject_schedule:
                self.slots[(packet[6] >> 4) & 7] = packet[3:7]
                if self.change_unrelated_slot:
                    self.slots[0] = bytes((0, 19, 0, 8))
                if self.mark_unrelated_executed:
                    slot = bytearray(self.slots[0])
                    slot[3] |= 128
                    self.slots[0] = bytes(slot)
        elif command == 4:
            self.countdown = max(0, int.from_bytes(packet[3:7], "big") - self.elapsed)
        elif command == 1:
            await self.notify(
                build_packet(1, self.countdown.to_bytes(3, "big") + bytes((1, 2, 201, 0, 100)))
            )
        elif command == 5 and self.clock_echo:
            await self.notify(self.clock_reply or packet)


@pytest.fixture
def radio(api, client):
    return TimingRadio(api, client)


@pytest.fixture
def fast_timeout():
    original = asyncio.wait_for
    with patch(
        "custom_components.hello_fairy_ble.native.asyncio.wait_for",
        lambda coro, timeout: original(coro, timeout=0.01),
    ):
        yield


TIMER = dict(slot=6, hour=23, minute=30, weekdays=[7], enabled=True, power=True)


async def test_inspection_queries_both_banks_without_schedule_or_clock_writes(api, radio):
    snapshot = await api.inspect_native()
    assert [p[1:3] for p in radio.packets] == [
        bytes((0, 0)),
        bytes((12, 0)),
        bytes((221, 0)),
        bytes((6, 0)),
        bytes((7, 0)),
    ]
    assert snapshot["native"]["timers_supported"] is True
    assert len(snapshot["native"]["timers"]) == 8
    assert snapshot["native"]["last_command"] is None


async def test_missing_second_bank_does_not_grant_schedule_access(api, radio, fast_timeout):
    radio.missing_bank = 7
    snapshot = await api.inspect_native()
    assert snapshot["native"]["timers_supported"] is False
    with pytest.raises(ValueError, match="both timer banks"):
        await api.set_native("timer", TIMER)
    assert all(p[2] == 0 for p in radio.packets if p[1] == 6)


async def test_timer_write_changes_one_slot_and_preserves_other_device_slots(api, radio):
    with patch.object(api, "_native_offset", return_value=180):
        await api.inspect_native()
        before = deepcopy(radio.slots)
        radio.packets.clear()
        result = await api.set_native("timer", TIMER)
    assert [p[1] for p in radio.packets] == [6, 7, 6, 6, 7]
    writes = [p for p in radio.packets if p[1:3] == bytes((6, 4))]
    assert writes == [build_timer_write(**TIMER, utc_offset_minutes=180)]
    assert radio.slots[:6] == before[:6]
    assert radio.slots[7] == before[7]
    assert radio.slots[6] != before[6]
    assert result["native"]["last_command"]["readback_confirmed"] is True
    edited = next(t for t in result["native"]["timers"] if t["slot"] == 6)
    assert edited["hour"] == 23
    assert edited["weekdays"] == [7]


async def test_existing_timer_number_mismatch_fails_before_single_slot_write(api, radio):
    await api.inspect_native()
    radio.slots[5] = bytes((0, 18, 5, 8 | 4 << 4))
    radio.packets.clear()
    with pytest.raises(ValueError, match="numbering"):
        await api.set_native("timer", TIMER)
    assert [p[1:3] for p in radio.packets] == [bytes((6, 0)), bytes((7, 0))]
    assert api.studio_snapshot["native"]["timers_supported"] is False


async def test_timer_readback_mismatch_records_single_attempt_without_replay(api, radio):
    await api.inspect_native()
    radio.reject_schedule = True
    radio.packets.clear()
    with pytest.raises(ValueError, match="readback did not match"):
        await api.set_native("timer", TIMER)
    assert len([p for p in radio.packets if p[1:3] == bytes((6, 4))]) == 1
    assert api.studio_snapshot["native"]["last_command"]["readback_confirmed"] is False


async def test_unrelated_timer_change_is_reported_without_replay(api, radio):
    await api.inspect_native()
    radio.change_unrelated_slot = True
    radio.packets.clear()
    with pytest.raises(ValueError, match="[Uu]nrelated|[Oo]ther|[Uu]nchanged|[Uu]ntouched"):
        await api.set_native("timer", TIMER)
    assert len([p for p in radio.packets if p[1:3] == bytes((6, 4))]) == 1
    assert api.studio_snapshot["native"]["last_command"]["readback_confirmed"] is False


async def test_unrelated_executed_flag_is_dynamic_and_does_not_fail_readback(api, radio):
    await api.inspect_native()
    radio.mark_unrelated_executed = True
    result = await api.set_native("timer", TIMER)
    assert result["native"]["last_command"]["readback_confirmed"] is True


async def test_duplicate_weekdays_rejected_before_any_device_access(api, radio):
    with pytest.raises((ValueError, vol.Invalid), match="duplicates|unique"):
        await api.set_native("timer", {**TIMER, "weekdays": [1, 1]})
    assert radio.packets == []


async def test_timer_capability_does_not_survive_replacement_client(api, client, radio):
    await api.inspect_native()
    previous = api._native_client
    api._client = deepcopy(client)
    api._client.write_gatt_char = client.write_gatt_char
    radio.packets.clear()
    with pytest.raises(ValueError, match="both timer banks"):
        await api.set_native("timer", TIMER)
    assert api._native_client is not previous
    assert [p[1] for p in radio.packets] == [0]
    assert api.studio_snapshot["native"]["timers_supported"] is False


@pytest.mark.parametrize("seconds,elapsed", [(0, 0), (60, 0), (60, 5), (86400, 10)])
async def test_countdown_and_zero_cancel_confirm_current_remaining_seconds(
    api, radio, seconds, elapsed
):
    radio.elapsed = elapsed
    result = await api.set_native("countdown", {"seconds": seconds, "power": False})
    assert [p[1] for p in radio.packets] == [0, 4, 1]
    assert radio.packets[1] == build_packet(4, seconds.to_bytes(4, "big") + b"\x00")
    assert result["reported"]["countdown_seconds"] == max(0, seconds - elapsed)
    assert result["native"]["last_command"]["readback_confirmed"] is True


async def test_countdown_mismatch_is_not_success_or_replayed(api, radio):
    radio.elapsed = 11
    with pytest.raises(ValueError, match="remaining time did not match"):
        await api.set_native("countdown", {"seconds": 60, "power": True})
    assert len([p for p in radio.packets if p[1] == 4]) == 1
    assert api.studio_snapshot["native"]["last_command"]["readback_confirmed"] is False


async def test_explicit_clock_sync_matches_exact_echo_once(api, radio):
    now = datetime.fromtimestamp(0x6ACF985B, UTC)
    with (
        patch("custom_components.hello_fairy_ble.native.dt_util.utcnow", return_value=now),
        patch.object(api, "_native_offset", return_value=180),
    ):
        result = await api.set_native("clock_sync", {})
    assert [p[1] for p in radio.packets] == [0, 5]
    assert radio.packets[1].hex() == "aa05076acf985b0100b497"
    assert result["native"]["last_command"]["readback_confirmed"] is True
    assert api._native_clock_expected is None


async def test_different_clock_echo_cannot_confirm_or_trigger_replay(api, radio, fast_timeout):
    radio.clock_reply = build_clock_sync(0x6ACF985B, 0)
    with pytest.raises(TimeoutError):
        await api.set_native("clock_sync", {})
    assert len([p for p in radio.packets if p[1] == 5]) == 1
    assert api._native_clock_expected is None
    assert api._native_pending is None
    assert api.studio_snapshot["native"]["last_command"]["readback_confirmed"] is False


@pytest.mark.parametrize(
    "action,payload",
    [("clock_sync", {}), ("countdown", {"seconds": 0, "power": True}), ("timer", TIMER)],
)
async def test_timing_controls_preserve_existing_draw_mode_and_playback(
    api, radio, action, payload
):
    await api.inspect_native()
    playback = {"kind": "animation", "movement": "breathe", "speed": 25}
    api._in_draw_mode = True
    api._last_playback = deepcopy(playback)
    await api.set_native(action, payload)
    assert api._in_draw_mode is True
    assert api._last_playback == playback
