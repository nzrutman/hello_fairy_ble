"""Persistent Studio designs and conservative Home Assistant playlist playback.
Generated with aurora@aurora-smart-home (ha-integration-dev skill)
https://github.com/tonylofgren/aurora-smart-home
"""

from __future__ import annotations

import asyncio
import copy
import json
import logging
import random
import re
from uuid import uuid4

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .diy_controls import build_playback_commands
from .orientation import transform_frame, validate_orientation
from .pixel_protocol import split_virtual_frame, validate_color_byte
from .rendering import render_clock, render_pages

_LOGGER = logging.getLogger(__name__)
MAX_DESIGNS = 50
MAX_STEPS = 50
MIN_SECONDS = 10


def validate_design(value: dict) -> dict:
    """Accept bounded, portable version-2 Studio designs; never execute supplied data."""
    if not isinstance(value, dict):
        raise ValueError("Design must be an object")
    width = value.get("width")
    kind = value.get("kind")
    if (
        value.get("format") != "hello-fairy-pattern"
        or value.get("version") != 2
        or type(width) is not int
        or width not in range(20, 161, 20)
        or value.get("height") != 20
        or kind not in ("picture", "animation")
    ):
        raise ValueError("Choose a version-2 design for one to eight 20×20 curtains")
    frames = value.get("frames")
    if not isinstance(frames, list) or len(frames) != (2 if kind == "animation" else 1):
        raise ValueError("Design must contain its complete picture(s)")
    for frame in frames:
        if not isinstance(frame, list) or len(frame) != width * 20:
            raise ValueError("Design has the wrong number of pixels")
        for color in frame:
            validate_color_byte(color)
    settings = value.get("settings")
    if not isinstance(settings, dict):
        raise ValueError("Playback settings are required")
    build_playback_commands(
        kind, settings.get("movement"), settings.get("speed"), settings.get("brightness")
    )
    return {
        "format": "hello-fairy-pattern",
        "version": 2,
        "width": width,
        "height": 20,
        "kind": kind,
        "frames": copy.deepcopy(frames),
        "settings": {k: settings[k] for k in ("movement", "speed", "brightness")},
    }


class StudioLibrary:
    """One domain-owned manager referenced by registered handlers, not global data."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self.store = Store(hass, 1, f"{DOMAIN}.studio_library")
        self.data = {"designs": [], "playlist": {"items": [], "loop": False}}
        self.status = {"state": "stopped", "message": "Playlist is stopped"}
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()
        self._lock = asyncio.Lock()
        self._wake = asyncio.Event()
        self._navigation = []
        self._paused = False
        self._hold_deadline = None
        self._hold_remaining = 0.0
        self._library_revision = uuid4().hex
        self._upgrade(self.data)

    async def async_load(self) -> None:
        stored = await self.store.async_load()
        if stored is None:
            return
        self.data = self._validated_data(stored)
        # Playback state is deliberately never restored.

    @staticmethod
    def _addresses(addresses):
        if (
            not isinstance(addresses, list)
            or not 1 <= len(addresses) <= 8
            or any(
                not isinstance(a, str)
                or not re.fullmatch(r"[0-9A-Fa-f]{2}(?::[0-9A-Fa-f]{2}){5}", a.strip())
                for a in addresses
            )
        ):
            raise ValueError("Choose one to eight valid curtain Bluetooth addresses")
        result = [a.strip().upper() for a in addresses]
        if len(set(result)) != len(result):
            raise ValueError("Curtain addresses must be unique")
        return result

    @classmethod
    def _validated_data(cls, source):
        """Validate and normalize an entire library without touching disk or hardware."""
        if not isinstance(source, dict):
            raise ValueError("Library must be an object")
        data = copy.deepcopy(source)
        if not isinstance(data.get("designs"), list) or len(data["designs"]) > MAX_DESIGNS:
            raise ValueError("Library can contain at most 50 designs")

        def identifiers(records, label, limit):
            if not isinstance(records, list) or len(records) > limit:
                raise ValueError(f"Invalid {label} collection")
            ids = []
            for record in records:
                if (
                    not isinstance(record, dict)
                    or not isinstance(record.get("id"), str)
                    or not 1 <= len(record["id"]) <= 80
                ):
                    raise ValueError(f"Invalid {label} identifier")
                ids.append(record["id"])
            if len(set(ids)) != len(ids):
                raise ValueError(f"Duplicate {label} identifiers")

        identifiers(data["designs"], "design", MAX_DESIGNS)
        designs = [
            {
                "id": d["id"],
                "name": cls._name(d.get("name")),
                "design": validate_design(d.get("design")),
            }
            for d in data["designs"]
        ]
        cls._validate_playlist(data.get("playlist"), designs)
        if data.get("playlists"):
            identifiers(data["playlists"], "playlist", 20)
        if "selected_playlist_id" in data and not isinstance(data["selected_playlist_id"], str):
            raise ValueError("Selected playlist identifier must be text")
        cls._upgrade(data)
        identifiers(data["playlists"], "playlist", 20)
        playlists = [
            {"id": p["id"], "name": cls._name(p.get("name")), **cls._validate_playlist(p, designs)}
            for p in data["playlists"]
        ]
        ids = {d["id"]: d for d in designs}
        favorites = data["favorites"]
        if not isinstance(favorites, list) or len(favorites) > MAX_DESIGNS:
            raise ValueError("Invalid favorites collection")
        normalized_favorites = []
        seen = set()
        for f in favorites:
            if (
                not isinstance(f, dict)
                or not isinstance(f.get("design_id"), str)
                or f["design_id"] not in ids
                or f["design_id"] in seen
            ):
                raise ValueError("Favorite refers to an unknown or duplicate design")
            addresses = cls._addresses(f.get("addresses"))
            if ids[f["design_id"]]["design"]["width"] != 20 * len(addresses):
                raise ValueError("Favorite width does not match its curtain count")
            seen.add(f["design_id"])
            normalized_favorites.append({"design_id": f["design_id"], "addresses": addresses})
        if len(data["orientations"]) > 100:
            raise ValueError("At most 100 curtain orientations are allowed")
        orientations = {}
        for address, value in data["orientations"].items():
            normalized = cls._addresses([address])[0]
            if normalized in orientations:
                raise ValueError("Duplicate curtain orientation")
            orientations[normalized] = validate_orientation(value)
        identifiers(data["layouts"], "layout", 20)
        layouts = [
            {
                "id": layout["id"],
                "name": cls._name(layout.get("name")),
                "addresses": cls._addresses(layout.get("addresses")),
            }
            for layout in data["layouts"]
        ]
        result = {
            "designs": designs,
            "playlists": playlists,
            "playlist": copy.deepcopy(data["playlist"]),
            "selected_playlist_id": data["selected_playlist_id"],
            "favorites": normalized_favorites,
            "orientations": orientations,
            "layouts": layouts,
        }
        cls._upgrade(result)
        return result

    def _import_data(self, payload):
        backup = payload.get("backup")
        try:
            size = len(json.dumps(backup, allow_nan=False).encode("utf-8"))
        except (TypeError, ValueError, OverflowError) as err:
            raise ValueError("Backup must contain ordinary JSON data") from err
        if size > 4 * 1024 * 1024:
            raise ValueError("Backup exceeds the 4 MB limit")
        if (
            not isinstance(backup, dict)
            or backup.get("format") != "hello-fairy-studio-library"
            or type(backup.get("version")) is not int
            or backup["version"] != 1
        ):
            raise ValueError("Choose a version-1 Hello Fairy Studio library backup")
        incoming = self._validated_data(backup.get("data"))
        mode = payload.get("mode", "merge")
        if mode not in ("merge", "replace"):
            raise ValueError("Import mode must be merge or replace")
        counts = {
            key: len(incoming[key])
            for key in ("designs", "playlists", "favorites", "orientations", "layouts")
        }
        if mode == "replace":
            return incoming, {"mode": mode, "counts": counts}
        result = copy.deepcopy(self.data)
        remaps = {}
        for key in ("designs", "playlists", "layouts"):
            occupied = {r["id"] for r in result[key]}
            mapping = {}
            for record in incoming[key]:
                old = record["id"]
                if old in occupied:
                    record["id"] = uuid4().hex
                occupied.add(record["id"])
                mapping[old] = record["id"]
            remaps[key] = mapping
        for p in incoming["playlists"]:
            for item in p["items"]:
                item["design_id"] = remaps["designs"][item["design_id"]]
            if p["end_design_id"]:
                p["end_design_id"] = remaps["designs"][p["end_design_id"]]
        for f in incoming["favorites"]:
            f["design_id"] = remaps["designs"][f["design_id"]]
        for key in ("designs", "playlists", "layouts", "favorites"):
            result[key].extend(incoming[key])
        for address, orientation in incoming["orientations"].items():
            result["orientations"].setdefault(address, orientation)
        return self._validated_data(result), {
            "mode": mode,
            "counts": counts,
            "message": "Current selection and existing curtain orientations are preserved; colliding identifiers are remapped",
        }

    @staticmethod
    def _upgrade(data):
        """Add collections without changing the Store schema or old selected alias."""
        if "playlists" in data and (
            not isinstance(data["playlists"], list)
            or any(not isinstance(p, dict) for p in data["playlists"])
        ):
            raise ValueError("Saved playlists are invalid")
        if not isinstance(data.get("orientations", {}), dict):
            raise ValueError("Saved orientations are invalid")
        if not data.get("playlists"):
            data["playlists"] = [{"id": "default", "name": "My playlist", **data["playlist"]}]
        selected = data.get("selected_playlist_id", data["playlists"][0]["id"])
        record = next((p for p in data["playlists"] if p["id"] == selected), None)
        if record is None:
            raise ValueError("Selected playlist no longer exists")
        for p in data["playlists"]:
            p.setdefault("shuffle", False)
            p.setdefault("repeat_count", 1)
            p.setdefault("end_design_id", None)
        data["selected_playlist_id"] = record["id"]
        data["playlist"] = copy.deepcopy(record)
        data.setdefault("favorites", [])
        data.setdefault("orientations", {})
        data.setdefault("layouts", [])

    @property
    def active(self) -> bool:
        return self._task is not None and not self._task.done()

    def snapshot(self) -> dict:
        if self._hold_deadline is not None:
            self.status["hold_remaining_seconds"] = max(
                0.0, self._hold_deadline - asyncio.get_running_loop().time()
            )
        self.status["paused"] = self._paused
        return copy.deepcopy(
            {**self.data, "status": self.status, "library_revision": self._library_revision}
        )

    @staticmethod
    def _name(name: str) -> str:
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 80:
            raise ValueError("Give the design a name of 1–80 characters")
        return name.strip()

    @staticmethod
    def _validate_playlist(value: dict, designs: list) -> dict:
        if not isinstance(value, dict) or type(value.get("loop")) is not bool:
            raise ValueError("Playlist needs items and a repeat choice")
        items = value.get("items")
        if not isinstance(items, list) or len(items) > MAX_STEPS:
            raise ValueError(f"A playlist can contain at most {MAX_STEPS} steps")
        ids = {d["id"] for d in designs}
        result = []
        for item in items:
            if (
                not isinstance(item, dict)
                or not isinstance(item.get("design_id"), str)
                or item["design_id"] not in ids
            ):
                raise ValueError("Playlist refers to a design that is not in the library")
            seconds = item.get("seconds")
            if type(seconds) is not int or not MIN_SECONDS <= seconds <= 86400:
                raise ValueError("Each design must play for 10–86400 seconds after upload")
            result.append({"design_id": item["design_id"], "seconds": seconds})
        shuffle = value.get("shuffle", False)
        repeat = value.get("repeat_count", 1)
        ending = value.get("end_design_id") or None
        if type(shuffle) is not bool or type(repeat) is not int or not 1 <= repeat <= 100:
            raise ValueError("Choose shuffle on/off and 1–100 repeats")
        if ending is not None and (not isinstance(ending, str) or ending not in ids):
            raise ValueError("Final design is not in the library")
        return {
            "items": result,
            "loop": value["loop"],
            "shuffle": shuffle,
            "repeat_count": repeat,
            "end_design_id": ending,
        }

    async def _persist(self, next_data: dict) -> None:
        # Publish changes only after a successful disk write.
        await self.store.async_save(next_data)
        self.data = next_data
        self._library_revision = uuid4().hex
        async_dispatcher_send(self.hass, f"{DOMAIN}_library_changed", self.snapshot())

    async def command(self, action: str, payload: dict) -> dict:
        if action == "stop":
            await self.stop()
            return self.snapshot()
        if action in ("pause", "resume"):
            if (
                not self.active
                or self.status.get("mode", "playlist") != "playlist"
                or self._stop.is_set()
            ):
                raise ValueError("Pause and resume are available only for an active playlist")
            self._paused = action == "pause"
            if self._paused:
                uploading = self.status.get("state") in ("uploading", "pausing")
                self.status.update(
                    state="pausing" if uploading else "paused",
                    phase="pausing" if uploading else "paused",
                    message="Finishing the current design before pausing"
                    if uploading
                    else "Playlist paused; current design remains",
                )
            else:
                self.status.update(
                    state="holding" if self._hold_remaining else "uploading",
                    phase="holding" if self._hold_remaining else "uploading",
                    message="Playlist resumed",
                )
            self._wake.set()
            return self.snapshot()
        if action in ("next", "previous"):
            if self._paused:
                raise ValueError("Resume the playlist before navigating")
            if not self.active or self.status.get("mode", "playlist") != "playlist":
                raise ValueError("Start a playlist first")
            if len(self._navigation) >= 20:
                raise ValueError("Wait for queued navigation to finish")
            self._navigation.append(1 if action == "next" else -1)
            self._wake.set()
            return self.snapshot()
        if action in ("recall", "show_message", "start_clock"):
            # Validate synchronously before stopping an existing playback session.
            operation = self._prepare_operation(action, payload)
            try:
                await self.stop()
                async with self._lock:
                    if self.active:
                        raise ValueError("Playback is already starting")
                    self._launch(operation)
                    return self.snapshot()
            except BaseException:
                operation.close()
                raise
        async with self._lock:
            if action == "status":
                self.snapshot()
                return {
                    "status": copy.deepcopy(self.status),
                    "orientations": copy.deepcopy(self.data["orientations"]),
                    "library_revision": self._library_revision,
                }
            if action == "get":
                return self.snapshot()
            if action == "export_library":
                return {
                    "backup": {
                        "format": "hello-fairy-studio-library",
                        "version": 1,
                        "data": copy.deepcopy(self.data),
                    }
                }
            if action == "validate_import":
                _, summary = self._import_data(payload)
                return summary
            if self.active:
                raise ValueError(
                    "Stop the playlist before changing the library or starting another"
                )
            data = copy.deepcopy(self.data)
            if action == "import_library":
                data, _ = self._import_data(payload)
                await self._persist(data)
            elif action == "save_layout":
                addresses = self._addresses(payload.get("addresses"))
                self._coordinators(addresses)
                layout_id = payload.get("layout_id")
                existing = next(
                    (layout for layout in data["layouts"] if layout["id"] == layout_id), None
                )
                if layout_id and existing is None:
                    raise ValueError("Layout no longer exists")
                if existing is None and len(data["layouts"]) >= 20:
                    raise ValueError("At most 20 layouts are allowed")
                record = {
                    "id": layout_id or uuid4().hex,
                    "name": self._name(payload.get("name")),
                    "addresses": addresses,
                }
                if existing is None:
                    data["layouts"].append(record)
                else:
                    data["layouts"][data["layouts"].index(existing)] = record
                await self._persist(data)
            elif action == "delete_layout":
                target = payload.get("layout_id")
                if not any(layout["id"] == target for layout in data["layouts"]):
                    raise ValueError("Layout no longer exists")
                data["layouts"] = [layout for layout in data["layouts"] if layout["id"] != target]
                await self._persist(data)
            elif action == "save_design":
                name = self._name(payload.get("name"))
                design = validate_design(payload.get("design"))
                design_id = payload.get("design_id")
                existing = next((d for d in data["designs"] if d["id"] == design_id), None)
                if design_id and existing is None:
                    raise ValueError("The design to replace no longer exists")
                if existing is None and len(data["designs"]) >= MAX_DESIGNS:
                    raise ValueError(f"The library can hold at most {MAX_DESIGNS} designs")
                if existing is not None and any(
                    f["design_id"] == design_id and len(f["addresses"]) * 20 != design["width"]
                    for f in data["favorites"]
                ):
                    raise ValueError("Remove this favorite before changing its curtain count")
                record = {"id": design_id or uuid4().hex, "name": name, "design": design}
                if existing is None:
                    data["designs"].append(record)
                else:
                    data["designs"][data["designs"].index(existing)] = record
                await self._persist(data)
            elif action == "delete_design":
                design_id = payload.get("design_id")
                if any(
                    i["design_id"] == design_id for p in data["playlists"] for i in p["items"]
                ) or any(p.get("end_design_id") == design_id for p in data["playlists"]):
                    raise ValueError("Remove this design from the playlist before deleting it")
                if not any(d["id"] == design_id for d in data["designs"]):
                    raise ValueError("Design no longer exists")
                data["designs"] = [d for d in data["designs"] if d["id"] != design_id]
                data["favorites"] = [f for f in data["favorites"] if f["design_id"] != design_id]
                await self._persist(data)
            elif action == "save_playlist":
                playlist = self._validate_playlist(payload.get("playlist"), data["designs"])
                playlist_id = payload.get("playlist_id", data["selected_playlist_id"])
                existing = next((p for p in data["playlists"] if p["id"] == playlist_id), None)
                if existing is None and playlist_id:
                    raise ValueError("Playlist no longer exists")
                if existing is None and len(data["playlists"]) >= 20:
                    raise ValueError("At most 20 playlists are allowed")
                record = {
                    "id": playlist_id or uuid4().hex,
                    "name": self._name(
                        payload.get("name", existing["name"] if existing else "My playlist")
                    ),
                    **playlist,
                }
                if existing is None:
                    data["playlists"].append(record)
                else:
                    data["playlists"][data["playlists"].index(existing)] = record
                data["selected_playlist_id"] = record["id"]
                self._upgrade(data)
                await self._persist(data)
            elif action == "select_playlist":
                data["selected_playlist_id"] = payload.get("playlist_id")
                self._upgrade(data)
                await self._persist(data)
            elif action == "delete_playlist":
                if len(data["playlists"]) == 1:
                    raise ValueError("Keep at least one playlist")
                target = payload.get("playlist_id")
                if not any(p["id"] == target for p in data["playlists"]):
                    raise ValueError("Playlist no longer exists")
                data["playlists"] = [p for p in data["playlists"] if p["id"] != target]
                if data["selected_playlist_id"] == target:
                    data["selected_playlist_id"] = data["playlists"][0]["id"]
                self._upgrade(data)
                await self._persist(data)
            elif action == "set_favorite":
                record = self._design(payload.get("design_id"))
                enabled = payload.get("enabled")
                if type(enabled) is not bool:
                    raise ValueError("Favorite enabled must be true or false")
                addresses = payload.get("addresses")
                if enabled:
                    self._validate_targets([record], addresses)
                data["favorites"] = [f for f in data["favorites"] if f["design_id"] != record["id"]]
                if enabled:
                    data["favorites"].append(
                        {
                            "design_id": record["id"],
                            "addresses": [a.strip().upper() for a in addresses],
                        }
                    )
                await self._persist(data)
            elif action == "save_orientation":
                address = payload.get("address")
                self._coordinators([address])
                data["orientations"][address.strip().upper()] = validate_orientation(
                    {
                        k: payload.get(k, False if k != "rotation" else 0)
                        for k in ("rotation", "flip_h", "flip_v")
                    }
                )
                await self._persist(data)
            elif action == "start":
                self._start(payload.get("addresses"), payload.get("playlist_id"))
            else:
                raise ValueError("Unknown Studio library action")
            return self.snapshot()

    def _coordinators(self, addresses: list) -> list:
        if (
            not isinstance(addresses, list)
            or not 1 <= len(addresses) <= 8
            or any(not isinstance(a, str) for a in addresses)
        ):
            raise ValueError("Choose one to eight configured curtains in left-to-right order")
        addresses = [a.strip().upper() for a in addresses]
        if len(set(addresses)) != len(addresses):
            raise ValueError("Playlist curtains must be unique")
        available = {
            e.runtime_data.coordinator.device_address.upper(): e.runtime_data.coordinator
            for e in self.hass.config_entries.async_entries(DOMAIN)
            if getattr(e, "runtime_data", None) is not None
        }
        if any(a not in available for a in addresses):
            raise ValueError("A selected curtain is not configured or loaded")
        return [available[a] for a in addresses]

    def _design(self, design_id):
        record = next((d for d in self.data["designs"] if d["id"] == design_id), None)
        if record is None:
            raise ValueError("Design no longer exists")
        return copy.deepcopy(record)

    def _validate_targets(self, records, addresses):
        coordinators = self._coordinators(addresses)
        if any(s["design"]["width"] != len(coordinators) * 20 for s in records):
            raise ValueError("Every design must match the selected curtain count")
        return coordinators

    def _start(self, addresses, playlist_id=None):
        self._coordinators(addresses)
        selected = (
            self.data["playlist"]
            if playlist_id is None
            else next((p for p in self.data["playlists"] if p["id"] == playlist_id), None)
        )
        if selected is None:
            raise ValueError("Playlist no longer exists")
        playlist = self._validate_playlist(selected, self.data["designs"])
        if not playlist["items"]:
            raise ValueError("Add a saved design to the playlist first")
        steps = [{**i, **self._design(i["design_id"])} for i in playlist["items"]]
        records = steps + (
            [self._design(playlist["end_design_id"])] if playlist["end_design_id"] else []
        )
        coordinators = self._validate_targets(records, addresses)
        self._launch(self._run(steps, coordinators, playlist))

    def _launch(self, operation):
        self._paused = False
        self._hold_deadline = None
        self._hold_remaining = 0.0
        self._stop.clear()
        self._wake.clear()
        self._navigation.clear()
        mode = {"_clock": "clock", "_message": "message", "_recall": "design"}.get(
            operation.cr_code.co_name, "playlist"
        )
        self.status = {
            "state": "uploading",
            "mode": mode,
            "kind": mode,
            "message": "Starting playback",
            "index": 0,
        }
        self._task = self.hass.async_create_background_task(
            self._guard(operation), "Hello Fairy Studio playback"
        )

    async def _upload(self, record, coordinators):
        design = record["design"]
        self.status.update(
            state="pausing" if self._paused else "uploading",
            phase="pausing" if self._paused else "uploading",
            design_name=record.get("name", "Design"),
            name=record.get("name", "Design"),
            completed_curtains=0,
            total_curtains=len(coordinators),
            hold_remaining_seconds=0,
        )
        frames = [split_virtual_frame(f, len(coordinators)) for f in design["frames"]]
        for i, coordinator in enumerate(coordinators):
            if self._stop.is_set():
                return
            orientation = self.data["orientations"].get(coordinator.device_address.upper())
            outgoing = [transform_frame(f[i], orientation) for f in frames]
            if design["kind"] == "animation":
                await coordinator.set_two_picture_animation(outgoing)
            else:
                await coordinator.set_frame(outgoing[0])
            settings = design["settings"]
            await coordinator.set_diy_playback(
                design["kind"], settings["movement"], settings["speed"], settings["brightness"]
            )
            self.status["completed_curtains"] = i + 1

    async def _run(self, steps, coordinators, playlist):
        cycle = 0
        while not self._stop.is_set():
            order = list(range(len(steps)))
            if playlist["shuffle"]:
                random.shuffle(order)
            position = 0
            while position < len(order) and not self._stop.is_set():
                await self._wait_playlist_unpaused()
                if self._stop.is_set():
                    return
                index = order[position]
                step = steps[index]
                self.status = {
                    "state": "uploading",
                    "mode": "playlist",
                    "message": f"Uploading {step['name']}",
                    "index": index,
                    "name": step["name"],
                    "total": len(steps),
                    "cycle": cycle + 1,
                }
                await self._upload(step, coordinators)
                if self._stop.is_set():
                    return
                self.status = {
                    **self.status,
                    "state": "holding",
                    "message": f"Last transmitted: {step['name']} — physical display unconfirmed",
                    "seconds": step["seconds"],
                    "since": dt_util.utcnow().isoformat(),
                }
                if not self._navigation or self._paused:
                    await self._hold(step["seconds"])
                delta = self._navigation.pop(0) if self._navigation else 1
                position = max(0, position + delta)
                if not self._navigation and not self._stop.is_set():
                    self._wake.clear()
            cycle += 1
            if not playlist["loop"] and cycle >= playlist["repeat_count"]:
                await self._wait_playlist_unpaused()
                if playlist["end_design_id"] and not self._stop.is_set():
                    await self._upload(self._design(playlist["end_design_id"]), coordinators)
                return

    def _prepare_operation(self, action, payload):
        addresses = payload.get("addresses")
        if action == "recall":
            record = self._design(payload.get("design_id"))
            if addresses is None:
                favorite = next(
                    (f for f in self.data["favorites"] if f["design_id"] == record["id"]), None
                )
                addresses = favorite["addresses"] if favorite else None
            coordinators = self._validate_targets([record], addresses)
            return self._recall(record, coordinators)
        coordinators = self._coordinators(addresses)
        width = len(coordinators) * 20
        color = payload.get("color_byte", 0)
        background = payload.get("background_byte", 254)
        if action == "show_message":
            pages = render_pages(
                payload.get("text", ""), width, color, background, payload.get("icon", "none")
            )
            seconds = payload.get("duration", 10)
            if type(seconds) is not int or not 10 <= seconds <= 86400:
                raise ValueError("Message duration must be 10–86400 seconds per page")
            restore = (
                self._design(payload["restore_design_id"])
                if payload.get("restore_design_id")
                else None
            )
            if restore:
                self._validate_targets([restore], addresses)
            return self._message(pages, coordinators, seconds, restore)
        interval = payload.get("interval", 60)
        if type(interval) is not int or not 60 <= interval <= 86400:
            raise ValueError("Clock interval must be 60–86400 seconds")
        clock_format = payload.get("format", "24h")
        render_clock(dt_util.now(), width, clock_format, color, background)
        return self._clock(coordinators, width, clock_format, color, background, interval)

    @staticmethod
    def _picture(frame, width, name):
        return {
            "name": name,
            "design": {
                "kind": "picture",
                "width": width,
                "frames": [frame],
                "settings": {"movement": "still", "speed": 30, "brightness": 100},
            },
        }

    async def _recall(self, record, coordinators):
        self.status = {
            "state": "uploading",
            "mode": "design",
            "message": f"Uploading {record['name']}",
        }
        await self._upload(record, coordinators)

    async def _message(self, pages, coordinators, seconds, restore):
        for index, page in enumerate(pages):
            if self._stop.is_set():
                return
            self.status = {
                "state": "uploading",
                "mode": "message",
                "message": f"Uploading message page {index + 1}/{len(pages)}",
            }
            await self._upload(self._picture(page, len(coordinators) * 20, "Message"), coordinators)
            if self._stop.is_set():
                return
            self.status = {
                **self.status,
                "state": "holding",
                "message": "Message transmitted; physical display unconfirmed",
            }
            await self._hold(seconds)
        if restore and not self._stop.is_set():
            await self._upload(restore, coordinators)

    async def _clock(self, coordinators, width, clock_format, color, background, interval):
        while not self._stop.is_set():
            self.status = {
                "state": "uploading",
                "mode": "clock",
                "kind": "clock",
                "message": "Updating clock",
            }
            frame = render_clock(dt_util.now(), width, clock_format, color, background)
            await self._upload(self._picture(frame, width, "Clock"), coordinators)
            if self._stop.is_set():
                return
            self.status = {
                "state": "holding",
                "mode": "clock",
                "kind": "clock",
                "message": "Clock transmitted; physical display unconfirmed",
            }
            await self._hold(interval)

    async def _guard(self, operation):
        try:
            await operation
            if not self._stop.is_set():
                self.status = {
                    **self.status,
                    "state": "completed",
                    "phase": "completed",
                    "hold_remaining_seconds": 0,
                    "message": "Playback completed; physical display unconfirmed",
                }
        except asyncio.CancelledError:
            self.status = {"state": "stopped", "message": "Playback cancelled; check the lights"}
            raise
        except Exception as err:
            self.status = {
                **self.status,
                "state": "error",
                "phase": "error",
                "message": f"Stopped after transfer failure: {err}",
            }
            _LOGGER.exception("Studio playback stopped; no automatic replay")
        finally:
            self._paused = False
            self._hold_deadline = None
            if self._stop.is_set() and self.status["state"] != "error":
                self.status = {
                    **self.status,
                    "state": "stopped",
                    "phase": "stopped",
                    "hold_remaining_seconds": 0,
                    "message": "Playlist stopped; last design remains",
                }

    async def _wait_playlist_unpaused(self) -> None:
        """Honor pause before any subsequent design, even with queued navigation."""
        while self._paused and not self._stop.is_set():
            self._wake.clear()
            self.status.update(
                state="paused",
                phase="paused",
                message="Playlist paused; current design remains",
            )
            await self._wake.wait()

    async def _hold(self, seconds: int) -> None:
        """Freeze the remaining hold while paused, without repeating an upload."""
        self._hold_remaining = float(seconds)
        loop = asyncio.get_running_loop()
        try:
            while self._hold_remaining > 0 and not self._stop.is_set():
                self._wake.clear()
                if self._paused:
                    self._hold_deadline = None
                    self.status.update(
                        state="paused",
                        phase="paused",
                        hold_remaining_seconds=self._hold_remaining,
                        message="Playlist paused; current design remains",
                    )
                    await self._wake.wait()
                    continue
                if self._navigation:
                    return
                self.status.update(
                    state="holding", phase="holding", hold_remaining_seconds=self._hold_remaining
                )
                self._hold_deadline = loop.time() + self._hold_remaining
                try:
                    await asyncio.wait_for(self._wake.wait(), self._hold_remaining)
                except TimeoutError:
                    pass
                self._hold_remaining = max(0.0, self._hold_deadline - loop.time())
                self._hold_deadline = None
        finally:
            self._hold_deadline = None
            self.status["hold_remaining_seconds"] = self._hold_remaining

    async def stop(self) -> None:
        """Finish the current curtain operation rather than cancelling a partial frame."""
        if self.active:
            self._stop.set()
            self._wake.set()
            self.status = {
                **self.status,
                "state": "stopping",
                "message": "Finishing current upload…",
            }
            await asyncio.shield(self._task)


async def async_stop_playlist(hass: HomeAssistant) -> None:
    """Let deliberate light controls take over from background playback."""
    if hass.services.has_service(DOMAIN, "stop_playlist"):
        await hass.services.async_call(DOMAIN, "stop_playlist", {}, blocking=True)


async def async_setup_library(hass: HomeAssistant) -> StudioLibrary:
    """Register admin-only editing, automation actions and orderly shutdown."""
    library = StudioLibrary(hass)
    load_error = None
    try:
        await library.async_load()
    except (ValueError, OSError, HomeAssistantError) as err:
        load_error = f"Studio library could not load: {err}"
        _LOGGER.error("%s", load_error)

    @websocket_api.websocket_command(
        {
            vol.Required("type"): f"{DOMAIN}/studio/library",
            vol.Required("action"): str,
            vol.Optional("payload", default=dict): dict,
        }
    )
    @websocket_api.require_admin
    @websocket_api.async_response
    async def handle_library(hass, connection, msg):
        try:
            if load_error:
                raise ValueError(load_error)
            result = await library.command(msg["action"], msg["payload"])
        except (ValueError, OSError, HomeAssistantError) as err:
            connection.send_error(msg["id"], "library_failed", str(err))
        else:
            connection.send_result(msg["id"], result)

    async def start(call: ServiceCall) -> None:
        try:
            if load_error:
                raise ValueError(load_error)
            await library.command("start", dict(call.data))
        except ValueError as err:
            raise HomeAssistantError(str(err)) from err

    async def stop(call: ServiceCall) -> None:
        await library.stop()

    async def shutdown(event) -> None:
        await library.stop()

    websocket_api.async_register_command(hass, handle_library)
    hass.services.async_register(
        DOMAIN,
        "start_playlist",
        start,
        schema=vol.Schema({vol.Required("addresses"): [str], vol.Optional("playlist_id"): str}),
    )
    hass.services.async_register(DOMAIN, "stop_playlist", stop, schema=vol.Schema({}))

    async def playback_action(call: ServiceCall) -> None:
        action = {
            "show_design": "recall",
            "playlist_next": "next",
            "playlist_previous": "previous",
            "playlist_pause": "pause",
            "playlist_resume": "resume",
        }.get(call.service, call.service)
        try:
            if load_error:
                raise ValueError(load_error)
            await library.command(action, dict(call.data))
        except (ValueError, OSError) as err:
            raise HomeAssistantError(str(err)) from err

    schemas = {
        "show_design": {vol.Required("design_id"): str, vol.Optional("addresses"): [str]},
        "playlist_next": {},
        "playlist_previous": {},
        "playlist_pause": {},
        "playlist_resume": {},
        "show_message": {
            vol.Required("addresses"): [str],
            vol.Optional("text", default=""): str,
            vol.Optional("color_byte", default=0): int,
            vol.Optional("background_byte", default=254): int,
            vol.Optional("icon", default="none"): vol.In(["none", "bell", "heart", "door"]),
            vol.Optional("duration", default=10): vol.All(int, vol.Range(min=10, max=86400)),
            vol.Optional("restore_design_id"): str,
        },
        "start_clock": {
            vol.Required("addresses"): [str],
            vol.Optional("format", default="24h"): vol.In(["24h", "12h"]),
            vol.Optional("color_byte", default=0): int,
            vol.Optional("background_byte", default=254): int,
            vol.Optional("interval", default=60): vol.All(int, vol.Range(min=60, max=86400)),
        },
    }
    for service, schema in schemas.items():
        hass.services.async_register(DOMAIN, service, playback_action, schema=vol.Schema(schema))
    hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, shutdown)
    return library
