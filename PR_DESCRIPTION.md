# Release 2.1.1: Preset speed control entity (#12) & idle BLE disconnect option (#8)

This release ports and fixes the universal preset **Speed** number entity from [PR #12](https://github.com/nzrutman/hello_fairy_ble/pull/12) by @jr4 on top of `v2.1.0` (`9a212b7`), while preserving the session-gated `native.py` `scene_speed` capability contract and keeping cached speed state synchronized between both paths. It also adds a per-device **Idle Bluetooth disconnect delay** option for strips that flicker while holding a persistent BLE link (#8).

### Changes

- **Universal Speed number entity (`0x0C`):** Add `CMD_SPEED = 0x0C` (`const.py`), `HelloFairyAPI.set_speed()` (`api.py`), `HelloFairyApiData.current_speed` / `HelloFairyCoordinator.set_speed()` (`coordinator.py`), and `HelloFairySpeedNumber` (`number.py`, 0–100 slider) with English, German, and Spanish translations.
- **Fixes over PR #12:**
  - Preserve speed `0` in `HelloFairySpeedNumber.native_value` (`is not None` check instead of falsy truthiness).
  - Push coordinator state immediately in `set_speed()` (`expect_ack=False`, since `0x0C` does not emit a 4-byte ACK) and call `async_request_refresh()` after updating.
  - Decode `0x0C` device notifications into `current_speed` and sync `current_speed` during `inspect_native()` / `set_native("scene_speed", ...)` without lowering `native.py`'s `scene_speed_supported` session capability gate.
  - Use `mdi:speedometer`, gate availability on `device_discovered`, validate `0..100` bounds before stopping active Studio playlists.
- **Configurable Idle BLE Disconnect (#8):**
  - Add `HelloFairyOptionsFlow` (`idle_disconnect_seconds`, `0–600` seconds, default `0` to keep existing persistent-connection behavior) with English, German, and Spanish translations.
  - Schedule idle `disconnect_if_idle()` cleanup in `HelloFairyAPI` after commands finish when `idle_disconnect_seconds > 0` (canceling on new commands, active DIY transfers, or explicit `disconnect()`), and expose `idle_disconnect_seconds` in `diagnostics.py` (`transport`).
- **Tests & Documentation:** Add `0x0C` and idle-disconnect API, coordinator, entity, options-flow, diagnostics, and playlist-interlock regressions in `tests/ha/test_api.py`, `tests/ha/test_light_and_sync.py`, and `tests/ha/test_library.py`; bump versions to `2.1.1` across `manifest.json`, `__init__.py`, `api.py`, `studio.py`, frontend modules/header, `tests/browser/studio.cjs`, `CHANGELOG.md`, `README.md`, `STUDIO_GUIDE.md`, and `VALIDATION.md`.

### Validation

- 311 tests passed on Home Assistant **2026.9.3** (`hello-fairy-ha-tests:2026.9.3`, Python 3.14, offline container).
- 311 tests passed on Home Assistant **2026.10.1** (`hello-fairy-ha-tests:2026.10.1`, Python 3.14, offline container).
- Official `hassfest` passed (`1` integration, `0` invalid integrations).
- Ruff 0.15.14 lint (`ruff check --no-cache .`) and format (`ruff format --check --no-cache .`) passed.
- Prettier 3.6.2 check (`npx prettier --end-of-line auto --check ...`) passed.
- 98 offline browser/helper checks passed (`npm run test:browser`).
