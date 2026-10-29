# Changes

> Generated with [aurora@aurora-smart-home (ha-integration-dev skill)](https://github.com/tonylofgren/aurora-smart-home)

## 2.0.0

- Bump the integration, Studio header and browser module cache versions to 2.0.0.
- Restore original string-light documentation, protocol details, troubleshooting, contribution history and License wording; document Studio in an additive section.
- Restore still-applicable API/coordinator comments and remove generated-attribution headers from the existing API, coordinator, light and number modules.
- Validate and normalize DIY service payloads and resolve all target coordinators before stopping a running playlist. Invalid inputs and missing targets now leave playback running without writes; valid requests still stop it before taking over.
- Add active-playlist regression coverage for invalid pixel/frame/animation/playback/virtual-frame requests, missing targets and valid manual takeover.

## 1.1.0rc5

- Add integrated experimental native controls with one-curtain explicit capability inspection and an exact model/firmware gate.
- Add built-in microphone music modes only when advertised by the device, with status verification and no phone audio streaming.
- Add preset speed only after a genuine capability reply and current built-in-scene status, with readback verification.
- Add explicit device-clock synchronization, a one-time power countdown/cancel, and single-slot device schedules after both timer banks are read successfully.
- Convert schedules through the APK's UTC+08 time basis with weekday rollover; document fixed-offset and daylight-saving limits.
- Inspect font support without exposing unverified native text transfers, true firmware pause, scene loops or device storage writes.
- Keep capability discovery tied to the current connection and preserve the existing working controls, image preflight and bounded connection recovery.
- Include a sanitized native-protocol evidence audit and one controlled music-response check. rc3 was physically confirmed by the user; the user subsequently reported release validation of rc5. Per-feature and long-term execution evidence remains separate.

## 1.1.0rc4

- Add named curtain layouts and validated complete-library JSON backup/import, with safe merge and explicit replacement.
- Add a separate local estimated movement preview with no device writes, no automatic playback and reduced-motion support.
- Add playlist pause/resume that freezes remaining hold time and honors queued navigation without re-uploading the current design.
- Show per-curtain transfer completion, current design/cycle and remaining hold time; preserve partial counts on error.
- Block competing Studio sends/status/layout changes during an import and preserve the editor draft.
- Add allowlisted Home Assistant diagnostics without images, private names/addresses or new BLE queries.
- Record the user's successful rc3 test report separately from unconfirmed rc4 hardware behavior.

## 1.1.0rc3

- Add pixel text, local time snapshots, hue palettes and custom palette input.
- Add curtain/rectangular drawing selections, region patterns/fill/erase, mirroring, centered rotation and tile repetition; edits stay local and undoable.
- Persist per-curtain clockwise rotation and flips, applied once at Studio/backend output while saved artwork remains portable.
- Add favorite recall with explicit saved targets and generated Home Assistant button entities.
- Add up to 20 named playlists, finite cycles, shuffle, queued next/previous and an optional final design.
- Add minute-resolution clock and paginated text/icon notifications with an optional explicit final saved design, using existing guarded full-frame transfers.
- Add automation actions for recall, navigation, messages, clocks and explicit playlist IDs.
- Keep shared clients current using compact status/revision checks; do not repeatedly download image catalogs.
- Retain ordinary controls, MTU/model preflight, bounded connection setup and no partial-transfer replay. Native animation hardware limits remain unchanged.

## 1.1.0rc2

- Add a persistent shared design library with named thumbnails, replacement and deletion, and editor recall without writes.
- Add one HA-owned ordered playlist with per-step hold time, repeat, graceful stop and automation start/stop actions. It continues with the browser closed and never resumes automatically after restart.
- Stop background playback before manual light/preset/Studio controls or integration unload. Preserve transfer errors even if Stop was requested during a failing upload.
- Bound storage and playlist sizes, validate saved frame/settings data and refuse deletion of referenced designs.
- Retain every feature from the combined rc1 candidate below.

## 1.1.0rc1

- Bundle Curtain Studio with the integration: image import, painting, patterns, saved designs and ordered multi-curtain layouts.
- Add capture-shaped full-frame and two-picture native uploads, guarded by fresh model information and verified transport capacity.
- Add APK-derived movement, speed and DIY brightness controls, with timestamped device status distinct from upload history.
- Bound connection setup retries; clean up failed clients, stop sequential transfers at the first failure and avoid partial image replay.
- Use config-entry runtime data and preserve existing entity identifiers and standard command formats.
- Share validated brightness decoding between Studio and HA entities; retain legacy scaling for unverified models.
- Add real HA framework tests, browser workflow tests and CI; declare minimum HA 2026.9.3.

Experimental release candidate: physical regression on this package and native-control verification remain outstanding. See VALIDATION.md.
