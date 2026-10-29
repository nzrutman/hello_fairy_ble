# Curtain Studio guide

> Generated with [aurora@aurora-smart-home (ha-integration-dev skill)](https://github.com/tonylofgren/aurora-smart-home)

Version **2.0.0** combines the integration and all Studio tools. Open **Curtain Studio** in HA's sidebar as an administrator. Choose your curtains under **Your Hello Fairy curtains**, ordered left to right.

## Text, palettes and artwork areas

Open **Text, palettes, regions & symmetry** in the editor. Choose the entire canvas, one curtain, or a rectangle with X/Y/width/height. The outlined area controls painting, text, fill, pattern and transformation tools. Selecting an area does not send anything.

Type text, choose its position and scale, and apply it to the preview. The tiny pixel font is designed for these low-resolution curtains. Wrapping, unsupported-character substitutions and clipping are reported. A short word is usually clearer than a sentence on one 20×20 curtain. The editor's current-time insertion is a snapshot; it does not start an updating clock.

Choose a named palette or enter custom colors to recolor the selected artwork. Supported curtain colors are vivid hues, white and off. These are hue remaps, not WLED's per-pixel brightness or saturation gradients. White/off preservation is controlled by the palette options.

Fill or erase the selected area, or apply a reusable pattern inside it. This lets you give each curtain different artwork or build a picture from rectangular sections. Region boundaries are editor selections; they are not independent on-device animation segments.

Use flip, symmetry, rotation and tile tools to repeat or rearrange the selected artwork. Symmetry copies one half onto the other. Tile repeats the selected area's upper-left tile. A 90° rotation on a non-square selection is centered and cropped/padded to retain the canvas dimensions. Undo/redo remains available. In Animation mode, edits affect the active picture only.

## Installation corrections

Under the curtain layout, choose each curtain's clockwise rotation and left/right or up/down flips. These settings are saved in Home Assistant by Bluetooth address. Saving them sends nothing to the lights.

Corrections apply once when Studio, a saved design, playlist, message or clock is sent. The canvas and saved artwork remain in logical coordinates, so a design can be reused on different installations. Corrections rotate first, then apply flips. They do not remap the device's native movement directions. Raw low-level `set_frame`/`set_pixel` actions keep their original coordinates for compatibility.

## Estimated movement preview

Press **Play preview** beside the canvas to see a separate local simulation. It shows still, directional, looping, blink/breathe and two-picture movement, with each 20×20 curtain simulated independently. It never uploads anything or changes your saved artwork. The preview is in logical artwork coordinates; it does not simulate installation corrections.

Timing, brightness and wrapping are illustrative, not measurements of the controller's behavior. The numeric speed slider still sends the device's original native value when you deliberately upload/apply settings. The simulation is not a live view or a promise that seamless movement will cross curtain boundaries.

Use **Stop preview** to close it. Editing, loading another design, changing layout/playback settings, hiding the page or leaving Studio stops it. Nothing starts automatically. If reduced motion is requested by your browser/OS, Play shows a static estimate instead of animation.

## Named layouts and complete backups

Below the library, expand **Curtain layouts & library backup**. Give the selected curtains a layout name and press **Save selected curtains**. Up to 20 layouts remember their exact left-to-right address order. Applying a layout changes only the editor selection; it asks before clearing a nonblank draft and sends nothing to the lights. A layout with unloaded/missing targets fails clearly instead of silently selecting a partial display.

**Download library backup** saves all saved designs, named playlists, favorites, installation corrections and layouts into one versioned JSON file. Unsaved editor pictures and unsaved playlist edits are not included. The backup contains private device addresses and artwork; keep it private. Individual design-file downloads remain available for sharing portable artwork without your installation settings.

To restore, choose **Merge with library** or **Replace entire library**, then choose the backup file. Files are limited to 4 MB and the complete contents are validated before the confirmation dialog. Invalid files or failed saves leave the library unchanged. Import does not contact the curtains, and the current editor picture is preserved.

Merge adds imported copies and remaps colliding identifiers with their playlist/favorite references. It preserves the currently selected playlist and existing orientation settings for matching curtains. Replace restores the backup's saved collections and selection after explicit confirmation. Existing size limits still apply to the combined result. Imported favorites/layouts may refer to offline or unconfigured hardware; using them requires those devices to be loaded. Playback must be stopped before import, and it never starts as a result of importing.

## Library and favorite buttons

Below the editor, name the current design and press **Save current design**. Use **Open** to restore a design to the editor without sending it. Existing-name replacement requires confirmation. A design's width must match the selected curtain count when it is sent.

Mark a saved design as a favorite on the currently selected curtains. The favorite remembers those exact targets and their order, even if you later change the Studio selection. Studio provides recall buttons. Home Assistant also creates a **Favorite …** button entity, associated with the first saved target curtain. Add it to a dashboard or call it from an automation.

Removing a favorite removes its generated button. Updating a favorite's first target creates a button associated with the new curtain; update any dashboard/automation references if needed. Existing light and preset entity identifiers are unchanged. A favorite fails clearly if one of its saved targets is no longer configured or loaded.

## Multiple playlists

Use **New playlist**, give it a name, and add library designs. Up to 20 named playlists are supported, with 50 steps each and 50 shared saved designs. Save changes explicitly. Every step and final design must match the target curtain count before playback starts.

Set each step's hold time to 10–86400 seconds. Timing begins after every curtain finishes that design's upload; upload time is additional. Select **Repeat forever** or choose 1–100 cycles. **Shuffle each cycle** changes step order while including each step once per cycle. An optional final design is uploaded only after natural completion, never after Stop or an error. Repeat forever has no natural completion.

**Next** and **Previous** navigate the playlist without interrupting an in-flight frame. Previous at the beginning stays at the beginning; Next after the final step advances toward normal completion. When shuffle is enabled, navigation follows the shuffled order. Automation navigation can be queued during an upload, with a bounded queue; Studio enables navigation during a playlist's hold period.

Playback runs in Home Assistant after the browser closes. Storage survives restart, but playback never resumes automatically at boot. Only one playlist, favorite recall, message sequence or clock runs at a time. A new recall/message/clock explicitly replaces the current job after its current curtain operation finishes. Invalid requests leave existing playback alone.

**Pause playlist** freezes the remaining hold time and prevents future design uploads while leaving the curtain's current picture/native movement running. A pause requested during upload waits until that complete design and its settings finish across the selected curtains. **Resume playlist** continues from that point without uploading the current picture again. Pause applies only to playlists, not message/clock jobs. Stop still works when paused; pending navigation stays queued until resume. Restart always leaves playback stopped rather than restoring a paused job.

The job status shows the design, playlist step/cycle, completed curtains and remaining hold time. Completed curtains means transfer/control calls completed, not physical confirmation. If a later curtain fails, the completed count remains visible. Hold time is a server-side estimate; no guaranteed upload ETA is shown.

## Clock and notification displays

Use **Clock & notifications** below the playlist controls. Pick foreground and background colors, then start a 24-hour or 12-hour clock. It uses Home Assistant's configured local time; 12-hour display has no AM/PM suffix. Updates are minute precision, at least 60 seconds apart after completed uploads. Uploads take time, so this is not a seconds-accurate live clock. Stop playback ends future updates and leaves the last picture.

Notifications accept up to 160 characters from A–Z, digits, spaces, colon, dash, period, `!` and `?`; letters are converted to uppercase. Choose an optional bell, heart or door icon, or leave text empty to show an icon alone. Text is divided into complete picture pages when needed. Duration applies to **each page after upload**, with a minimum of 10 seconds. On a single curtain each text page holds five characters, so longer messages take several uploads.

Optionally choose a saved design to display after the message finishes naturally. This is an explicit chosen design, not a readback/restore of whatever was physically showing beforehand. Stop or a failure suppresses the restoration. Notifications do not automatically resume an interrupted playlist or clock.

## Home Assistant automations

Existing power, brightness, colors and presets work as before. New actions are available in **Developer Tools → Actions**:

| Action | Purpose |
| --- | --- |
| `hello_fairy_ble.start_playlist` | Start the selected playlist, or an explicit optional `playlist_id`, on ordered `addresses`. |
| `hello_fairy_ble.stop_playlist` | Stop playlist, recall, message or clock jobs after the current curtain operation. |
| `hello_fairy_ble.playlist_next` / `playlist_previous` | Queue navigation for an active playlist. |
| `hello_fairy_ble.playlist_pause` / `playlist_resume` | Pause future playlist uploads or resume the remaining hold without a resend. |
| `hello_fairy_ble.show_design` | Recall `design_id` on optional ordered addresses, or its saved favorite targets. |
| `hello_fairy_ble.show_message` | Send text/icon pages with duration and an optional `restore_design_id`. |
| `hello_fairy_ble.start_clock` | Start occasional clock uploads on ordered addresses. |

Expand **Use in Home Assistant automations** in Studio for playlist/design IDs. Favorite button entities can be selected directly in an automation without copying IDs. An explicit playlist ID starts that playlist without changing the shared Studio selection. `addresses` is a list, including when it contains only one curtain. Standard HA automation triggers can schedule these actions; no separate scheduler is installed.

## Native curtain controls

Expand **Native curtain controls · experimental**, choose one curtain, and press **Inspect capabilities**. This reads the device's advertised music support, preset speed, font capability and schedule banks. It does not upload a design, change modes, set the clock or write a schedule. These additional controls require the researched 400-LED model and firmware profile; unsupported or unanswered capabilities remain unavailable. Inspect again after a new connection if a control becomes unavailable.

**Built-in music response** uses the microphone in the curtain controller. Choose Energy, Rhythm, Roll or Spectrum, sensitivity and brightness, then press **Start music response**. Home Assistant does not stream audio. Energy uses automatic colors. Other modes allow automatic colors or a hue/saturation setting. This deliberately takes over from a Studio job; select a normal HA preset or upload a Studio design to return to those modes.

**Preset speed** adjusts an active built-in preset after speed support has answered inspection. Select the preset through the normal HA controls first, then set its speed here. The image editor's DIY speed still controls uploaded designs separately.

**Sync curtain clock** explicitly sends the current HA time and current UTC offset. It does not draw a clock on the curtain; **Clock & notifications** remains the tool for that. **One-time power countdown** takes seconds and the target power state. Check **Turn on when countdown ends** for on; leave it unchecked for off. Zero cancels a pending countdown. Countdown status is device-reported, while the future power transition still needs physical confirmation.

**Device schedule · one slot** becomes available only after both schedule banks return valid information. Choose slot 0–7, local hour/minute, target power and whether to enable it. Select weekdays for a repeating schedule; no selected days means one-time. **Replace selected schedule slot** changes only that slot and rereads the schedule to check it. Disabled means that slot will not run; it does not delete every stored schedule. Review the existing device schedule before replacing a slot.

The device stores schedules with a fixed time basis. Studio converts your entered local time using HA's current offset, including day rollover. Review/reapply schedules and synchronize again after daylight-saving or timezone changes. HA automations handle ongoing timezone-aware schedules more reliably. Native actions stop Studio background playback before taking over, and none runs automatically on restart.

Native text upload, extra device storage management, true device-animation pause, built-in scene loops and full pixel readback remain unavailable pending exact-model evidence. Studio's existing text rendering, HA library, software playlists and playlist pause remain available.

### One controlled rc5 check

Close the phone app, choose one curtain in **Native curtain controls**, and press **Inspect capabilities**. If music support is available, leave **Energy**, sensitivity 50 and brightness 100 selected, then press **Start music response** once. Play sound near the controller and check whether the curtain responds. Report the visible result and any Studio error. Return to a known HA preset afterward. If inspection leaves music unavailable, report that result without repeatedly sending commands. This is one feature check; rc5 is not physically confirmed merely because the status reply succeeds. The preceding rc3 package was already physically confirmed by the user.

## Stop, errors and limits

Stop lets the current curtain's full upload and playback settings finish, then prevents later sends. It does not stop native movement already running on the curtain. Stopping during a multiple-curtain update can leave curtains showing different steps. Check the lights before sending again.

Manual Studio sends and normal HA light/preset controls stop background playback before taking over. Integration unload and HA shutdown also stop it. Phone-app/physical changes are not reliably detectable and cannot automatically stop a job.

Connection setup retries are bounded. An image/control failure stops playback without replay, final-design upload, notification restoration, or sends to later curtains. Studio status describes transmission, not physical confirmation. Device-reported status and uploaded-picture history remain separate; there is no verified pixel readback.

Full-frame and model/MTU checks remain mandatory. Built-in music response is experimental and uses device hardware; arbitrary audio streaming/visualization, smooth image streaming, independent moving regions, seamless cross-curtain scrolling and phase synchronization are not provided by these tools.

For troubleshooting, Home Assistant's integration menu can download diagnostics. This integration returns allowlisted capability/state metadata without artwork, device names/addresses or any new BLE query. Complete library backups are different: they deliberately contain your private saved installation data.

## Native automation action

`hello_fairy_ble.native_control` accepts one configured `address`, an `action` and a `payload` object. Actions are `inspect`, `music`, `scene_speed`, `clock_sync`, `countdown` and `timer`. Invalid settings fail before a connection or playback stop. Inspection makes read-only queries; other actions stop any Studio background job before proceeding. Device-specific gates still apply when called by automations.

| Action | Payload |
| --- | --- |
| inspect | `{}` |
| music | `mode` 1–4; optional `auto_color` boolean, `sensitivity` 1–100 (50), `brightness` 1–100 (100), `hue` 0–360 (0), `saturation` 0–100 (100). Mode 1 forces auto colors. |
| scene_speed | `speed` integer 0–100; first inspect on this connection and select a known built-in preset through HA. |
| clock_sync | `{}`; current HA epoch and timezone offset. |
| countdown | `seconds` integer 0–86400 and `power` boolean. Zero cancels. Readback verifies remaining time, not the eventual target-power transition. |
| timer | `slot` 0–7, `hour` 0–23, `minute` 0–59, `power` and `enabled` booleans, `weekdays` list of unique ISO days (Monday=1…Sunday=7). An empty list is one-time. |

All numeric settings must be integers. One action transmits once; setup retries do not replay uncertain device writes. A reply confirms only its decoded fields, never physical LED behavior. For ongoing local-time schedules across DST, prefer normal HA automations using the existing light entities.
