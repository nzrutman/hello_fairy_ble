# Release candidate validation

> Generated with [aurora@aurora-smart-home (ha-integration-dev skill)](https://github.com/tonylofgren/aurora-smart-home)

Candidate **2.0.0**, based on upstream `cc166bc3d847cd8ec6f5f217717403bbf2b60c78` (1.0.0). One combined package and proposed PR.

## Automated checks

- 271 tests passed on real Home Assistant **2026.9.3**, Python 3.14, test plugin 0.13.366.
- 271 tests passed on real Home Assistant **2026.10.1**, Python 3.14, test plugin 0.13.372.
- 97 helper/browser workflow checks passed with Node and headless Edge using Playwright 1.62.1: 27 original Studio checks, 13 drawing-tool checks, 13 advanced library checks, five orientation checks, 10 movement-preview checks, 12 backup/layout/playback finishing checks, eight combined panel-layout/native/import-interlock checks, and nine native-control checks.
- Official hassfest passed: one integration, zero invalid integrations, no warnings (image digest `sha256:4b1adfb1e0a37710af0390708eb8000230b80b2193ccffbeed0a901fa9765181`).
- Ruff 0.15.14 lint/format and Prettier 3.6.2 format checks passed.

HA tests use the actual framework, service validation, HTTP and authenticated WebSocket APIs, with simulated BLE clients. Browser checks use a local mock HA connection. These do not contact the user's Home Assistant or lights. Python tests ran in containers with networking disabled. GitHub CI passed both HA jobs and the Chromium browser job for the original PR revision eaa375e on 27 October 2026. The 2.0.0 review follow-up is checked locally and will receive its own hosted CI results after pushing.

Tests cover model/MTU gating, capture-shaped framing, brightness compatibility, bounded connection retries and cleanup, no partial replay, ordered multi-device failure, entry cleanup, admin authorization, static-file serving, image editing, saved designs, animation controls and phone layout.

The rc2 additions test persistent library reload without starting playback, failed-save rollback, replacement/deletion guards, malformed designs/durations and limits, serial playlist uploads/settings before holding, graceful Stop, failure without replay, ordinary controls taking over, admin-only editing, and automation actions. Browser coverage includes the actual library component with mocked HA responses; playlist execution itself is covered by real-framework Python tests.

The rc3 additions cover multiple-playlist storage migration/selection, finite cycles and final designs, shuffle, queued navigation, saved favorite targets and HA button creation, orientation parity and logical artwork preservation, minute clock stop, paginated messages and explicit restoration, icon-only notifications, invalid requests preserving an existing job, compact revision/orientation state, explicit playlist automation IDs, and malformed library isolation from ordinary controls. Drawing checks cover bounds, clipping, wrap, hue mapping, transforms, undo, local edits and separate animation frames. This is automated evidence, not hardware confirmation of the new displays.


The rc4 additions cover strict complete-library validation and atomic restore/merge with remapped references, private backup boundaries, named layouts without writes, pause/resume remaining-time preservation and queued-navigation races, progress retention on failure, privacy-filtered diagnostics, local preview cleanup/nonmutation, and combined-panel import interlocks. Backend tests use real HA; all radio calls remain simulated.

The rc5 additions cover strict device-info extension parsing, exact researched profile restrictions, connection-specific notifications/capability grants, advertised device-microphone music with ACK and complete status verification, read-only scene-speed discovery with known-preset gating and value readback, font discovery without upload, explicit clock echo verification, countdown status/cancel, both timer banks, UTC+08/local conversion, single-slot readback and preservation of unrelated schedules, and no command replay after errors. UI checks cover explicit single-target inspection, disabled unsupported controls, strict bounds, mobile layout, and interlocks with editor/status/import/layout actions. Unanswered capability queries remain unavailable. No BLE commands were sent to real lights during development.

The 2.0.0 review follow-up adds 18 real-HA service regressions with a running Studio playlist: invalid frame length/colors, missing or conflicting pixel colors, malformed animation frames, invalid playback combinations, invalid/duplicate virtual targets, missing targets across every DIY service, and valid manual takeover. Invalid requests leave the same playlist task holding without new writes; a valid request stops playback before writing. The maintainer independently confirmed ordinary string-light controls and unsupported-curtain rejection on their hardware, and ran the earlier 253-test/97-check suites successfully.

## Physical evidence and release checks

On 16 October 2026, after delivery of rc5, the tester reported that the release had been validated. This records the tester's release-level confirmation on the curtain/ESPHome proxy setup. No separate feature-by-feature checklist, extended reliability run or future schedule-execution report was supplied. The limitations below remain documented.

The user reported successful physical testing of rc3 in this conversation: “i did test it, all good.” That confirmation is recorded for rc3. Earlier explicit confirmations included ordinary power/presets, complete single-curtain images, combined 40×20 images and native two-picture playback. No new Bluetooth capture or APK evidence was needed for rc4.

New rc4 and rc5 behavior has automated coverage and is covered by the subsequent general release-validation report, without an individual hardware checklist: playlist pause/resume and progress, named layouts, complete-library backup/import, estimated local preview, and the newly added native music/speed/timing controls. The preview is deliberately a browser simulation and is never claimed to match measured native timing. Diagnostics and editing/backup actions issue no new BLE queries or writes.

The focused rc5 physical check is a single-curtain Energy music response after explicit capability inspection, described in STUDIO_GUIDE.md. Hardware timing, schedule persistence/execution and the additional rc4 library/playback behavior remain outside the existing rc3 confirmation. Existing rc3 hardware confirmation should not be discarded or re-labelled as untested.

Unverified limits remain: other firmware/DIY types, direct adapters, extended-load radio reliability, cross-curtain phase alignment, pixel readback and future HA/ESPHome releases. These are separate from the user's successful test of the supported setup.

## Reproducing checks

Use Python 3.14 on Linux. Install `pytest-homeassistant-custom-component==0.13.366` or `==0.13.372`, run `python tests/install_dependencies.py`, then `pytest tests/ha -q`. The helper installs that HA version's Bluetooth/USB/network/frontend dependencies.

For Studio, use Node 22+: `npm ci`, `npx playwright install chromium`, then `npm run test:browser`. On Windows with Edge, set `PW_CHANNEL=msedge`. Reports/screenshots go to `test-results/browser`.

Use Ruff 0.15.14: `ruff check --no-cache .` and `ruff format --check --no-cache .`. JavaScript: `npm run format:check`. HACS and official hassfest workflows are included.
