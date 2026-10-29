# Major expansion: integrated Curtain Studio, full-image uploads and native curtain controls

This PR substantially expands the integration beyond its existing light controls, adding a complete curtain design and playback interface directly inside Home Assistant. It brings image uploads, drawing tools, saved designs, multi-curtain layouts, playlists and additional native device controls together in one HACS package.

Existing power, brightness, color, presets and entity identifiers are preserved. No separate dashboard card, add-on or external application is required.

### Features

- Image import, painting, reusable patterns, pixel text, palettes and multi-curtain layouts.
- Saved designs, favorite HA buttons, playlists, clock/message displays, orientation corrections, library backup/import and local movement preview.
- Complete 20×20 image uploads and native two-picture animations.
- Native movement, DIY speed and brightness.
- Capability-gated microphone music, preset speed, explicit clock sync, countdowns and individual device schedules.
- Timestamped device reports displayed separately from upload history.

### Bluetooth reliability

Controlled tests showed that splitting an image into many small writes retained only the final packet. Uploads now reproduce the captured Android six-packet sequence after verifying the device profile, connection source, MTU and write capacity.

Commands are serialized. Connection setup uses bounded retries and cleanup; partial uploads and uncertain device writes are never automatically replayed. Additional native controls require capability checks and available readback. Schedule conversion handles timezone and weekday rollover, with documented DST limitations.

### Validation

- 253 tests passed on each of Home Assistant 2026.9.3 and 2026.10.1, using real framework components with simulated Bluetooth I/O.
- 97 offline browser/helper checks passed.
- Official hassfest, Ruff and Prettier checks passed.
- I have validated the release on my curtain setup using an ESPHome Bluetooth proxy.

Full pixel readback, synchronized cross-curtain playback, native font uploads, extra device storage, true firmware animation pause and native scene loops are not claimed. Evidence gaps and hardware limitations are documented.

Includes tests, CI workflows, installation instructions and protocol evidence. No vendor APK, decompiled source, raw Bluetooth captures or credentials are included.

### Ongoing collaboration

I appreciate that this is a substantial addition to review and maintain. I’m happy to help work through review feedback, investigate compatibility issues and continue improving the integration after this PR. If you would prefer a different structure or a staged review, I’m happy to coordinate while keeping the end result available as one integrated package.
