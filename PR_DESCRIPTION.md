# Release 2.1.0: BlueZ MTU acquisition, explicit status sync, standard light fixes and profile diagnostics

This release addresses issues reported after v2.0.0 while keeping all existing wire formats, fail-closed DIY safety gates, and non-polling startup behavior intact.

### Changes

- **Direct BlueZ adapter DIY support (#9):** Acquire the negotiated ATT MTU via `_acquire_mtu()` on local BlueZ backends (`BleakClientBlueZDBus`, bounded to 5s, cached once per backend) before preflight checks on both fresh and reused verified connections. Genuine low-MTU links and acquisition errors still fail closed before any D0/DA write.
- **Explicit status sync for all devices (#1):** Add a diagnostic **Refresh status** button entity and `hello_fairy_ble.refresh_status` action (`AA 01 00 AB`) without enabling automatic startup/periodic BLE polling or interrupting active Studio playlists.
- **Standard light control fixes (#8):** Preserve requested or current brightness in `set_color_rgb` instead of forcing 100%, eliminate intermediate white-flash `set_brightness` writes when turning on with `rgb_color` or `effect`, keep preset mode active when dimming, avoid coercing explicit `0` brightness to `50`, clear stale `current_preset` outside preset mode, and keep the 0.1s power-on settle delay when applying standalone brightness. (Hardware-specific flicker on non-curtain strips remains under investigation via user diagnostics.)
- **Unsupported device profile diagnostics (#10):** Keep the fail-closed `(400, 20, 20, 3)` DIY gate for unverified hardware such as the 832-LED tree, and surface the device-reported `model`, `firmware`, `led_count`, `columns`×`rows`, and `diy_type` in DIY-blocked errors/logs and in Curtain Studio's **Device status & last sent** panel.
- **Version 2.1.0:** Bump `manifest.json`, API/integration/Studio versions, frontend module cache query strings, and documentation (`CHANGELOG.md`, `README.md`, `PROTOCOL.md`, `STUDIO_GUIDE.md`, `VALIDATION.md`).

### Validation

- 288 tests passed on Home Assistant **2026.9.3** (`hello-fairy-ha-tests:2026.9.3`, Python 3.14, offline container).
- 288 tests passed on Home Assistant **2026.10.1** (`hello-fairy-ha-tests:2026.10.1`, Python 3.14, offline container).
- 97 offline browser/helper checks passed with Node and headless Edge using Playwright 1.62.1.
- Official `hassfest` passed (`1` integration, `0` invalid integrations).
- Ruff 0.15.14 lint/format and Prettier 3.6.2 formatting checks passed.

Automated suites simulate Bluetooth I/O and Home Assistant browser sessions. Physical hardware confirmation for the BlueZ `_acquire_mtu()` pattern was reported in #9; explicit status sync, standard light control fixes, and profile diagnostics await release confirmation on real devices, and #8/#10 remain open for reporter diagnostics/captures where hardware specifics differ.
