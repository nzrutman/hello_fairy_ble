/** Hello Fairy Curtain Studio — bundled integration editor v2.0.0.
 * Generated with aurora@aurora-smart-home (ha-integration-dev skill)
 * https://github.com/tonylofgren/aurora-smart-home
 */
import { PATTERNS, makePattern } from "./patterns.js?v=2.0.0";
import { transformCurtain } from "./orientation.js?v=2.0.0";
import {
  PALETTES,
  checkedRegion,
  mapRegion,
  parsePalette,
  recolor,
  renderText,
  transformRegion,
} from "./design-tools.js?v=2.0.0";
import { estimateMovement } from "./movement-preview.js?v=2.0.0";
const VERSION = "2.0.0";
const OFF = 254;
const DEFAULT_CURTAINS = [];
const esc = (s) =>
  String(s).replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );

export function normalizeConfig(config) {
  const curtains = config.curtains ?? DEFAULT_CURTAINS;
  if (!Array.isArray(curtains) || !curtains.length || curtains.length > 8)
    throw new Error("Configure between one and eight curtains.");
  const checked = curtains.map((c, i) => {
    const address = String(c.address || "")
      .trim()
      .toUpperCase();
    if (!/^([0-9A-F]{2}:){5}[0-9A-F]{2}$/.test(address))
      throw new Error(`Curtain ${i + 1} needs a valid Bluetooth address.`);
    return { name: String(c.name || `Curtain ${i + 1}`).slice(0, 80), address };
  });
  if (new Set(checked.map((c) => c.address)).size !== checked.length)
    throw new Error("Each curtain must have a different address.");
  return {
    type: "hello-fairy-canvas-editor",
    title: String(config.title || "Curtain Studio"),
    curtains: checked,
  };
}

export function rgbToPixel(r, g, b, a = 255) {
  // Composite transparency onto black, then mirror pixel_protocol.py's thresholds.
  r = ((r / 255) * a) / 255;
  g = ((g / 255) * a) / 255;
  b = ((b / 255) * a) / 255;
  const hi = Math.max(r, g, b),
    lo = Math.min(r, g, b),
    d = hi - lo;
  if (hi <= 0.05) return OFF;
  if (d / hi <= 0.1) return 255;
  let hue =
    hi === r ? ((g - b) / d) % 6 : hi === g ? (b - r) / d + 2 : (r - g) / d + 4;
  hue = (hue * 60 + 360) % 360;
  // Python round uses ties-to-even.
  const h = hue / 2,
    base = Math.floor(h),
    frac = h - base;
  return Math.min(180, frac === 0.5 ? base + (base % 2) : Math.round(h));
}

export function pixelCss(p) {
  return p === OFF
    ? "#17243b"
    : p === 255
      ? "#f9fafb"
      : `hsl(${p * 2} 100% 56%)`;
}

export function validateFrame(pixels, width) {
  if (
    !Array.isArray(pixels) ||
    pixels.length !== width * 20 ||
    pixels.some(
      (p) =>
        !Number.isInteger(p) ||
        !((p >= 0 && p <= 180) || p === 254 || p === 255),
    )
  ) {
    throw new Error(
      `Pattern must contain ${width * 20} supported pixel colors for this layout.`,
    );
  }
  return pixels.slice();
}

export function splitFrame(pixels, count) {
  validateFrame(pixels, count * 20);
  return Array.from({ length: count }, (_, c) =>
    Array.from(
      { length: 400 },
      (_, i) => pixels[Math.floor(i / 20) * count * 20 + c * 20 + (i % 20)],
    ),
  );
}

const CSS = `
  :host{container-type:inline-size;display:block;color:var(--primary-text-color,#172536);font:14px/1.5 var(--paper-font-body1_-_font-family,system-ui,sans-serif);--accent:#087f73;--muted:var(--secondary-text-color,#526373);--surface:var(--card-background-color,#fff);--edge:var(--divider-color,#dce5e7)}
  *{box-sizing:border-box}ha-card{display:block;overflow:hidden;background:var(--surface);border-radius:20px;border:1px solid var(--edge)}
  header{padding:24px 24px 18px;display:flex;align-items:start;justify-content:space-between;gap:12px}.eyebrow{color:var(--muted);font-size:11px;letter-spacing:1.8px;font-weight:800;text-transform:uppercase}h2{font-size:26px;line-height:1.2;letter-spacing:-.7px;margin:5px 0 7px}p{margin:0;color:var(--muted)}.badge{background:color-mix(in srgb,var(--accent) 10%,var(--surface));color:var(--primary-text-color,#172536);border-radius:30px;padding:7px 10px;font-size:12px;white-space:nowrap}
  .body{align-items:start;display:grid;grid-template-columns:minmax(0,1fr) minmax(220px,.65fr);gap:22px;padding:0 24px 22px}.preview{position:sticky;top:16px;background:#0c1628;border-radius:14px;padding:16px;color:#d9e5f4;min-width:0}.preview-head,.row{display:flex;align-items:center;justify-content:space-between;gap:10px}.preview-head{font-size:12px;margin-bottom:12px}.dim{color:#a9bacf}.canvas-wrap{overflow:auto;max-height:430px;padding:3px}canvas{display:block;width:100%;min-width:240px;image-rendering:pixelated;touch-action:none;border-radius:5px;outline-offset:3px}.canvas-note{margin-top:12px;font-size:11px;color:#a9bacf}.curtain-labels{display:flex;gap:4px;margin-top:10px}.curtain-labels span{flex:1;text-align:center;font-size:11px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.panel{min-width:0}.section{margin-bottom:18px}.label{display:block;font-weight:700;font-size:13px;margin-bottom:8px}.drop{display:block;width:100%;border:1px dashed var(--edge);border-radius:12px;padding:20px 12px;background:color-mix(in srgb,var(--accent) 4%,var(--surface));text-align:center;cursor:pointer}.drop strong{display:block;font-size:14px}.drop small{display:block;color:var(--muted);margin-top:4px}.drop.over{outline:2px solid var(--accent)}
  button,select,input,textarea{font:inherit;color:inherit}button,select{border:1px solid var(--edge);border-radius:9px;background:var(--surface);min-height:44px;padding:8px 12px;cursor:pointer}button:hover{background:color-mix(in srgb,var(--accent) 7%,var(--surface))}button:focus-visible,input:focus-visible,select:focus-visible,textarea:focus-visible,canvas:focus-visible{outline:3px solid #3998df;outline-offset:2px}button:disabled{opacity:.45;cursor:default}.small{font-size:12px}.fit-row{display:flex;align-items:center;gap:8px;margin-top:10px}.fit-row select{flex:1;min-width:0}.file-name{font-size:12px;margin-top:7px;word-break:break-word;color:var(--muted)}
  .tools{display:flex;gap:6px;flex-wrap:wrap}.tools button{flex:1;padding:7px 9px}.palette{display:flex;gap:7px;flex-wrap:wrap}.swatch{color:#fff;width:44px;min-height:44px;padding:0;border:3px solid transparent;background:var(--swatch)!important;box-shadow:inset 0 0 0 1px #71809688}.swatch[aria-pressed=true]{border-color:var(--primary-text-color,#172536);outline:2px solid var(--surface);outline-offset:-4px}.color-row{display:flex;align-items:center;gap:8px;margin-top:8px}.color-row input{width:44px;height:44px;padding:3px;border:1px solid var(--edge);border-radius:8px;background:var(--surface)}.color-row span{font-size:12px;color:var(--muted)}
  details{border-top:1px solid var(--edge);padding-top:12px}summary{cursor:pointer;min-height:36px;font-size:12px;font-weight:700}.extras{display:flex;flex-wrap:wrap;gap:6px}.extras button{flex:1;min-width:85px;font-size:12px}.info{font-size:12px;color:var(--muted);margin-top:10px}.info strong{color:var(--primary-text-color,#172536)}
  footer{border-top:1px solid var(--edge);padding:16px 24px;display:flex;align-items:center;gap:14px;justify-content:space-between}.status{font-size:12px;color:var(--muted);max-width:65%;overflow-wrap:anywhere}.status.error{color:var(--error-color,#b42318)}.status.success{color:var(--primary-text-color,#172536)}.send{background:var(--accent);color:#fff;border-color:var(--accent);font-weight:700;white-space:nowrap;padding:10px 18px}.send:hover{background:#06695f}.hidden{display:none}.version{font-size:10px;color:var(--muted);text-align:right;padding:0 24px 8px}
  @container(max-width:650px){header{padding:18px}.body{grid-template-columns:1fr;padding:0 18px 18px;gap:18px}h2{font-size:23px}.badge{font-size:10px}.panel{display:grid;grid-template-columns:1fr 1fr;gap:14px}.section{margin:0}.panel details,.panel .workflow-head{grid-column:1/-1}footer{padding:14px 18px;align-items:stretch;flex-direction:column}.status{max-width:100%}.send{width:100%}.preview{padding:12px;position:static}}
  @container(max-width:380px){.panel{grid-template-columns:1fr}.badge{display:none}}
  .design-tools{grid-column:1/-1;border-top:1px solid var(--edge);padding-top:14px}.design-tools select{width:100%}.design-tools input[type=range]{display:block;width:100%;min-height:44px;margin:0 0 8px}.design-tools output{float:right;color:var(--muted)}.tools button[aria-pressed=true],.frame-tabs button[aria-pressed=true]{border:2px solid var(--accent);background:color-mix(in srgb,var(--accent) 10%,var(--surface))}.frame-tabs{display:flex;gap:8px;margin:12px 0}.frame-tabs button{flex:1;display:grid;justify-items:center;gap:6px}.mini{display:block;width:64px;height:48px;min-width:0!important;max-width:100%;object-fit:contain;border-radius:3px;image-rendering:pixelated;touch-action:auto}.pattern-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px;margin:10px 0}.pattern-grid button{display:grid;justify-items:center;gap:6px;padding:8px;font-size:12px}.pattern-grid .mini{width:48px;height:48px}@container(max-width:650px){.pattern-grid{grid-template-columns:repeat(4,minmax(0,1fr))}}
  .creative .coords{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:6px}.creative input:not([type=checkbox]),.creative textarea,.creative select{max-width:100%;width:100%;min-height:44px;padding:8px;border:1px solid var(--edge);border-radius:8px;background:var(--surface)}.creative textarea{resize:vertical}.creative .check{display:flex;align-items:center;gap:8px;min-height:44px}.creative label{font-size:12px}.creative .coords label{min-width:0}.creative h3{font-size:13px;margin:12px 0 6px}
  @media(prefers-reduced-motion:reduce){*{scroll-behavior:auto!important}}
  .preview .canvas-note p{color:#b8c6d8}.preview .tools button{background:#20324b;border-color:#72849d;color:#f1f5fb}.preview .tools button:disabled{background:#18283e;color:#a8b5c8;opacity:.65}
`;

export class HelloFairyCurtainStudio extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._undo = [];
    this._redo = [];
    this._brush = 0;
    this._busy = false;
    this._loading = false;
    this._designKind = "picture";
    this._activeFrame = 0;
    this._settings = {
      picture: { movement: "still", speed: 100, brightness: 100 },
      animation: { movement: "blink", speed: 100, brightness: 100 },
    };
    this._animationFrames = [null, null];
    this._cursor = { x: 0, y: 0 };
    this._loadGeneration = 0;
  }
  setConfig(raw) {
    this._stopMovementPreview();
    const config = normalizeConfig(raw);
    if (this._busy)
      throw new Error(
        "Wait for the current send to finish before changing the curtain layout.",
      );
    const layoutChanged =
      JSON.stringify(this._config?.curtains) !==
      JSON.stringify(config.curtains);
    this._config = config;
    this._width = config.curtains.length * 20;
    this._region = { x: 0, y: 0, width: this._width, height: 20 };
    if (layoutChanged || !this._pixels) {
      this._designKind = "picture";
      this._pictureDraft = null;
      this._activeFrame = 0;
      this._animationFrames = [null, null];
      this._pixels = Array(this._width * 20).fill(OFF);
      this._undo = [];
      this._redo = [];
      this._image = null;
      this._loadGeneration++;
      this._loading = false;
    }
    this._render();
  }
  set hass(value) {
    this._hass = value;
    this._updateButtons();
  }
  connectedCallback() {
    this._visibilityChanged ||= () => {
      if (document.hidden) this._stopMovementPreview();
    };
    document.addEventListener("visibilitychange", this._visibilityChanged);
    this._resize?.disconnect();
    this._resizeWidth = this.getBoundingClientRect().width;
    this._resize = new ResizeObserver(() => {
      const width = this.getBoundingClientRect().width;
      if (width !== this._resizeWidth) {
        this._resizeWidth = width;
        this._draw();
      }
    });
    this._resize.observe(this);
  }
  getCardSize() {
    return 12;
  }
  getGridOptions() {
    return { columns: 12, min_columns: 12 };
  }
  disconnectedCallback() {
    this._stopMovementPreview();
    document.removeEventListener("visibilitychange", this._visibilityChanged);
    this._resize?.disconnect();
    this._finishStroke();
  }
  _render() {
    this._stopMovementPreview();
    if (!this._config) return;
    const colors = [
      ["Red", 0],
      ["Orange", 15],
      ["Yellow", 30],
      ["Green", 60],
      ["Blue", 120],
      ["Purple", 145],
      ["Pink", 165],
      ["White", 255],
      ["Eraser", OFF],
    ];
    this.shadowRoot.innerHTML = `<style>${CSS}</style><ha-card>
      <header><div><div class="eyebrow">Hello Fairy</div><h2>${esc(this._config.title)}</h2><p>Create a design, choose its movement, then send it.</p></div><span class="badge">${this._config.curtains.length} curtain${this._config.curtains.length > 1 ? "s" : ""} · ${this._width} × 20</span></header>
      <div class="body"><section class="preview" aria-label="Pattern preview"><div class="preview-head"><strong>YOUR CANVAS</strong><span class="dim">Preview · not live readback</span></div>
      <div class="canvas-wrap"><canvas id="grid" tabindex="0" role="img" aria-label="Editable curtain pixel grid. Arrow keys move; Space paints; Delete erases."></canvas></div>
      <div class="curtain-labels">${this._config.curtains.map((c) => `<span>${esc(c.name)}</span>`).join("")}</div>
      <div class="canvas-note"><strong>ESTIMATED LOCAL PREVIEW</strong><p>Simulation only: no light commands or pixel readback. Speed and brightness are illustrative; device timing, wrapping and direction may differ. Each curtain moves separately.</p><div class="tools"><button id="preview-play">Play preview</button><button id="preview-stop" disabled>Stop preview</button></div><p id="preview-state" role="status">Stopped. Nothing starts automatically.</p><div id="motion-output" hidden style="display:none"><canvas id="motion-preview" aria-label="Estimated movement simulation"></canvas></div></div><div class="canvas-note" id="position">Click or drag to paint. Keyboard: arrows + Space; Delete to erase.</div></section>
      <section class="panel"><div class="section workflow-head">        <span class="label">Design type</span><div class="tools"><button id="mode-picture" aria-pressed="true">Picture</button><button id="mode-animation" aria-pressed="false">Animation</button></div>
        <div id="animation" hidden><p class="info">Edit each picture below. Your changes are saved automatically as you switch between them.</p><div class="frame-tabs"><button id="show-a"><canvas class="mini" id="thumb-a"></canvas>First picture</button><button id="show-b"><canvas class="mini" id="thumb-b"></canvas>Second picture</button></div><p class="info" id="animation-state"></p><button id="animation-test">Use pink/green example</button><span hidden><button id="frame-a">Save current as A</button><button id="frame-b">Save current as B</button><button id="send-animation">Upload animation</button></span></div>
</div>      <details id="patterns" open><summary>Ready-made patterns</summary><div class="pattern-grid">${PATTERNS.map(([id, name]) => `<button data-pattern="${id}"><canvas class="mini" data-pattern-preview="${id}"></canvas>${name}</button>`).join("")}</div><p class="info">Choose a pattern to edit it. Nothing is sent until you press Send design.</p></details><div class="section"><span class="label">Choose a picture</span><button class="drop" id="choose"><strong>＋ Choose image</strong><small>or drop it here · PNG, JPG, WebP</small></button><input class="hidden" id="image-file" type="file" accept="image/png,image/jpeg,image/webp"><div id="filename" class="file-name">Images stay in your browser.</div><div class="fit-row"><label for="fit" class="small">Image fit</label><select id="fit"><option value="contain">Fit whole image</option><option value="cover">Fill canvas / crop</option></select></div></div>
      <div class="section"><span class="label">Draw &amp; edit</span><div class="palette">${colors.map(([name, p]) => `<button class="swatch" data-color="${p}" aria-label="${name}" title="${name}" aria-pressed="${p === this._brush}" style="--swatch:${pixelCss(p)}">${p === OFF ? "⌫" : ""}</button>`).join("")}</div><div class="color-row"><input id="color" type="color" value="#ff0000" aria-label="Choose custom brush color"><span id="brush-label">Brush: red</span></div><div class="tools" style="margin-top:10px"><button id="undo">Undo</button><button id="redo">Redo</button></div></div>
      <details class="creative design-tools" id="creative-tools"><summary>Text, palettes, regions &amp; symmetry</summary>
      <p class="info">Edits affect only the current picture in this browser. Every edit is undoable; nothing is sent automatically.</p>
      <h3>Work area</h3><label for="region-target">Target area</label><select id="region-target"><option value="all">Whole canvas</option>${this._config.curtains.map((c, i) => `<option value="${i}">${esc(c.name)}</option>`).join("")}<option value="custom">Custom rectangle</option></select>
      <div class="coords">${[
        ["rx", "X", 0, this._width - 1],
        ["ry", "Y", 0, 19],
        ["rw", "Width", 1, this._width],
        ["rh", "Height", 1, 20],
      ]
        .map(
          ([id, label, min, max]) =>
            `<label>${label}<input id="${id}" aria-label="Region ${label}" type="number" min="${min}" max="${max}" value="${id === "rw" ? this._width : id === "rh" ? 20 : 0}"></label>`,
        )
        .join(
          "",
        )}</div><button id="region-apply">Use rectangle</button><p class="info" id="region-note">Whole canvas selected. Coordinates start at zero.</p>
      <div class="tools"><button id="region-fill">Fill area with brush</button><button id="region-clear">Erase area</button></div>
      <h3>Pixel text</h3><label for="text-content">Message (A–Z, numbers and basic punctuation)</label><textarea id="text-content" rows="2" maxlength="240" placeholder="HELLO"></textarea>
      <div class="coords"><label>X offset<input id="text-x" aria-label="Text X offset" type="number" value="0" min="-1000" max="1000"></label><label>Y offset<input id="text-y" aria-label="Text Y offset" type="number" value="0" min="-1000" max="1000"></label><label>Size<select id="text-scale"><option value="1">3 × 5</option><option value="2">6 × 10</option><option value="3">9 × 15</option></select></label></div>
      <label class="check"><input id="text-wrap" type="checkbox">Wrap to next line inside area</label><label class="check"><input id="text-clear" type="checkbox">Erase area before adding text</label><div class="tools"><button id="text-add">Add text in brush color</button><button id="text-clock">Insert current time</button></div><p class="info">Offsets are relative to the area. Text outside it is clipped. Lowercase becomes uppercase; unsupported characters become ?. Time is a snapshot, not an automatic clock.</p>
      <h3>Recolor artwork</h3><label for="palette-name">Palette</label><select id="palette-name">${Object.keys(
        PALETTES,
      )
        .map(
          (n) =>
            `<option value="${n}">${n[0].toUpperCase() + n.slice(1)}</option>`,
        )
        .join(
          "",
        )}<option value="custom">Custom hues</option></select><label for="palette-custom">Custom hue angles, separated by commas (0–360, white or off)</label><input id="palette-custom" value="0, 120, 240" maxlength="160"><label class="check"><input id="palette-white" type="checkbox">Also recolor white pixels</label><button id="palette-apply">Recolor selected area</button><p class="info">Each hue maps to its nearest palette hue. Off stays off; white stays white unless selected. Colors are vivid hues, white or off; there is no per-pixel dimming.</p>
      <h3>Symmetry &amp; repetition</h3><div class="tools"><button data-transform="flip-h">Flip ↔ area</button><button data-transform="flip-v">Flip ↕ area</button><button data-transform="mirror-h">Mirror left half</button><button data-transform="mirror-v">Mirror top half</button><button data-transform="rotate-90">Rotate 90°</button><button data-transform="rotate-180">Rotate 180°</button></div><p class="info">Rotation keeps the area size. A 90° turn centers and crops rectangles; uncovered pixels turn off.</p><div class="coords"><label>Tile width<input id="tile-width" type="number" min="1" max="${this._width}" value="5"></label><label>Tile height<input id="tile-height" type="number" min="1" max="20" value="5"></label></div><button id="tile-apply">Repeat top-left tile across area</button><p class="info">Draw a tile in the area's top-left corner, then repeat it. Pattern buttons above also fill only the selected area.</p></details>
      <section class="design-tools" aria-label="Design and playback">
        <label class="label" for="movement" style="margin-top:16px">Movement</label><select id="movement"></select>
        <label class="label" for="speed" style="margin-top:12px">Speed <output id="speed-value">100%</output></label><input id="speed" type="range" min="0" max="100" step="1" value="100">
        <label class="label" for="diy-brightness">DIY brightness <output id="brightness-value">100%</output></label><input id="diy-brightness" type="range" min="0" max="100" step="1" value="100">
        <button id="apply-playback">Apply movement &amp; speed</button><p class="info">Send a design first. Then this button changes its movement and speed without uploading the pictures again. Each curtain plays independently.</p>
      </section>

      <details><summary>Save, open &amp; more tools</summary><div class="extras"><button id="flip-h">Flip ↔</button><button id="flip-v">Flip ↕</button><button id="clear">Clear canvas</button><button id="save">Save design</button><button id="load">Open design</button></div><input class="hidden" id="pattern-file" type="file" accept="application/json,.json"><p class="info">The preview uses the curtain’s colors: vivid hues, white and off. Dark colors become bright hues. Image details simplify to ${this._width} × 20 pixels.</p><p class="info"><strong>Layout:</strong> ${this._config.curtains.map((c) => esc(c.name)).join(" → ")}. Arrange curtains left to right using Display layout above.</p><p class="info">Opening an image or editing the canvas does not change your lights.</p></details></section></div>
      <footer><div id="status" class="status" role="status" aria-live="polite">Ready. Choose an image or draw a pattern.</div><button id="send" class="send">Send to curtain${this._config.curtains.length > 1 ? "s" : ""}</button></footer><div class="version">Curtain Studio ${VERSION}</div></ha-card>`;
    const $ = (id) => this.shadowRoot.getElementById(id);
    this._$ = $;
    $("choose").onclick = () => $("image-file").click();
    $("image-file").onchange = (e) => {
      const file = e.target.files[0];
      e.target.value = "";
      if (file) this._loadImage(file);
    };
    $("choose").ondragover = (e) => {
      e.preventDefault();
      if (!this._busy) $("choose").classList.add("over");
    };
    $("choose").ondragleave = () => $("choose").classList.remove("over");
    $("choose").ondrop = (e) => {
      e.preventDefault();
      $("choose").classList.remove("over");
      const f = e.dataTransfer.files[0];
      if (f) this._loadImage(f);
    };
    $("fit").onchange = () => {
      if (this._image && !this._busy && !this._loading) this._resample();
    };
    for (const b of this.shadowRoot.querySelectorAll("[data-color]"))
      b.onclick = () => this._selectBrush(Number(b.dataset.color), b.title);
    $("color").oninput = (e) => {
      const h = e.target.value;
      this._selectBrush(
        rgbToPixel(
          parseInt(h.slice(1, 3), 16),
          parseInt(h.slice(3, 5), 16),
          parseInt(h.slice(5, 7), 16),
        ),
        "custom color",
      );
    };
    $("undo").onclick = () => this._history(false);
    $("redo").onclick = () => this._history(true);
    $("clear").onclick = () => this._edit(() => this._pixels.fill(OFF));
    $("flip-h").onclick = () =>
      this._edit(() => {
        const old = this._pixels.slice();
        for (let y = 0; y < 20; y++)
          for (let x = 0; x < this._width; x++)
            this._pixels[y * this._width + x] =
              old[y * this._width + this._width - 1 - x];
      });
    $("flip-v").onclick = () =>
      this._edit(() => {
        const old = this._pixels.slice();
        for (let y = 0; y < 20; y++)
          for (let x = 0; x < this._width; x++)
            this._pixels[y * this._width + x] = old[(19 - y) * this._width + x];
      });
    $("save").onclick = () => this._savePattern();
    $("load").onclick = () => $("pattern-file").click();
    $("pattern-file").onchange = (e) => {
      const file = e.target.files[0];
      e.target.value = "";
      if (file) this._loadPattern(file);
    };
    $("send").onclick = () =>
      this._designKind === "animation" ? this._sendAnimation() : this._send();
    $("frame-a").onclick = () => this._storeAnimationFrame(0);
    $("frame-b").onclick = () => this._storeAnimationFrame(1);
    $("show-a").onclick = () => this._activateFrame(0);
    $("show-b").onclick = () => this._activateFrame(1);
    $("animation-test").onclick = () => {
      if (this._busy || this._loading) return;
      this._animationFrames = [
        Array(this._width * 20).fill(164),
        Array(this._width * 20).fill(60),
      ];
      this._changeKind("animation");
      this._activeFrame = 0;
      this._pixels = this._animationFrames[0].slice();
      this._draw();
      this._updateButtons();
      this._message(
        "Pink/green animation ready. Press Send design to put it on the curtains.",
      );
    };
    $("send-animation").onclick = () => this._sendAnimation();
    $("mode-picture").onclick = () => this._changeKind("picture");
    $("mode-animation").onclick = () => this._changeKind("animation");
    $("preview-play").onclick = () => this._startMovementPreview();
    $("preview-stop").onclick = () => this._stopMovementPreview();
    $("movement").onchange = (e) => {
      this._stopMovementPreview();
      this._settings[this._designKind].movement = e.target.value;
    };
    $("speed").oninput = (e) => {
      this._stopMovementPreview();
      this._settings[this._designKind].speed = Number(e.target.value);
      $("speed-value").textContent = e.target.value + "%";
    };
    $("diy-brightness").oninput = (e) => {
      this._stopMovementPreview();
      this._settings[this._designKind].brightness = Number(e.target.value);
      $("brightness-value").textContent = e.target.value + "%";
    };
    $("apply-playback").onclick = () => this._applyPlayback();
    this._bindCreativeTools();
    for (const b of this.shadowRoot.querySelectorAll("[data-pattern]"))
      b.onclick = () =>
        this._toolEdit(() => {
          const r = this._region;
          const patternWidth = Math.ceil(r.width / 20) * 20;
          const pattern = makePattern(
            b.dataset.pattern,
            patternWidth,
            this._brush === OFF ? 0 : this._brush,
          );
          this._pixels = mapRegion(
            this._pixels,
            this._width,
            r,
            (x, y) =>
              pattern[
                Math.min(19, Math.floor((y * 20) / r.height)) * patternWidth +
                  Math.min(
                    patternWidth - 1,
                    Math.floor((x * patternWidth) / r.width),
                  )
              ],
          );
        });
    for (const c of this.shadowRoot.querySelectorAll("[data-pattern-preview]"))
      this._mini(c, makePattern(c.dataset.patternPreview, 20, 0), 20);
    const grid = $("grid");
    grid.width = this._width * 20;
    grid.height = 400;
    grid.style.minWidth = this._width <= 40 ? "0px" : `${this._width * 8}px`;
    grid.style.maxWidth = `${this._width * 20}px`;
    grid.style.margin = "auto";
    grid.onpointerdown = (e) => {
      if (
        this._busy ||
        this._loading ||
        e.button !== 0 ||
        this._stroke !== undefined
      )
        return;
      e.preventDefault();
      grid.focus();
      this._pushUndo();
      this._stroke = e.pointerId;
      grid.setPointerCapture(e.pointerId);
      this._paintEvent(e);
    };
    grid.onpointermove = (e) => {
      if (this._stroke === e.pointerId) this._paintEvent(e);
    };
    grid.onpointerup =
      grid.onpointercancel =
      grid.onlostpointercapture =
        () => this._finishStroke();
    grid.onkeydown = (e) => this._keyPaint(e);
    this._draw();
    this._updateButtons();
  }
  _toolEdit(fn) {
    if (this._busy || this._loading) return;
    try {
      this._edit(fn);
    } catch (e) {
      this._message(e.message, "error");
    }
  }
  _syncRegion() {
    const r = this._region;
    for (const [id, key] of [
      ["rx", "x"],
      ["ry", "y"],
      ["rw", "width"],
      ["rh", "height"],
    ])
      this._$(id).value = r[key];
    this._$("region-note").textContent =
      `Selected area: x${r.x}, y${r.y}, ${r.width} × ${r.height}. Tools and drawing stay inside it.`;
    this._draw();
  }
  _insideRegion(x, y) {
    const r = this._region;
    return x >= r.x && y >= r.y && x < r.x + r.width && y < r.y + r.height;
  }
  _bindCreativeTools() {
    const $ = this._$;
    $("region-target").onchange = () => {
      if ($("region-target").value === "custom") return;
      const n = $("region-target").value;
      this._region =
        n === "all"
          ? { x: 0, y: 0, width: this._width, height: 20 }
          : { x: Number(n) * 20, y: 0, width: 20, height: 20 };
      this._syncRegion();
    };
    $("region-apply").onclick = () => {
      try {
        this._region = checkedRegion(
          Object.fromEntries(
            [
              ["rx", "x"],
              ["ry", "y"],
              ["rw", "width"],
              ["rh", "height"],
            ].map(([id, key]) => [
              key,
              $(id).value === "" ? NaN : Number($(id).value),
            ]),
          ),
          this._width,
        );
        $("region-target").value = "custom";
        this._syncRegion();
      } catch (e) {
        this._message(e.message, "error");
      }
    };
    $("region-fill").onclick = () =>
      this._toolEdit(
        () =>
          (this._pixels = mapRegion(
            this._pixels,
            this._width,
            this._region,
            () => this._brush,
          )),
      );
    $("region-clear").onclick = () =>
      this._toolEdit(
        () =>
          (this._pixels = mapRegion(
            this._pixels,
            this._width,
            this._region,
            () => OFF,
          )),
      );
    $("text-clock").onclick = () => {
      $("text-content").value = new Intl.DateTimeFormat(undefined, {
        hour: "2-digit",
        minute: "2-digit",
        hour12: false,
      }).format(new Date());
    };
    $("text-add").onclick = () => {
      let report;
      this._toolEdit(() => {
        report = renderText(
          this._pixels,
          this._width,
          this._region,
          $("text-content").value,
          {
            color: this._brush,
            x: Number($("text-x").value),
            y: Number($("text-y").value),
            scale: Number($("text-scale").value),
            wrap: $("text-wrap").checked,
            clear: $("text-clear").checked,
          },
        );
        this._pixels = report.pixels;
      });
      if (report)
        this._message(
          `Text added to preview.${report.clipped ? " Some text was clipped by the selected area." : ""}${report.unsupported ? ` ${report.unsupported} unsupported character(s) shown as ?.` : ""} Press Send to update the lights.`,
        );
    };
    $("palette-apply").onclick = () =>
      this._toolEdit(() => {
        const palette =
          $("palette-name").value === "custom"
            ? parsePalette($("palette-custom").value)
            : PALETTES[$("palette-name").value];
        this._pixels = recolor(
          this._pixels,
          this._width,
          this._region,
          palette,
          $("palette-white").checked,
        );
      });
    for (const b of this.shadowRoot.querySelectorAll("[data-transform]"))
      b.onclick = () =>
        this._toolEdit(
          () =>
            (this._pixels = transformRegion(
              this._pixels,
              this._width,
              this._region,
              b.dataset.transform,
            )),
        );
    $("tile-apply").onclick = () =>
      this._toolEdit(
        () =>
          (this._pixels = transformRegion(
            this._pixels,
            this._width,
            this._region,
            "tile",
            {
              tileWidth: Number($("tile-width").value),
              tileHeight: Number($("tile-height").value),
            },
          )),
      );
  }
  _selectBrush(pixel, label) {
    this._brush = pixel;
    for (const b of this.shadowRoot.querySelectorAll("[data-color]"))
      b.setAttribute("aria-pressed", String(Number(b.dataset.color) === pixel));
    this._$("brush-label").textContent = `Brush: ${label.toLowerCase()}`;
  }
  _message(text, kind = "") {
    this._$("status").textContent = text;
    this._$("status").className = `status ${kind}`;
  }
  _pushUndo() {
    this._undo.push(this._pixels.slice());
    if (this._undo.length > 40) this._undo.shift();
    this._redo = [];
  }
  _edit(fn) {
    if (this._busy || this._loading) return;
    this._finishStroke();
    this._pushUndo();
    fn();
    this._commitDesign();
    this._draw();
    this._message("Preview changed. Press Send to update the lights.");
    this._updateButtons();
  }
  _history(redo) {
    if (this._busy || this._loading) return;
    this._finishStroke();
    const from = redo ? this._redo : this._undo,
      to = redo ? this._undo : this._redo;
    if (!from.length) return;
    to.push(this._pixels.slice());
    this._pixels = from.pop();
    this._commitDesign();
    this._draw();
    this._message("Preview changed. Press Send to update the lights.");
    this._updateButtons();
  }
  _finishStroke() {
    if (this._stroke !== undefined) {
      this._stroke = undefined;
      this._lastPoint = null;
      this._commitDesign();
      this._updateButtons();
    }
  }
  _paintEvent(e) {
    const rect = this._$("grid").getBoundingClientRect();
    const x = Math.min(
        this._width - 1,
        Math.max(
          0,
          Math.floor(((e.clientX - rect.left) / rect.width) * this._width),
        ),
      ),
      y = Math.min(
        19,
        Math.max(0, Math.floor(((e.clientY - rect.top) / rect.height) * 20)),
      );
    let a = this._lastPoint || { x, y };
    const steps = Math.max(Math.abs(x - a.x), Math.abs(y - a.y), 1);
    for (let s = 0; s <= steps; s++) {
      const px = Math.round(a.x + ((x - a.x) * s) / steps);
      const py = Math.round(a.y + ((y - a.y) * s) / steps);
      if (this._insideRegion(px, py))
        this._pixels[py * this._width + px] = this._brush;
    }
    this._lastPoint = { x, y };
    this._cursor = { x, y };
    this._draw();
    this._message("Preview changed. Press Send to update the lights.");
  }
  _keyPaint(e) {
    if (this._busy || this._loading) return;
    let { x, y } = this._cursor;
    const arrows = {
      ArrowLeft: [-1, 0],
      ArrowRight: [1, 0],
      ArrowUp: [0, -1],
      ArrowDown: [0, 1],
    };
    if (arrows[e.key]) {
      e.preventDefault();
      const [dx, dy] = arrows[e.key];
      this._cursor = {
        x: Math.max(0, Math.min(this._width - 1, x + dx)),
        y: Math.max(0, Math.min(19, y + dy)),
      };
      this._draw();
    } else if ([" ", "Enter", "Delete", "Backspace"].includes(e.key)) {
      if (!this._insideRegion(x, y)) {
        e.preventDefault();
        return;
      }
      e.preventDefault();
      this._edit(
        () =>
          (this._pixels[y * this._width + x] = ["Delete", "Backspace"].includes(
            e.key,
          )
            ? OFF
            : this._brush),
      );
    }
  }
  _draw() {
    this._stopMovementPreview();
    if (!this._$) return;
    const canvas = this._$("grid"),
      ctx = canvas.getContext("2d");
    ctx.fillStyle = "#0c1628";
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    for (let y = 0; y < 20; y++)
      for (let x = 0; x < this._width; x++) {
        ctx.fillStyle = pixelCss(this._pixels[y * this._width + x]);
        ctx.fillRect(x * 20 + 2, y * 20 + 2, 16, 16);
      }
    for (let x = 20; x < this._width; x += 20) {
      ctx.fillStyle = "#9eb0c8";
      ctx.fillRect(x * 20 - 1, 0, 2, 400);
    }
    const r = this._region;
    ctx.strokeStyle = "#39d8bc";
    ctx.lineWidth = 2;
    ctx.strokeRect(
      r.x * 20 + 1,
      r.y * 20 + 1,
      r.width * 20 - 2,
      r.height * 20 - 2,
    );
    const { x, y } = this._cursor;
    ctx.strokeStyle = "#fff";
    ctx.lineWidth = 1;
    ctx.strokeRect(x * 20 + 0.5, y * 20 + 0.5, 19, 19);
    this._$("position").textContent =
      `Selected: x${x}, y${y} · arrows move · Space paints · Delete erases`;
  }
  _stopMovementPreview() {
    if (this._previewRAF !== undefined) cancelAnimationFrame(this._previewRAF);
    this._previewRAF = undefined;
    this._previewRunning = false;
    if (!this._$?.("preview-play")) return;
    this._$("preview-play").disabled = this._busy || this._loading;
    this._$("preview-stop").disabled = true;
    this._$("motion-output").hidden = true;
    this._$("motion-output").style.display = "none";
    this._$("preview-state").textContent =
      "Stopped. Play to simulate the current draft.";
  }
  _startMovementPreview() {
    this._stopMovementPreview();
    if (this._busy || this._loading || !this.isConnected || document.hidden)
      return;
    const frames =
      this._designKind === "animation"
        ? this._animationFrames.map((f, i) =>
            (i === this._activeFrame
              ? this._pixels
              : f || this._pixels
            ).slice(),
          )
        : [this._pixels.slice()];
    const settings = { ...this._settings[this._designKind] };
    const animation = this._designKind === "animation";
    const width = this._width;
    const canvas = this._$("motion-preview");
    canvas.width = width * 8;
    canvas.height = 160;
    canvas.style.minWidth = "0";
    const ctx = canvas.getContext("2d");
    this._$("motion-output").hidden = false;
    this._$("motion-output").style.display = "block";
    const reduced = window.matchMedia(
      "(prefers-reduced-motion: reduce)",
    ).matches;
    const paint = (elapsed) => {
      const result = estimateMovement(
        frames,
        width,
        settings,
        elapsed,
        animation,
      );
      ctx.globalAlpha = 1;
      ctx.fillStyle = "#0c1628";
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      ctx.globalAlpha = result.opacity;
      result.pixels.forEach((p, i) => {
        if (p === OFF) return;
        ctx.fillStyle = pixelCss(p);
        ctx.fillRect((i % width) * 8 + 1, Math.floor(i / width) * 8 + 1, 6, 6);
      });
      ctx.globalAlpha = 1;
      for (let x = 20; x < width; x += 20) {
        ctx.fillStyle = "#9eb0c8";
        ctx.fillRect(x * 8 - 1, 0, 2, 160);
      }
    };
    paint(0);
    this._$("preview-stop").disabled = false;
    this._$("preview-state").textContent = reduced
      ? "Reduced motion: static estimate only. No light commands sent."
      : "Playing a local estimate. Device speed and timing are not measured.";
    if (reduced || settings.movement === "still") return;
    this._previewRunning = true;
    this._$("preview-play").disabled = true;
    this._$("preview-stop").disabled = false;
    const start = performance.now();
    let last = -Infinity;
    const tick = (now) => {
      if (!this._previewRunning || !this.isConnected || document.hidden) {
        this._stopMovementPreview();
        return;
      }
      if (now - last >= 50) {
        paint(now - start);
        last = now;
      }
      this._previewRAF = requestAnimationFrame(tick);
    };
    this._previewRAF = requestAnimationFrame(tick);
  }
  set externalBusy(value) {
    this._externalBusy = Boolean(value);
    this._updateButtons();
  }
  _updateButtons() {
    if (!this._$) return;
    for (const b of this.shadowRoot.querySelectorAll("button,select,input"))
      b.disabled = this._busy || this._loading;
    this._$("undo").disabled =
      this._busy || this._loading || !this._undo.length;
    this._$("redo").disabled =
      this._busy || this._loading || !this._redo.length;
    const available = Boolean(
      this._hass?.services?.hello_fairy_ble?.[
        this._designKind === "animation"
          ? "set_two_picture_animation"
          : "set_frame"
      ],
    );
    this._$("send").disabled =
      this._busy ||
      this._loading ||
      !available ||
      this._capabilityBlocked ||
      this._externalBusy;
    this._$("show-a").disabled =
      this._busy || this._loading || !this._animationFrames[0];
    this._$("show-b").disabled =
      this._busy || this._loading || !this._animationFrames[1];
    this._$("send-animation").disabled =
      this._busy ||
      this._loading ||
      this._externalBusy ||
      this._capabilityBlocked ||
      !this._animationFrames.every(Boolean) ||
      !this._hass?.services?.hello_fairy_ble?.set_two_picture_animation;
    this._$("animation-state").textContent = this._animationFrames
      .map((f, i) => `${i === 0 ? "A" : "B"}: ${f ? "saved" : "empty"}`)
      .join(" · ");
    const active = this._busy || this._loading;
    if (active !== this._reportedBusy) {
      this._reportedBusy = active;
      this.dispatchEvent(
        new CustomEvent("studio-busy", {
          detail: { busy: active },
          bubbles: true,
          composed: true,
        }),
      );
    }
    if (active) this._stopMovementPreview();
    this._$("preview-play").disabled = active || this._previewRunning;
    this._$("preview-stop").disabled = !this._previewRunning;
    this._$("send").textContent = this._busy ? "Sending…" : "Send design";
    this._syncDesignControls();
    if (this._capabilityBlocked && !this._busy)
      this._message(
        "DIY is unavailable for the device type reported by a selected curtain. Standard light controls still work.",
        "error",
      );
    if (this._hass && !available && !this._busy)
      this._message(
        "Hello Fairy frame action is unavailable. Check that the integration is loaded.",
        "error",
      );
  }
  async _loadImage(file) {
    if (this._busy || this._loading) return;
    if (!["image/png", "image/jpeg", "image/webp"].includes(file.type)) {
      this._message("Choose a PNG, JPG or WebP image.", "error");
      return;
    }
    if (file.size > 15 * 1024 * 1024) {
      this._message("Choose an image smaller than 15 MB.", "error");
      return;
    }
    this._loading = true;
    const generation = ++this._loadGeneration;
    this._updateButtons();
    this._message("Opening image…");
    let bitmap;
    try {
      bitmap = await createImageBitmap(file);
      if (bitmap.width * bitmap.height > 32_000_000)
        throw new Error("Choose an image below 32 megapixels.");
      if (generation !== this._loadGeneration) return;
      if (this._image) this._image.close();
      this._image = bitmap;
      bitmap = null;
      this._$("filename").textContent = file.name;
      this._loading = false;
      this._resample();
    } catch (e) {
      if (generation === this._loadGeneration)
        this._message(`Image could not be opened: ${e.message}`, "error");
    } finally {
      bitmap?.close();
      if (generation === this._loadGeneration) {
        this._loading = false;
        this._updateButtons();
      }
    }
  }
  _resample() {
    if (!this._image) return;
    this._edit(() => {
      const c = document.createElement("canvas");
      c.width = this._width;
      c.height = 20;
      const ctx = c.getContext("2d", { willReadFrequently: true });
      ctx.fillStyle = "#000";
      ctx.fillRect(0, 0, c.width, c.height);
      const ratio =
        this._$("fit").value === "cover"
          ? Math.max(c.width / this._image.width, c.height / this._image.height)
          : Math.min(
              c.width / this._image.width,
              c.height / this._image.height,
            );
      const w = this._image.width * ratio,
        h = this._image.height * ratio;
      ctx.drawImage(this._image, (c.width - w) / 2, (20 - h) / 2, w, h);
      const data = ctx.getImageData(0, 0, c.width, 20).data;
      this._pixels = Array.from({ length: c.width * 20 }, (_, i) =>
        rgbToPixel(...data.slice(i * 4, i * 4 + 4)),
      );
    });
  }
  exportDesign() {
    this._finishStroke();
    this._commitDesign();
    return structuredClone({
      format: "hello-fairy-pattern",
      version: 2,
      width: this._width,
      height: 20,
      kind: this._designKind,
      frames:
        this._designKind === "animation"
          ? this._animationFrames
          : [this._pixels],
      settings: this._settings[this._designKind],
    });
  }
  _savePattern() {
    const data = JSON.stringify(this.exportDesign(), null, 2);
    const url = URL.createObjectURL(
      new Blob([data], { type: "application/json" }),
    );
    const a = document.createElement("a");
    a.href = url;
    a.download = `curtain-${this._designKind}-${this._width}x20.json`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  async _loadPattern(file) {
    if (this._busy || this._loading) return;
    if (file.size > 200_000) {
      this._message("Design file is too large.", "error");
      return;
    }
    this._loading = true;
    this._updateButtons();
    try {
      const p = JSON.parse(await file.text());
      if (
        p.format !== "hello-fairy-pattern" ||
        p.width !== this._width ||
        p.height !== 20
      )
        throw new Error("This design uses a different canvas size.");
      let kind, frames, settings;
      if (p.version === 1) {
        kind = "picture";
        frames = [validateFrame(p.pixels, this._width)];
        settings = { movement: "still", speed: 100, brightness: 100 };
      } else if (p.version === 2) {
        kind = p.kind;
        if (
          !["picture", "animation"].includes(kind) ||
          !Array.isArray(p.frames) ||
          p.frames.length !== (kind === "animation" ? 2 : 1)
        )
          throw new Error("Invalid design pictures.");
        frames = p.frames.map((f) => validateFrame(f, this._width));
        settings = p.settings;
        if (
          !settings ||
          !this._movementOptions(kind).some(([v]) => v === settings.movement) ||
          ![settings.speed, settings.brightness].every(
            (v) => Number.isInteger(v) && v >= 0 && v <= 100,
          )
        )
          throw new Error("Invalid playback settings.");
      } else throw new Error("Unsupported design version.");
      this._loading = false;
      this._changeKind(kind);
      this._settings[kind] = { ...settings };
      if (kind === "animation") {
        this._animationFrames = frames;
        this._activeFrame = 0;
      }
      this._pixels = frames[0].slice();
      this._commitDesign();
      this._undo = [];
      this._redo = [];
      this._draw();
      this._updateButtons();
      this._message("Design opened. Press Send design to update the curtains.");
    } catch (e) {
      this._message(`Design could not be opened: ${e.message}`, "error");
    } finally {
      this._loading = false;
      this._updateButtons();
    }
  }
  _commitDesign() {
    if (!this._pixels) return;
    if (this._designKind === "animation")
      this._animationFrames[this._activeFrame] = this._pixels.slice();
    else this._pictureDraft = this._pixels.slice();
  }
  _changeKind(kind) {
    if (this._busy || this._loading || kind === this._designKind) return;
    this._finishStroke();
    this._commitDesign();
    this._designKind = kind;
    if (kind === "animation") {
      this._animationFrames = this._animationFrames.map(
        (f) => f || this._pixels.slice(),
      );
      this._pixels = this._animationFrames[this._activeFrame].slice();
    } else this._pixels = (this._pictureDraft || this._pixels).slice();
    this._image?.close();
    this._image = null;
    this._undo = [];
    this._redo = [];
    this._draw();
    this._updateButtons();
    this._message(
      kind === "animation"
        ? "Choose First picture or Second picture, then draw or choose an image. Press Send design when ready."
        : "Picture mode. Choose a pattern or image, then Send design.",
    );
  }
  _activateFrame(index) {
    if (this._busy || this._loading) return;
    if (this._designKind !== "animation") this._changeKind("animation");
    this._finishStroke();
    this._commitDesign();
    this._activeFrame = index;
    this._pixels = this._animationFrames[index].slice();
    this._image?.close();
    this._image = null;
    this._undo = [];
    this._redo = [];
    this._draw();
    this._updateButtons();
    this._message(
      `Editing ${index === 0 ? "first" : "second"} picture. Changes are saved automatically in this design.`,
    );
  }
  _movementOptions(kind) {
    return kind === "animation"
      ? [
          ["blink", "Alternate"],
          ["breathe", "Fade between pictures"],
        ]
      : [
          ["still", "Still"],
          ["up", "Move up"],
          ["down", "Move down"],
          ["left", "Move left"],
          ["right", "Move right"],
          ["blink", "Blink"],
          ["breathe", "Breathe"],
          ["loop_up", "Loop up"],
          ["loop_down", "Loop down"],
          ["loop_left", "Loop left"],
          ["loop_right", "Loop right"],
        ];
  }
  _syncDesignControls() {
    const $ = this._$;
    if (!$("movement")) return;
    const kind = this._designKind,
      s = this._settings[kind];
    $("mode-picture").setAttribute("aria-pressed", String(kind === "picture"));
    $("mode-animation").setAttribute(
      "aria-pressed",
      String(kind === "animation"),
    );
    $("animation").hidden = kind !== "animation";
    const signature = kind;
    if ($("movement").dataset.kind !== signature) {
      $("movement").innerHTML = this._movementOptions(kind)
        .map(([v, label]) => `<option value="${v}">${label}</option>`)
        .join("");
      $("movement").dataset.kind = signature;
    }
    $("movement").value = s.movement;
    $("speed").value = s.speed;
    $("speed-value").textContent = s.speed + "%";
    $("diy-brightness").value = s.brightness;
    $("brightness-value").textContent = s.brightness + "%";
    for (let i = 0; i < 2; i++) {
      const id = i ? "b" : "a";
      $("show-" + id).disabled = this._busy || this._loading;
      $("show-" + id).setAttribute(
        "aria-pressed",
        String(this._activeFrame === i),
      );
      if (this._animationFrames[i])
        this._mini($("thumb-" + id), this._animationFrames[i], this._width);
    }
    $("animation-state").textContent =
      "Two pictures · edits stay in this tab until you save the design";
    $("apply-playback").disabled =
      this._busy ||
      this._loading ||
      this._capabilityBlocked ||
      this._externalBusy ||
      !this._hass?.services?.hello_fairy_ble?.set_diy_playback;
  }
  _mini(c, pixels, width) {
    c.width = width;
    c.height = 20;
    const ctx = c.getContext("2d");
    for (let i = 0; i < pixels.length; i++) {
      ctx.fillStyle = pixels[i] === OFF ? "#09111e" : pixelCss(pixels[i]);
      ctx.fillRect(i % width, Math.floor(i / width), 1, 1);
    }
  }
  async _applyPlayback() {
    if (
      this._busy ||
      this._loading ||
      this._capabilityBlocked ||
      this._externalBusy
    )
      return;
    this._finishStroke();
    this._busy = true;
    this._updateButtons();
    try {
      for (const c of this._config.curtains)
        await this._hass.callService("hello_fairy_ble", "set_diy_playback", {
          address: c.address,
          kind: this._designKind,
          ...this._settings[this._designKind],
        });
      this._message(
        "Playback settings sent. Check movement and speed on the curtains.",
        "success",
      );
    } catch (e) {
      this._message(
        `Playback settings stopped: ${e.message || e}. Send the design first if needed.`,
        "error",
      );
    } finally {
      this._busy = false;
      this._updateButtons();
      this.dispatchEvent(
        new CustomEvent("studio-sent", { bubbles: true, composed: true }),
      );
    }
  }
  async _applyAfterUpload(curtain, kind) {
    const settings = this._settings[kind];
    const defaultMovement = kind === "animation" ? "blink" : "still";
    if (
      settings.movement !== defaultMovement ||
      settings.speed !== 100 ||
      settings.brightness !== 100
    )
      await this._hass.callService("hello_fairy_ble", "set_diy_playback", {
        address: curtain.address,
        kind,
        ...settings,
      });
  }
  _storeAnimationFrame(index) {
    if (this._busy || this._loading) return;
    this._finishStroke();
    this._animationFrames[index] = validateFrame(this._pixels, this._width);
    this._updateButtons();
    this._message(
      `Picture ${index === 0 ? "A" : "B"} saved in this tab. Save again after editing to update it.`,
    );
  }
  _showAnimationFrame(index) {
    if (this._busy || this._loading || !this._animationFrames[index]) return;
    this._edit(() => (this._pixels = this._animationFrames[index].slice()));
    this._image?.close();
    this._image = null;
    this._$("filename").textContent =
      `Editing picture ${index === 0 ? "A" : "B"}`;
  }
  async _sendAnimation() {
    if (
      this._busy ||
      this._loading ||
      this._capabilityBlocked ||
      this._externalBusy ||
      !this._animationFrames.every(Boolean) ||
      !this._hass?.services?.hello_fairy_ble?.set_two_picture_animation
    )
      return;
    this._finishStroke();
    this._commitDesign();
    const pictures = this._animationFrames.map((f) =>
      splitFrame(f, this._config.curtains.length),
    );
    this._busy = true;
    this._updateButtons();
    let sent = 0;
    try {
      for (let i = 0; i < this._config.curtains.length; i++) {
        const curtain = this._config.curtains[i];
        this._message(
          `Uploading two pictures: ${curtain.name} (${i + 1} of ${this._config.curtains.length})…`,
        );
        await this._hass.callService(
          "hello_fairy_ble",
          "set_two_picture_animation",
          {
            address: curtain.address,
            frames: [pictures[0][i], pictures[1][i]].map((frame) =>
              transformCurtain(frame, this._orientations?.[curtain.address]),
            ),
            experimental: true,
          },
        );
        await this._applyAfterUpload(curtain, "animation");
        sent++;
      }
      this._message(
        "Animation sent. Check it on the curtains; each curtain plays independently.",
        "success",
      );
    } catch (e) {
      this._message(
        `Stopped: ${sent} of ${this._config.curtains.length} completed. ${e.message || String(e)}. Check your lights before sending again.`,
        "error",
      );
    } finally {
      this._busy = false;
      this._updateButtons();
      this.dispatchEvent(
        new CustomEvent("studio-sent", { bubbles: true, composed: true }),
      );
    }
  }
  async _send() {
    if (
      this._busy ||
      this._loading ||
      this._capabilityBlocked ||
      this._externalBusy ||
      !this._hass?.services?.hello_fairy_ble?.set_frame
    )
      return;
    this._finishStroke();
    const frames = splitFrame(this._pixels, this._config.curtains.length);
    this._busy = true;
    this._updateButtons();
    let sent = 0;
    try {
      for (let i = 0; i < frames.length; i++) {
        const curtain = this._config.curtains[i];
        this._message(`Sending ${i + 1} of ${frames.length}: ${curtain.name}…`);
        await this._hass.callService("hello_fairy_ble", "set_frame", {
          address: curtain.address,
          pixels: transformCurtain(
            frames[i],
            this._orientations?.[curtain.address],
          ),
        });
        await this._applyAfterUpload(curtain, "picture");
        sent++;
      }
      this._message(
        "Transfer completed. Check the pattern on your curtain" +
          (frames.length > 1 ? "s" : "") +
          ".",
        "success",
      );
    } catch (e) {
      this._message(
        `Stopped: ${sent} of ${frames.length} completed. ${e.message || String(e)}. Check your lights before sending again.`,
        "error",
      );
    } finally {
      this._busy = false;
      this._updateButtons();
      this.dispatchEvent(
        new CustomEvent("studio-sent", { bubbles: true, composed: true }),
      );
    }
  }
}

if (!customElements.get("hello-fairy-canvas-editor"))
  customElements.define("hello-fairy-canvas-editor", HelloFairyCurtainStudio);
