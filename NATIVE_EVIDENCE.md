# Native feature evidence — 1.1.0rc5

> Generated with [aurora@aurora-smart-home (ha-integration-dev skill)](https://github.com/tonylofgren/aurora-smart-home)

## Source and confidence

The official Hello Fairy website linked the inspected beta APK: package `com.lenzetech.hellofairy`, version 3.6.118, code 306118. APK SHA-256: `990d09e21a649915564867ec480e2d69b030a519995c18a34a6714ac1b686985`. The successful Android capture has SHA-256 `57f00fbc2d50e3a4091454e9a10c1b7b79c5bdff2eaf01ee514c41a4ac8192e3`. Other app packages or versions may differ.

Source references below name classes in that APK; line numbers refer to the inspected decompilation and may differ under another tool. This document contains derived protocol facts only. The APK, decompiled vendor source, private capture and download credentials are not distributed.

The captured curtain reports raw model `25025`, firmware `4.6.0`, 400 LEDs, 20×20 geometry and DIY type 3. rc5 requires that exact profile for these additional controls. Raw model 25025 is absent from the APK's explicit curtain model lists (`app/ProductInfoProvider.java:1650–1674`), and `ModelProvider.java` contains a default pass-through map. Therefore geometry alone is not treated as proof of every protocol in this multi-product app. Additional advertised flags, current-session query replies and readback gates are used where available.

| Feature | Evidence | rc5 exposure |
| --- | --- | --- |
| Device microphone music | Captured info advertises music capability 3; APK maps that capability to device/phone microphone choices. | Device modes 1–4 only; profile/advertised flag required, then real status verification. Physical response unconfirmed. |
| Preset speed | App explicitly queries support and enables setter only after reply. | Same discovery gate plus current built-in scene mode and value readback. |
| Clock sync | Exact command and its echo are in original capture. | Explicit action; persistence/accuracy not proven. |
| Power countdown | Shared settings UI and decoder use seconds and target power. | Explicit bounded action and current status verification. Future power transition unconfirmed. |
| Device schedules | Shared settings UI reads two timer banks and writes one slot. | Both valid bank replies required before edit; slot replacement and readback verification. Actual scheduled execution unconfirmed. |
| Font support | Curtain text-list screen issues empty DD query. | Read-only inspection; no text transfer enabled. |
| True firmware pause | Command exists in preset-editing paths; no proof for this DIY3 controller. | Withheld. Software playlist pause remains. |
| Native scene loop | Requires info tag 02; absent from captured device. | Withheld. Software playlists remain. |
| Extra device storage | App save calls exist but no safe capacity/read/list/overwrite contract established. | Withheld. HA library remains. |
| Current rendered pixels | No verified pixel readback established. | No live screen claim. Local preview and upload history remain separate. |

The user physically confirmed rc3 and subsequently reported release validation of rc5 on 16 October 2026. New controls also have source and software validation. No separate per-feature checklist or long-term execution report was supplied; individual evidence gaps in the table refer to that missing detail, not a rejection of the release-validation report.

## Music and preset speed

`ble/Cmds.java:GetDeviceInfoCmd` around line 4896 consumes extension tag 08's next byte as `musicMode`. Captured extension bytes advertise value 3. `defpackage/x03.java:295–324` distinguishes capability 1 from 3 and creates a device/phone microphone switch for 3. `v03.java` and `z03.java:47–75` set the phone-sampling flag. `g13.java:35–39` adds 4 to the music mode only on that phone path. Thus native modes 1–4 use the controller microphone; integration writes never select modes 5–8 or stream audio.

`x03.java:151–201` presents numeric modes 1–4 and forces automatic colors on mode 1. `g13.java:16–38` supplies sensitivity, brightness, hue and saturation; zero sensitivity/brightness is clamped upward by the app. `Cmds.java:338–429` defines `MusicMode`; around lines 5086–5089, light command 03 writes:

`03, (mode << 4) | auto_color, sensitivity, brightness_BE16, hue_BE16, saturation_BE16`.

Sensitivity is 1–100; brightness is 1–100 percent scaled by 10; hue is 0–360 degrees; saturation is 0–100 percent scaled by 10. Mode 1 forces automatic colors. The full packet is 13 bytes, within baseline ATT MTU 23. Packet checksum is the preceding-byte sum modulo 256.

Readback uses status command 01, with 13 payload bytes: countdown BE24, power, work mode 03, eight-byte music body (`Cmds.java:2840–2870`, `MusicMode.handleBytes:354–374`). Strict decoding checks command, length, checksum and ranges. It may report a phone mode previously selected externally without allowing the integration to send one. A status report is evidence of the selected mode, not the visible pixels or audio responsiveness.

`ui/MainActivity.java:887–900` sends empty `GetSceneModeSpeedCmd` and marks support only after a notification. `Cmds.java:2876–2902` defines command 0C, empty query, one-byte response. `SetSceneModeSpeedCmd:847–869` writes the same command with one speed byte 0–100. Example query `aa0c00b6`; speed 100 `aa0c01641b`. A missing reply never authorizes a setter. Discovery expires with the BLE connection. Preset speed applies only when current status reports scene mode 2; DIY uses existing D0 controls.

## Clock, countdown and schedule details

Capture records 494 and 500 contain command/echo `aa05076acf985b0100b497`. `SetCurrentTime` (`Cmds.java:3094–3121`) writes UTC Unix seconds BE4, sign byte (0 negative, 1 nonnegative), absolute offset minutes BE2. `CommonCmd.java:93–99` confirms byte order; `ox4.java:686–692` obtains current raw timezone offset plus DST. `InitBleCmdTask.java:29–43` sends this in normal app synchronization. The integration exposes it only as an explicit action, with no automatic startup/upload time mutation.

`SetCountdownCmd` (`Cmds.java:1558–1609`) writes command 04, BE4 seconds and target power. `md4.java:30–62` converts hours/minutes to seconds; `ld4.java:18–22` cancels with zero. The UI provides up to 24 hours with zero minutes at the upper bound (`ui/a.java:208–219`, `qt3.java:onWheelSelected`), supporting a conservative 0–86400-second range. A command 04 response contains at least four countdown bytes; ordinary status 01 also reports countdown in its first three bytes. Neither response proves the eventual power change.

Timing is available in the shared settings screen (`ui/a.java:171`), not exclusively in a 900-LED DIY class. Optional configuration flags can hide timing/countdown (`ui/a.java:483–494`); special thermometer configurations do so (`la5.java:b/c`). This establishes a shared app path, while exact-model support is still checked by runtime reads.

`RequestTimer1To4Cmd` (`Cmds.java:2931–3000`) uses empty command 06 to read the first four slots; `RequestTimer5To8Cmd` (`431–484`) uses empty 07 for the remaining four. Each complete bank response has 16 payload bytes. `pd4.java:257–266` reads bank 1, then bank 2 after 600 ms. A four-byte write echo is never accepted as a bank. Individual writes always use command 06 (`zk.java:9–13`), including slot numbers 4–7.

Each `LightTimer` contains four bytes (`Cmds.java:5150–5254`):

| Byte | Meaning |
| --- | --- |
| 0 | Repeat in bit 0; ISO weekdays Monday–Sunday in bits 1–7. |
| 1 | Hour 0–23. |
| 2 | Minute 0–59. |
| 3 | Power bit 0; enabled 1; reserved 2; exists 3; slot number 4–6; executed 7. |

New edits set exists and clear executed (`LightTimer` constructor around 5302–5312). Empty weekdays mean one-time. Writes replace one slot only; no delete-all or reset is implemented. Strict decoding rejects malformed framing, checksum, hours/minutes, reserved bit and inconsistent weekday/repeat masks. Encoded slot numbers are checked against bank positions before editing. Both banks are inspected and reread for verification; unexplained responses do not trigger speculative replay.

`pd4.E:93–154` converts local time to **UTC+08 wall time**, including weekday rotation; `pd4.D:28–89` reverses it. `H:234–235` obtains the current offset. This is distinct from command 05's epoch/sign/offset fields. The implementation handles fractional-hour offsets, midnight and Sunday/Monday rollover. It does not send HA local hours directly as wire hours outside UTC+08.

There is no IANA timezone or future DST transition table in these packets. Native schedules must be reviewed/reapplied after offset changes. The integration does not silently rewrite schedules after restart. HA automations are the practical choice when future timezone transitions must be handled automatically.

## Text, storage, pause and loop boundaries

`ui/curtain_light/Diy_Text_list.java:124–138` sends default `Set_Text_UniCode_Data` when opening text controls. `Cmds.java:1613–1692` defines command DD with empty query `aadd0087`; a one-byte response is font capability. `APP_SYS_Parameter.java:143–148` interprets values at least 1 as custom fonts and at least 2 as borders. A timeout is not evidence of legacy ASCII support. rc5 inspects this information without changing text or entering a mode.

Text writes have multiple paths: D3 parameters (`Cmds.java:3480–3545`, `mj1.java:89–111`); D4 legacy header `(21, ASCII_count, HanZi_count)` and per-character triplets (`3423–3477`); DB batched triplets (`3734–3779`); DD custom font rasters/offsets/colors (`oz1.java:37–127`). Text movement IDs have their own mapping, not D0 image direction IDs. A custom-font decompilation region also needs bytecode/capture verification before reconstruction. The exact profile's path remains unresolved, so none of these writers is enabled merely because the app contains it.

D9 `(slot,type)` is used by the app's text save path (`Cmds.java:3068–3093`, `uj1.java:19–29`), with six local default entries. This does not establish device capacity, safe overwrite semantics, power-cycle persistence or a complete device storage list/read/delete contract. No storage writer, factory reset or deletion fallback is exposed.

`SetPauseDeviceCmd` (`Cmds.java:784–815`) uses command 11 and a boolean, but its result handler toggles internal state rather than independently reading the controller. Callers include editable preset editors and `hk.java:344,353`. They do not prove that it pauses this DIY3 D0/DC animation. Existing software playlist pause prevents future uploads while leaving the current device animation running.

Native scene loop requires info extension tag 02 (`GetDeviceInfoCmd:4878–4882`, `BasicsCollectLoopControl.java:27–31`), absent from this capture. Command 19 also uses a positional bitmap tied to the app's filtered scene list (`Cmds.java:4279–4367`, `ry0.java:16–47`). Guessing a generic scene-ID bitmap would be unsafe even on another supported model. Software playlists remain the verified transport strategy.

## Validation limits

Focused tests cover captured clock bytes, music framing and readback, strict capability replies, malformed checksums/lengths, timer banks, cancellation, bounds, fractional offsets and weekday rollover. The overall framework/browser validation is recorded in [VALIDATION.md](VALIDATION.md). Tests simulate the radio; they do not establish hardware behavior. See [STUDIO_GUIDE.md](STUDIO_GUIDE.md) for one controlled music-response check after installation.
