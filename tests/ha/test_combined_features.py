"""Integration edges between shared controls (ha-integration-dev skill).
https://github.com/tonylofgren/aurora-smart-home
"""

from unittest.mock import AsyncMock, patch

import pytest

from custom_components.hello_fairy_ble.library import StudioLibrary
from custom_components.hello_fairy_ble.rendering import render_pages

from .conftest import ADDRESS
from .test_library import curtain, design


def test_icon_only_notifications_render_one_bounded_frame():
    for icon in ("bell", "heart", "door"):
        pages = render_pages("", 20, 255, 254, icon)
        assert len(pages) == 1
        assert len(pages[0]) == 400
        assert 255 in pages[0]
    with pytest.raises(ValueError):
        render_pages("", 20)


async def test_compact_status_updates_revision_and_orientation(hass, hass_storage):
    library = StudioLibrary(hass)
    curtain(hass)
    initial = await library.command("status", {})
    assert "designs" not in initial
    await library.command("save_orientation", {"address": ADDRESS, "rotation": 90})
    updated = await library.command("status", {})
    assert updated["library_revision"] != initial["library_revision"]
    assert updated["orientations"][ADDRESS]["rotation"] == 90
    assert "designs" not in updated
    await library.command("save_design", {"name": "Corner", "design": design()})
    assert (await library.command("get", {}))["library_revision"] != updated["library_revision"]


async def test_explicit_playlist_start_keeps_selected_playlist(hass, hass_storage):
    library = StudioLibrary(hass)
    c = curtain(hass)
    await library.command("save_design", {"name": "Red", "design": design()})
    design_id = library.data["designs"][0]["id"]
    first = library.data["selected_playlist_id"]
    await library.command(
        "save_playlist",
        {
            "playlist_id": None,
            "name": "Second",
            "playlist": {"items": [{"design_id": design_id, "seconds": 10}], "loop": False},
        },
    )
    second = library.data["selected_playlist_id"]
    await library.command("select_playlist", {"playlist_id": first})
    with patch.object(library, "_hold", AsyncMock()):
        await library.command("start", {"addresses": [ADDRESS], "playlist_id": second})
        await library._task
    c.set_frame.assert_awaited_once()
    assert library.data["selected_playlist_id"] == first
