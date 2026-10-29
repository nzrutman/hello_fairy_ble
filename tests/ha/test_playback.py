"""Playback controls and bounded rendering (ha-integration-dev skill).
https://github.com/tonylofgren/aurora-smart-home
"""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest

from custom_components.hello_fairy_ble.library import StudioLibrary
from custom_components.hello_fairy_ble.rendering import render_clock, render_pages

from .conftest import ADDRESS
from .test_library import curtain, design, saved


@pytest.fixture
def library(hass, hass_storage):
    return StudioLibrary(hass)


async def test_migrates_old_store_without_auto_start(library):
    old = {"designs": [], "playlist": {"items": [], "loop": False}}
    with patch.object(library.store, "async_load", AsyncMock(return_value=old)):
        await library.async_load()
    assert library.data["selected_playlist_id"] == "default"
    assert library.data["playlist"] == library.data["playlists"][0]
    assert library.data["favorites"] == []
    assert not library.active


async def test_named_playlist_selection_and_delete(library):
    await saved(library)
    first = library.data["selected_playlist_id"]
    await library.command(
        "save_playlist",
        {"playlist_id": None, "name": "Evening", "playlist": {"items": [], "loop": False}},
    )
    second = library.data["selected_playlist_id"]
    assert first != second
    assert len(library.data["playlists"]) == 2
    await library.command("select_playlist", {"playlist_id": first})
    assert library.data["playlist"]["items"]
    await library.command("delete_playlist", {"playlist_id": second})
    with pytest.raises(ValueError):
        await library.command("delete_playlist", {"playlist_id": first})


async def test_repeat_count_and_final_design(library):
    c = curtain(library.hass)
    identifier = await saved(library)
    await library.command(
        "save_playlist",
        {
            "playlist": {
                "items": [{"design_id": identifier, "seconds": 10}],
                "loop": False,
                "repeat_count": 3,
                "end_design_id": identifier,
            }
        },
    )
    with patch.object(library, "_hold", AsyncMock()):
        await library.command("start", {"addresses": [ADDRESS]})
        await library._task
    assert c.set_frame.await_count == 4
    assert library.status["state"] == "completed"


async def test_shuffle_keeps_each_step_once_per_cycle(library):
    c = curtain(library.hass)
    first = await saved(library)
    result = await library.command("save_design", {"name": "Other", "design": design()})
    second = result["designs"][-1]["id"]
    await library.command(
        "save_playlist",
        {
            "playlist": {
                "items": [
                    {"design_id": first, "seconds": 10},
                    {"design_id": second, "seconds": 10},
                ],
                "loop": False,
                "shuffle": True,
                "repeat_count": 2,
            }
        },
    )
    with (
        patch.object(library, "_hold", AsyncMock()),
        patch("custom_components.hello_fairy_ble.library.random.shuffle") as shuffle,
    ):
        await library.command("start", {"addresses": [ADDRESS]})
        await library._task
    assert shuffle.call_count == 2
    assert c.set_frame.await_count == 4


async def test_favorite_recall_targets_orientation_and_dispatch(library):
    c = curtain(library.hass)
    identifier = await saved(library)
    pattern = design()
    pattern["frames"][0][0] = 255
    with patch("custom_components.hello_fairy_ble.library.async_dispatcher_send") as dispatch:
        await library.command(
            "save_design", {"design_id": identifier, "name": "Corner", "design": pattern}
        )
        await library.command(
            "set_favorite", {"design_id": identifier, "addresses": [ADDRESS], "enabled": True}
        )
        await library.command("save_orientation", {"address": ADDRESS, "rotation": 180})
    assert dispatch.call_count == 3
    assert dispatch.call_args.args[1] == "hello_fairy_ble_library_changed"
    await library.command("recall", {"design_id": identifier})
    await library._task
    assert c.set_frame.await_args.args[0][-1] == 255
    assert c.set_frame.await_args.args[0][0] == 0


async def test_navigation_during_upload_queues_without_overlap(library):
    c = curtain(library.hass)
    first = await saved(library)
    second_result = await library.command("save_design", {"name": "Second", "design": design()})
    second = second_result["designs"][-1]["id"]
    await library.command(
        "save_playlist",
        {
            "playlist": {
                "items": [
                    {"design_id": first, "seconds": 10},
                    {"design_id": second, "seconds": 10},
                ],
                "loop": False,
            }
        },
    )
    entered, release = asyncio.Event(), asyncio.Event()

    async def upload(frame):
        if c.set_frame.await_count == 1:
            entered.set()
            await release.wait()

    c.set_frame.side_effect = upload
    with patch.object(library, "_hold", AsyncMock()):
        await library.command("start", {"addresses": [ADDRESS]})
        await entered.wait()
        await library.command("next", {})
        assert c.set_frame.await_count == 1
        release.set()
        await library._task
    assert c.set_frame.await_count == 2


async def test_message_pages_and_natural_restore(library):
    c = curtain(library.hass)
    identifier = await saved(library)
    with patch.object(library, "_hold", AsyncMock()) as hold:
        await library.command(
            "show_message",
            {
                "addresses": [ADDRESS],
                "text": "HELLO WORLD",
                "icon": "bell",
                "duration": 10,
                "restore_design_id": identifier,
            },
        )
        await library._task
    assert c.set_frame.await_count == 4  # three five-character pages then restore
    assert hold.await_count == 3


async def test_invalid_message_and_clock_fail_before_writes(library):
    c = curtain(library.hass)
    for payload in (
        {"text": "emoji 😀"},
        {"text": "HI", "duration": 1},
        {"text": "HI", "color_byte": 181},
    ):
        with pytest.raises(ValueError):
            await library.command("show_message", {"addresses": [ADDRESS], **payload})
    with pytest.raises(ValueError):
        await library.command("start_clock", {"addresses": [ADDRESS], "interval": 59})
    assert not library.active
    c.set_frame.assert_not_awaited()


async def test_clock_stops_on_hold_and_rejects_navigation(library):
    c = curtain(library.hass)
    holding = asyncio.Event()
    original = library._hold

    async def hold(seconds):
        assert seconds == 60
        holding.set()
        await original(seconds)

    with patch.object(library, "_hold", hold):
        await library.command("start_clock", {"addresses": [ADDRESS]})
        await holding.wait()
        with pytest.raises(ValueError):
            await library.command("next", {})
        await library.stop()
    assert c.set_frame.await_count == 1
    assert library.status["state"] == "stopped"


def test_clock_and_rendering_dimensions():
    assert len(render_pages("HELLO", 20)[0]) == 400
    assert len(render_pages("A" * 160, 160)) == 4
    assert len(render_clock(datetime(2026, 1, 1, 23, 59))) == 400
    assert render_clock(datetime(2026, 1, 1, 0, 0), clock_format="12h") == render_pages("12:00")[0]


async def test_message_stop_does_not_restore_and_preserves_error(library):
    c = curtain(library.hass)
    identifier = await saved(library)
    holding = asyncio.Event()
    original = library._hold

    async def hold(seconds):
        holding.set()
        await original(seconds)

    with patch.object(library, "_hold", hold):
        await library.command(
            "show_message", {"addresses": [ADDRESS], "text": "HI", "restore_design_id": identifier}
        )
        await holding.wait()
        await library.stop()
    assert c.set_frame.await_count == 1
    assert library.status["state"] == "stopped"
    c.set_frame.reset_mock()
    c.set_frame.side_effect = ConnectionError("lost link")
    await library.command(
        "show_message", {"addresses": [ADDRESS], "text": "HI", "restore_design_id": identifier}
    )
    await library._task
    assert c.set_frame.await_count == 1
    assert library.status["state"] == "error"


async def test_bad_replacement_keeps_clock_running(library):
    curtain(library.hass)
    holding = asyncio.Event()
    original = library._hold

    async def hold(seconds):
        holding.set()
        await original(seconds)

    with patch.object(library, "_hold", hold):
        await library.command("start_clock", {"addresses": [ADDRESS]})
        await holding.wait()
        task = library._task
        with pytest.raises(ValueError):
            await library.command(
                "show_message",
                {"addresses": [ADDRESS], "text": "HI", "restore_design_id": "missing"},
            )
        assert library._task is task and library.active
        await library.stop()


async def test_new_services_and_websocket_recall(hass, hass_ws_client, hass_storage):
    from homeassistant.exceptions import HomeAssistantError
    from homeassistant.setup import async_setup_component

    from custom_components.hello_fairy_ble.const import DOMAIN
    from custom_components.hello_fairy_ble.library import async_setup_library

    assert await async_setup_component(hass, "http", {})
    library = await async_setup_library(hass)
    c = curtain(hass)
    identifier = await saved(library)
    await hass.services.async_call(
        DOMAIN, "show_design", {"design_id": identifier, "addresses": [ADDRESS]}, blocking=True
    )
    await library._task
    assert c.set_frame.await_count == 1
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(DOMAIN, "playlist_next", {}, blocking=True)
    client = await hass_ws_client(hass)
    await client.send_json_auto_id(
        {
            "type": f"{DOMAIN}/studio/library",
            "action": "recall",
            "payload": {"design_id": identifier, "addresses": [ADDRESS]},
        }
    )
    response = await client.receive_json()
    assert response["success"]
    await library._task
    assert c.set_frame.await_count == 2
