"""Library persistence and playlist safety against real HA (ha-integration-dev skill).
https://github.com/tonylofgren/aurora-smart-home
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest
from homeassistant.exceptions import HomeAssistantError
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components import hello_fairy_ble as integration
from custom_components.hello_fairy_ble import RuntimeData
from custom_components.hello_fairy_ble.const import DOMAIN
from custom_components.hello_fairy_ble.library import (
    StudioLibrary,
    async_setup_library,
    validate_design,
)

from .conftest import ADDRESS


def design(width=20, kind="picture"):
    return {
        "format": "hello-fairy-pattern",
        "version": 2,
        "width": width,
        "height": 20,
        "kind": kind,
        "frames": [[0] * (width * 20)] * (2 if kind == "animation" else 1),
        "settings": {
            "movement": "blink" if kind == "animation" else "still",
            "speed": 30,
            "brightness": 75,
        },
    }


@pytest.fixture
def library(hass, hass_storage):
    return StudioLibrary(hass)


def curtain(hass, address=ADDRESS):
    e = MockConfigEntry(domain=DOMAIN, title="Curtain", unique_id=address)
    e.add_to_hass(hass)
    c = SimpleNamespace(
        device_address=address,
        set_frame=AsyncMock(),
        set_two_picture_animation=AsyncMock(),
        set_diy_playback=AsyncMock(),
    )
    e.runtime_data = RuntimeData(c, Mock())
    return c


async def saved(library, width=20, kind="picture", loop=False):
    result = await library.command("save_design", {"name": "Heart", "design": design(width, kind)})
    design_id = result["designs"][0]["id"]
    await library.command(
        "save_playlist",
        {"playlist": {"items": [{"design_id": design_id, "seconds": 10}], "loop": loop}},
    )
    return design_id


async def test_persists_across_instances_without_playback(library):
    design_id = await saved(library)
    loaded = StudioLibrary(library.hass)
    await loaded.async_load()
    assert loaded.data == library.data
    assert loaded.data["designs"][0]["id"] == design_id
    assert not loaded.active
    assert loaded.status["state"] == "stopped"
    snapshot = loaded.snapshot()
    snapshot["designs"][0]["design"]["frames"][0][0] = 255
    assert loaded.data["designs"][0]["design"]["frames"][0][0] == 0


async def test_failed_disk_save_does_not_publish(library):
    with patch.object(library.store, "async_save", AsyncMock(side_effect=OSError("disk full"))):
        with pytest.raises(OSError):
            await saved(library)
    assert library.data["designs"] == []


async def test_overwrite_delete_and_referenced_design_guard(library):
    design_id = await saved(library)
    await library.command(
        "save_design", {"design_id": design_id, "name": "Updated", "design": design()}
    )
    assert len(library.data["designs"]) == 1
    assert library.data["designs"][0]["name"] == "Updated"
    with pytest.raises(ValueError, match="Remove this design"):
        await library.command("delete_design", {"design_id": design_id})
    await library.command("save_playlist", {"playlist": {"items": [], "loop": False}})
    await library.command("delete_design", {"design_id": design_id})
    assert not library.data["designs"]


@pytest.mark.parametrize("bad", [True, 9, 1.5, 86401, "30"])
async def test_invalid_duration_rejected(library, bad):
    design_id = await saved(library)
    with pytest.raises(ValueError, match="10–86400"):
        await library.command(
            "save_playlist",
            {"playlist": {"items": [{"design_id": design_id, "seconds": bad}], "loop": False}},
        )
    assert library.data["playlist"]["items"][0]["seconds"] == 10


@pytest.mark.parametrize(
    "field,value",
    [
        ("width", 21),
        ("width", True),
        ("kind", []),
        ("frames", [[]]),
        ("settings", {"movement": [], "speed": 30, "brightness": 75}),
    ],
)
def test_invalid_design_data(field, value):
    with pytest.raises(ValueError):
        validate_design({**design(), field: value})


@pytest.mark.parametrize("addresses", [[], [ADDRESS, ADDRESS], ["not configured"]])
async def test_invalid_selection_has_no_writes(library, addresses):
    c = curtain(library.hass)
    await saved(library)
    with pytest.raises(ValueError):
        await library.command("start", {"addresses": addresses})
    c.set_frame.assert_not_awaited()


async def test_all_widths_checked_before_first_upload(library):
    c = curtain(library.hass)
    await saved(library, 40)
    with pytest.raises(ValueError, match="curtain count"):
        await library.command("start", {"addresses": [ADDRESS]})
    c.set_frame.assert_not_awaited()


@pytest.mark.parametrize("kind", ["picture", "animation"])
async def test_serial_split_settings_then_hold(library, kind):
    order = []
    a = curtain(library.hass)
    b = curtain(library.hass, "AA:BB:CC:DD:EE:02")
    await saved(library, 40, kind)
    for i, c in enumerate((a, b)):

        async def frame(*args, index=i):
            order.append(f"frame{index}")
            frames = args[0] if kind == "animation" else [args[0]]
            assert all(len(f) == 400 for f in frames)

        async def settings(*args, index=i):
            order.append(f"settings{index}")
            assert args == (kind, "blink" if kind == "animation" else "still", 30, 75)

        c.set_frame.side_effect = frame
        c.set_two_picture_animation.side_effect = frame
        c.set_diy_playback.side_effect = settings

    async def hold(seconds):
        order.append(f"hold{seconds}")

    with patch.object(library, "_hold", hold):
        await library.command("start", {"addresses": [a.device_address, b.device_address]})
        await library._task
    assert order == ["frame0", "settings0", "frame1", "settings1", "hold10"]
    assert library.status["state"] == "completed"


@pytest.mark.parametrize("stage", ["set_frame", "set_diy_playback"])
async def test_failure_no_replay_or_later_curtain(library, stage):
    a = curtain(library.hass)
    b = curtain(library.hass, "AA:BB:CC:DD:EE:02")
    await saved(library, 40, loop=True)
    getattr(a, stage).side_effect = ConnectionError("lost link")
    await library.command("start", {"addresses": [a.device_address, b.device_address]})
    await library._task
    assert library.status["state"] == "error"
    assert "lost link" in library.status["message"]
    assert a.set_frame.await_count == 1
    b.set_frame.assert_not_awaited()


async def test_stop_finishes_current_upload_and_no_next_curtain(library):
    a = curtain(library.hass)
    b = curtain(library.hass, "AA:BB:CC:DD:EE:02")
    entered, release = asyncio.Event(), asyncio.Event()

    async def slow_upload(frame):
        entered.set()
        await release.wait()

    a.set_frame.side_effect = slow_upload
    await saved(library, 40, loop=True)
    await library.command("start", {"addresses": [a.device_address, b.device_address]})
    await entered.wait()
    stopping = asyncio.create_task(library.stop())
    await asyncio.sleep(0)
    assert not stopping.done()
    assert library.status["state"] == "stopping"
    release.set()
    await stopping
    a.set_diy_playback.assert_awaited_once()
    b.set_frame.assert_not_awaited()
    assert library.status["state"] == "stopped"


async def test_repeat_stop_and_running_edit_guard(library):
    c = curtain(library.hass)
    await saved(library, loop=True)
    holding = asyncio.Event()
    original = library._hold

    async def hold(seconds):
        holding.set()
        await original(seconds)

    with patch.object(library, "_hold", hold):
        await library.command("start", {"addresses": [ADDRESS]})
        await holding.wait()
        with pytest.raises(ValueError, match="Stop the playlist"):
            await library.command("save_design", {"name": "Other", "design": design()})
        await library.stop()
    assert c.set_frame.await_count == 1
    assert library.status["state"] == "stopped"


async def test_admin_websocket_and_automation_actions(hass, hass_ws_client, hass_storage):
    assert await async_setup_component(hass, "http", {})
    library = await async_setup_library(hass)
    client = await hass_ws_client(hass)
    await client.send_json_auto_id(
        {
            "type": f"{DOMAIN}/studio/library",
            "action": "save_design",
            "payload": {"name": "Heart", "design": design()},
        }
    )
    response = await client.receive_json()
    assert response["success"]
    assert response["result"]["designs"][0]["name"] == "Heart"
    with pytest.raises(HomeAssistantError, match="configured or loaded"):
        await hass.services.async_call(
            DOMAIN, "start_playlist", {"addresses": [ADDRESS]}, blocking=True
        )
    await hass.services.async_call(DOMAIN, "stop_playlist", {}, blocking=True)
    assert library.status["state"] == "stopped"


async def test_readonly_user_cannot_edit_library(
    hass, hass_ws_client, hass_read_only_access_token, hass_storage
):
    assert await async_setup_component(hass, "http", {})
    library = await async_setup_library(hass)
    client = await hass_ws_client(hass, access_token=hass_read_only_access_token)
    await client.send_json_auto_id(
        {
            "type": f"{DOMAIN}/studio/library",
            "action": "save_design",
            "payload": {"name": "Forbidden", "design": design()},
        }
    )
    response = await client.receive_json()
    assert not response["success"]
    assert response["error"]["code"] == "unauthorized"
    assert not library.data["designs"]


async def test_automation_start_and_manual_service_stop(hass, hass_storage):
    assert await async_setup_component(hass, "http", {})
    library = await async_setup_library(hass)
    c = curtain(hass)
    await saved(library, loop=True)
    holding = asyncio.Event()
    original = library._hold

    async def hold(seconds):
        holding.set()
        await original(seconds)

    with (
        patch.object(integration, "async_setup_studio", AsyncMock()),
        patch.object(library, "_hold", hold),
    ):
        assert await integration.async_setup(hass, {})
        await hass.services.async_call(
            DOMAIN, "start_playlist", {"addresses": [ADDRESS]}, blocking=True
        )
        await holding.wait()
        await hass.services.async_call(
            DOMAIN, "set_frame", {"address": ADDRESS, "pixels": [255] * 400}, blocking=True
        )
    assert library.status["state"] == "stopped"
    assert c.set_frame.await_count == 2
    assert c.set_frame.await_args.args[0] == [255] * 400


async def test_library_limits_and_unknown_references(library):
    design_id = await saved(library)
    with pytest.raises(ValueError):
        await library.command(
            "save_playlist",
            {"playlist": {"items": [{"design_id": "missing", "seconds": 30}], "loop": False}},
        )
    with pytest.raises(ValueError):
        await library.command(
            "save_playlist",
            {"playlist": {"items": [{"design_id": design_id, "seconds": 30}] * 51, "loop": False}},
        )
    library.data["designs"] = [
        {"id": str(i), "name": str(i), "design": design()} for i in range(50)
    ]
    with pytest.raises(ValueError, match="50 designs"):
        await library.command("save_design", {"name": "Overflow", "design": design()})


async def test_transfer_failure_during_stop_remains_visible(library):
    c = curtain(library.hass)
    entered, release = asyncio.Event(), asyncio.Event()

    async def fail(frame):
        entered.set()
        await release.wait()
        raise ConnectionError("upload interrupted")

    c.set_frame.side_effect = fail
    await saved(library)
    await library.command("start", {"addresses": [ADDRESS]})
    await entered.wait()
    stopping = asyncio.create_task(library.stop())
    await asyncio.sleep(0)
    release.set()
    await stopping
    assert library.status["state"] == "error"
    assert "upload interrupted" in library.status["message"]


@pytest.mark.parametrize("action", ["on", "off", "preset"])
async def test_normal_entities_stop_background_before_controlling(hass, action):
    from custom_components.hello_fairy_ble.light import HelloFairyLight
    from custom_components.hello_fairy_ble.number import HelloFairyPresetNumber

    order = []

    async def stop(call):
        order.append("stop")

    async def control(*args):
        order.append("control")

    hass.services.async_register(DOMAIN, "stop_playlist", stop)
    c = SimpleNamespace(
        hass=hass,
        device_address=ADDRESS,
        device_name="Curtain",
        set_power=AsyncMock(side_effect=control),
        set_preset=AsyncMock(side_effect=control),
        async_request_refresh=AsyncMock(),
    )
    entity = HelloFairyPresetNumber(c) if action == "preset" else HelloFairyLight(c)
    entity.hass = hass
    if action == "preset":
        await entity.async_set_native_value(3)
    elif action == "off":
        await entity.async_turn_off()
    else:
        await entity.async_turn_on()
    assert order == ["stop", "control"]
