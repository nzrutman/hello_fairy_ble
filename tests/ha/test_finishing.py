"""Finishing features and atomic library portability (ha-integration-dev skill).
https://github.com/tonylofgren/aurora-smart-home
"""

import asyncio
import copy
from unittest.mock import AsyncMock, patch

import pytest

from custom_components.hello_fairy_ble.library import StudioLibrary

from .conftest import ADDRESS
from .test_library import curtain, saved


@pytest.fixture
def library(hass, hass_storage):
    return StudioLibrary(hass)


async def test_layout_save_does_not_touch_radio_or_selected_playlist(library):
    c = curtain(library.hass)
    selected = library.data["selected_playlist_id"]
    result = await library.command("save_layout", {"name": "Both", "addresses": [ADDRESS]})
    assert result["layouts"][0]["name"] == "Both"
    assert result["selected_playlist_id"] == selected
    c.set_frame.assert_not_called()
    await library.command("delete_layout", {"layout_id": result["layouts"][0]["id"]})
    assert library.data["layouts"] == []


async def test_backup_merge_remaps_references_and_preserves_selection(library):
    design_id = await saved(library)
    library.data["favorites"] = [{"design_id": design_id, "addresses": [ADDRESS]}]
    library.data["layouts"] = [{"id": "layout", "name": "Main", "addresses": [ADDRESS]}]
    library.data["playlist"]["end_design_id"] = design_id
    library.data["playlists"][0]["end_design_id"] = design_id
    backup = (await library.command("export_library", {}))["backup"]
    assert "status" not in backup["data"]
    summary = await library.command("validate_import", {"backup": backup})
    assert summary["counts"]["designs"] == 1
    assert len(library.data["designs"]) == 1
    selected = library.data["selected_playlist_id"]
    result = await library.command("import_library", {"backup": backup})
    new_id = result["designs"][1]["id"]
    assert new_id != design_id
    assert result["playlists"][1]["items"][0]["design_id"] == new_id
    assert result["playlists"][1]["end_design_id"] == new_id
    assert result["favorites"][1]["design_id"] == new_id
    assert result["layouts"][0]["id"] != result["layouts"][1]["id"]
    assert result["selected_playlist_id"] == selected


async def test_import_validates_all_before_saving_and_has_no_hardware_requirement(library):
    await saved(library)
    backup = (await library.command("export_library", {}))["backup"]
    backup["data"]["layouts"] = [{"id": "layout", "name": "Offline", "addresses": [ADDRESS]}]
    with patch.object(library.store, "async_save", AsyncMock()) as save:
        await library.command("validate_import", {"backup": backup, "mode": "replace"})
        save.assert_not_called()
        broken = copy.deepcopy(backup)
        broken["data"]["layouts"][0]["addresses"] = ["bad"]
        with pytest.raises(ValueError):
            await library.command("import_library", {"backup": broken, "mode": "replace"})
        save.assert_not_called()
    await library.command("import_library", {"backup": backup, "mode": "replace"})
    assert library.data["layouts"][0]["name"] == "Offline"


async def test_pause_during_upload_finishes_design_then_holds_without_reupload(library):
    c = curtain(library.hass)
    await saved(library)
    entered = asyncio.Event()
    release = asyncio.Event()

    async def upload(frame):
        entered.set()
        await release.wait()

    c.set_frame.side_effect = upload
    await library.command("start", {"addresses": [ADDRESS]})
    await entered.wait()
    result = await library.command("pause", {})
    assert result["status"]["state"] == "pausing"
    release.set()
    for _ in range(20):
        if library.status["state"] == "paused":
            break
        await asyncio.sleep(0)
    assert library.status["state"] == "paused"
    assert library.active
    assert library.snapshot()["status"]["completed_curtains"] == 1
    remaining = library.snapshot()["status"]["hold_remaining_seconds"]
    await asyncio.sleep(0.01)
    assert library.snapshot()["status"]["hold_remaining_seconds"] == remaining
    with pytest.raises(ValueError, match="Resume"):
        await library.command("next", {})
    with pytest.raises(ValueError, match="Stop"):
        await library.command("import_library", {})
    await library.command("resume", {})
    await asyncio.sleep(0.01)
    assert library.snapshot()["status"]["hold_remaining_seconds"] < remaining
    assert c.set_frame.await_count == 1
    assert c.set_diy_playback.await_count == 1
    await library.stop()
    assert library.status["state"] == "stopped"
    assert not library.active


async def test_failure_keeps_completed_curtain_count(library):
    c1 = curtain(library.hass)
    c2 = curtain(library.hass, "AA:BB:CC:DD:EE:02")
    c2.set_frame.side_effect = RuntimeError("disconnected")
    await saved(library, width=40)
    await library.command("start", {"addresses": [c1.device_address, c2.device_address]})
    await library._task
    assert library.status["state"] == "error"
    assert library.status["completed_curtains"] == 1
    assert library.status["total_curtains"] == 2


@pytest.mark.parametrize("mode", ["bad", False, None])
async def test_invalid_import_mode(library, mode):
    backup = (await library.command("export_library", {}))["backup"]
    with pytest.raises(ValueError, match="mode"):
        await library.command("validate_import", {"backup": backup, "mode": mode})


async def test_legacy_store_upgrades_without_resuming(library):
    legacy = {"designs": [], "playlist": {"items": [], "loop": False}}
    await library.store.async_save(legacy)
    loaded = StudioLibrary(library.hass)
    await loaded.async_load()
    assert loaded.data["layouts"] == []
    assert not loaded.active


async def test_import_disk_failure_does_not_change_library(library):
    await saved(library)
    backup = (await library.command("export_library", {}))["backup"]
    before = copy.deepcopy(library.data)
    with patch.object(library.store, "async_save", AsyncMock(side_effect=OSError("disk full"))):
        with pytest.raises(OSError):
            await library.command("import_library", {"backup": backup})
    assert library.data == before


@pytest.mark.parametrize(
    "change", ["playlist_id", "cross_reference", "orientation", "duplicate", "oversize"]
)
async def test_import_rejects_malformed_nested_records_before_persist(library, change):
    await saved(library)
    backup = (await library.command("export_library", {}))["backup"]
    data = backup["data"]
    if change == "playlist_id":
        del data["playlists"][0]["id"]
    elif change == "cross_reference":
        data["playlists"][0]["items"][0]["design_id"] = "missing"
    elif change == "orientation":
        data["orientations"][ADDRESS] = {"rotation": 45}
    elif change == "duplicate":
        data["designs"].append(copy.deepcopy(data["designs"][0]))
    else:
        backup["padding"] = "x" * (4 * 1024 * 1024)
    with patch.object(library.store, "async_save", AsyncMock()) as save:
        with pytest.raises(ValueError):
            await library.command("import_library", {"backup": backup})
        save.assert_not_called()


@pytest.mark.parametrize("finish", ["resume", "stop"])
@pytest.mark.parametrize("navigation,delta", [("next", 1), ("previous", -1)])
async def test_queued_navigation_cannot_bypass_pause_after_current_upload(
    library, finish, navigation, delta
):
    c = curtain(library.hass)
    await saved(library)
    entered = asyncio.Event()
    release = asyncio.Event()
    second = asyncio.Event()
    library.data["playlist"]["items"].append(copy.deepcopy(library.data["playlist"]["items"][0]))

    async def upload(frame):
        if c.set_frame.await_count == 1:
            entered.set()
            await release.wait()
        else:
            second.set()

    c.set_frame.side_effect = upload
    await library.command("start", {"addresses": [ADDRESS]})
    await entered.wait()
    await library.command(navigation, {})
    await library.command("pause", {})
    release.set()
    for _ in range(30):
        if library.status["state"] == "paused":
            break
        await asyncio.sleep(0)
    assert library.status["state"] == "paused"
    assert c.set_frame.await_count == 1
    assert library._navigation == [delta]
    assert not second.is_set()
    if finish == "resume":
        await library.command("resume", {})
        await asyncio.wait_for(second.wait(), 1)
        assert c.set_frame.await_count == 2
        await library.stop()
    else:
        await asyncio.wait_for(library.stop(), 1)
        assert c.set_frame.await_count == 1
    assert not library.active
