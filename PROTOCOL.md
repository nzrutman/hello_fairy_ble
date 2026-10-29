# Curtain protocol evidence

> Generated with [aurora@aurora-smart-home (ha-integration-dev skill)](https://github.com/tonylofgren/aurora-smart-home)

## Sources and limits

Static and two-picture framing was checked against a successful Android Bluetooth HCI capture. Playback controls and information/status field meanings were inspected in the official Hello Fairy beta APK, package `com.lenzetech.hellofairy`, version 3.6.118 (306118), linked from [Hello Fairy](https://hellofairy.com). Other packages and versions may differ.

Capture SHA-256: `57f00fbc2d50e3a4091454e9a10c1b7b79c5bdff2eaf01ee514c41a4ac8192e3`.

APK SHA-256: `990d09e21a649915564867ec480e2d69b030a519995c18a34a6714ac1b686985`.

Only derived facts and small vectors are included. Raw captures and vendor source are excluded.

## Static upload

Packets use `AA command payload_length payload checksum`; checksum is the sum of preceding bytes modulo 256. Each pixel entry is a big-endian two-byte index and color byte. Device indexing is column-major (`x * 20 + y`); frame input is row-major.

Successful captured sequence: `D0(03)`, `D0(00)`, six DA packets, `D0(04)`, `D0(01)`. Five DA packets contain 79 entries and the sixth contains five: all 400 pixels. Maximum GATT value is 242 bytes, requiring ATT MTU ≥245. Finalization follows an approximately 1.2-second delay. The implementation retains conservative pacing and this framing.

Earlier controlled hardware tests showed that 80 five-entry DA packets retained only the final packet. DA data therefore cannot safely be treated as arbitrarily fragmentable. There is no tiny-packet fallback.

Color bytes 0–180 encode hue; 254 is off and 255 white. Other raw values are rejected. RGB images are quantized to supported colors.

## Two-picture playback

The capture contains `D0(05,64,64,07)`, `D7(1,0)`, `D0(05,64,64,00)`, six DA packets for picture one, `D7(1,2)`, `D7(2,0)`, six DA packets for picture two, `D7(2,2)`, `D0(05,64,64,02)`, `DC(0)` (hexadecimal). The implementation preserves slot boundaries with conservative DA pacing. Playback was physically confirmed on the preceding experimental package.

## Native controls

APK classes `Cmds`, `SetSpeedView`, `SetDirectionView`, `DiyGlobalPictureConfig` and `DiyPictureShowActivity` establish D0 order: direction, brightness, speed, action. Sliders send 0–100. Picture action is 1; animation action is 2. Animation also uses DC: 0 blink, 1 breathe.

| Picture movement | Direction |
| --- | --- |
| Still | 0 |
| Up / down / left / right | 1 / 2 / 3 / 4 |
| Blink / breathe | 5 / 6 |
| Loop up / down / left / right | 7 / 8 / 9 / 10 |

Vectors: picture left, speed 20, brightness 100 → `aad00403641401fa`; animation breathe, speed 30, brightness 75 → `aad004014b1e02ea` followed by `aadc010188`. Each movement still needs physical confirmation on this candidate.

## Device information, status and transport

`AA0000AA` requests information. Captured firmware 4.6.0, raw model 25025 reports LED count at payload offsets 20–21, columns at 22, rows at 24 and DIY type at 26. DIY requires 400 / 20 / 20 / 3 on the active connection. Status uses an empty-payload command 01.

Status fields were checked against `GetDeviceStatusCmd` and `SceneMode`. Known curtain scene brightness is already percent; legacy scaling is retained for unverified models. Firmware and acknowledgement packets are not interpreted as status. No pixel readback is claimed.

Cached ESPHome connections can initially expose MTU 23 without proving exchanged MTU. Preflight clears the cache and reconnects uncached, checks source continuity, then inspects active MTU, characteristic properties and write capacity before DIY writes. It reuses the exact healthy verified connection and invalidates verification on disconnect/failure. Source inspection uses a private HA wrapper attribute: unavailable or changed capabilities fail clearly, and future HA versions may need adaptation.

The tested proxy's fresh-link logs reported MTU 512, write capacity 509 and handle 0x0009. No deliberately oversized probe is sent. TCP-buffer-full warnings alone do not establish packet loss. Transport completion alone does not establish physical success.

## Software-rendered features in rc3

Text, palette remaps, artwork regions and symmetry tools change the logical frame in the browser. Installation corrections transform each 20×20 tile once at output. Favorites, named playlists, messages/icons and clock snapshots use the same full-image protocol and existing native playback settings. They introduce no new inferred device commands. Messages hold complete pages for at least 10 seconds; clocks wait at least 60 seconds after completed uploads. No fast frame-streaming, independent on-device animated segments or per-pixel dimming capability is inferred from these software features.

## Additional native controls in rc5

These controls require fresh information for the exact researched profile: raw model `25025`, firmware `4.6.0`, 400 LEDs, 20 columns, 20 rows, DIY type 3. Other profiles fail clearly. The extra commands fit within a 20-byte GATT value; this does not relax the separate 242-byte full-image preflight. No new capability probes, time synchronization or timer changes run automatically at startup or during ordinary controls.

**Inspect capabilities** explicitly queries preset speed (`0C`), font support (`DD`) and the two timer banks (`06`, `07`). A timeout leaves the relevant feature unconfirmed. Only genuine checksummed replies from the current session establish support; a write echo is not accepted as a complete timer bank. Session capabilities expire when the connection changes. Inspection changes no mode, artwork, clock or schedule.

| Feature | Framing and safeguards |
| --- | --- |
| Built-in music response | Information extension tag `08` must advertise value `03`. Command `03` payload is `03, (music_mode << 4) | auto_color, sensitivity, brightness_BE16, hue_BE16, saturation_BE16`. Modes 1–4 use the device microphone; phone audio modes 5–8 are excluded. Brightness/saturation use scale 1000. Mode 1 forces automatic colors. Status mode 3 must subsequently be reported. |
| Preset speed | Empty `0C` query; one-byte 0–100 response establishes support. Setter uses one-byte speed and requires a current built-in scene status (mode 2). Readback verifies the result. DIY movement retains its separate D0 speed. |
| Explicit clock sync | `05`: UTC Unix seconds BE4, offset sign byte (`0` negative, `1` nonnegative), absolute offset BE2 minutes. The original capture contains this write and its echo. No automatic synchronization is introduced. |
| Power countdown | `04`: seconds BE4, target power byte. Range 0–86400; zero cancels. Current status `01` includes countdown seconds BE3. Verification reports device status, not proof of the future power transition. |
| Native schedules | `06` reads the first four slots; `07` reads the remaining four. Each complete response contains 16 bytes. Both banks must be valid before a single-slot edit. The app writes one four-byte slot with command `06`, including slots 4–7, then the integration rereads for verification. |

Timer bytes are: weekday mask/repeat, hour, minute, flags. Weekday bits 1–7 mean Monday–Sunday; bit 0 means repeat. Flags contain target power (bit 0), enabled (1), exists (3), slot number (4–6), executed (7); bit 2 is reserved. A new edit clears executed and sets exists. Empty weekdays means a one-time schedule. An individual edit does not send or rewrite the other slots.

The APK converts schedule wall time to **UTC+08**, including weekday rollover. The integration converts from HA's current UTC offset and reverses the conversion for display. Device protocols provide neither an IANA timezone nor future daylight-saving rules. Review/reapply schedules after an offset change; synchronization alone does not promise to adjust every stored schedule. HA automations are preferable for rules that must follow future timezone transitions.

Native pause (`11`), scene loop (`19`), text upload and extra storage management remain unavailable. The captured profile does not advertise the scene-loop flag, and the other app paths do not establish safe operation for this exact curtain. Font inspection provides capability information only. Full rendered-pixel readback remains unproven. See [NATIVE_EVIDENCE.md](NATIVE_EVIDENCE.md) for the source audit and confidence limits.

The user physically confirmed rc3 as working. The rc5 additions have software validation only until tested on the lights; no APK finding, echoed command or transport completion is presented as physical success.
