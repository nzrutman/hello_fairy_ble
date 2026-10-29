/** Integration-owned Hello Fairy Studio panel, v2.0.0.
 * Generated with aurora@aurora-smart-home (ha-integration-dev skill)
 * https://github.com/tonylofgren/aurora-smart-home
 */
import { normalizeConfig } from "./editor.js?v=2.0.0";
import "./device-status.js?v=2.0.0";
import "./library.js?v=2.0.0";
import "./native-controls.js?v=2.0.0";

const escape = (s) =>
  String(s).replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );

export class HelloFairyStudioPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._selected = [];
    this._devices = [];
    this._loaded = false;
    this._loading = false;
    this._orientations = {};
    this._savingOrientation = false;
  }
  connectedCallback() {
    this._render();
    if (this._hass && !this._loaded) this._load();
  }
  set hass(hass) {
    this._hass = hass;
    if (this._canvas) this._canvas.hass = hass;
    if (this._$) {
      this._$("library").hass = hass;
      this._$("native-controls").hass = hass;
    }
    if (this.isConnected && !this._loaded && !this._loading) this._load();
  }
  set narrow(value) {
    this._narrow = value;
    if (this._$) this._$("menu").hidden = !value;
  }
  set panel(value) {
    this._panel = value;
  }
  _render() {
    if (this._$) return;
    this.shadowRoot.innerHTML = `<style>
      :host{display:block;height:100%;background:var(--primary-background-color,#eef2f4);color:var(--primary-text-color,#172536);font:14px/1.5 var(--paper-font-body1_-_font-family,system-ui,sans-serif)}*{box-sizing:border-box}.page{height:100%;overflow:auto}.bar{display:flex;align-items:center;gap:14px;height:64px;padding:0 24px;background:var(--app-header-background-color,var(--primary-color,#087f73));color:var(--app-header-text-color,#fff)}h1{font-size:20px;font-weight:500;margin:0}.bar small{margin-left:auto}main{max-width:1120px;margin:auto;padding:24px}.layout{background:var(--card-background-color,#fff);border:1px solid var(--divider-color,#dce5e7);border-radius:14px;padding:14px 18px;margin-bottom:18px}summary{font-weight:600;cursor:pointer;min-height:28px}.help{color:var(--secondary-text-color,#526373);font-size:13px;margin:8px 0 12px}.devices{display:grid;gap:8px}.device{display:flex;align-items:center;gap:8px;flex-wrap:wrap;border-bottom:1px solid var(--divider-color,#dce5e7);padding:7px 0}label{display:flex;align-items:center;gap:8px;flex:1;min-width:180px;min-height:44px}input{width:20px;height:20px}button{font:inherit;min-height:44px;padding:7px 12px;border-radius:8px;color:inherit;background:var(--card-background-color,#fff);border:1px solid var(--divider-color,#dce5e7);cursor:pointer}button:disabled{opacity:.45;cursor:default}button:focus-visible,input:focus-visible,summary:focus-visible{outline:3px solid #3998df;outline-offset:2px}.position{font-size:12px;color:var(--secondary-text-color,#526373)}.move{display:flex;gap:6px}#refresh{margin-top:12px}.notice{color:var(--error-color,#b42318);font-size:13px}a{color:var(--primary-color,#087f73)}.empty{padding:24px;background:var(--card-background-color,#fff);border-radius:14px}.menu{color:inherit;background:transparent;border:0;font-size:24px;padding:0 8px}#connection{margin:8px 0 18px;color:var(--secondary-text-color,#526373)}
      @media(max-width:600px){main{padding:12px}.bar{padding:0 12px}.bar small{display:none}.layout{padding:12px}.move button{padding:7px 10px}}
    </style><div class="page"><header class="bar"><button id="menu" class="menu" aria-label="Open sidebar" hidden>☰</button><h1>Curtain Studio</h1><small>Hello Fairy · 2.0.0</small></header><main><details class="layout"><summary id="summary">Your Hello Fairy curtains</summary><p class="help">Choose curtains to use together. Their numbered order is left to right. Changing the layout starts a blank canvas.</p><div id="devices" class="devices"></div><button id="refresh">Refresh curtains</button><div id="orientation-settings"></div><p class="help">To add another physical curtain, use <a href="/config/integrations">Settings → Devices &amp; services</a> and add Hello Fairy Bluetooth Lights.</p><div id="layout-message" class="notice" role="alert"></div></details><div id="connection" role="status" aria-live="polite">Finding your configured curtains…</div><hello-fairy-device-status id="device-status"></hello-fairy-device-status><hello-fairy-native-controls id="native-controls"></hello-fairy-native-controls><div id="editor"></div><hello-fairy-design-library id="library"></hello-fairy-design-library></main></div>`;
    this._$ = (id) => this.shadowRoot.getElementById(id);
    this._$("refresh").onclick = () => this._load();
    this._$("menu").hidden = !this._narrow;
    this._$("menu").onclick = () =>
      this.dispatchEvent(
        new CustomEvent("hass-toggle-menu", { bubbles: true, composed: true }),
      );
    this.addEventListener("studio-library-updated", (event) => {
      this._orientations = structuredClone(event.detail?.orientations || {});
      if (this._canvas) this._canvas._orientations = this._orientations;
      if (!this._savingOrientation) this._showOrientations();
      this._updateBusy();
    });
    this.addEventListener("studio-library-busy", (event) => {
      this._libraryImportBusy = Boolean(event.detail?.busy);
      if (this._canvas) this._canvas.externalBusy = this._libraryImportBusy;
      this._$("device-status").externalBusy = this._libraryImportBusy;
      this._updateBusy();
    });
    this.addEventListener("studio-busy", () => this._updateBusy());
    this.addEventListener("studio-apply-layout", (event) =>
      this._applySavedLayout(event.detail),
    );
    this.addEventListener("studio-sent", () => {
      this._load();
      this._$("library").refresh();
    });
  }
  _storageKey() {
    return `hello_fairy_ble.studio.layout.${this._hass?.user?.id || "user"}`;
  }
  _savedSelection() {
    try {
      const saved = JSON.parse(
        localStorage.getItem(this._storageKey()) || "null",
      );
      if (Array.isArray(saved))
        return saved
          .filter(
            (address, i) =>
              typeof address === "string" &&
              saved.indexOf(address) === i &&
              this._devices.some((d) => d.address === address),
          )
          .slice(0, 8);
    } catch {}
    return [];
  }
  _remember() {
    try {
      localStorage.setItem(this._storageKey(), JSON.stringify(this._selected));
    } catch {
      /* Layout still works if browser storage is unavailable. */
    }
  }
  async _load() {
    if (this._loading || this._canvas?._busy || this._canvas?._loading) return;
    this._loading = true;
    this._updateBusy();
    try {
      const result = await this._hass.callWS({
        type: "hello_fairy_ble/studio/devices",
      });
      if (!Array.isArray(result.curtains))
        throw new Error("The integration returned an invalid device list.");
      this._devices = result.curtains.map((d) => ({
        ...normalizeConfig({ curtains: [d] }).curtains[0],
        discovered: Boolean(d.discovered),
        snapshot: d.snapshot,
      }));
      const next = (
        this._loaded ? this._selected : this._savedSelection()
      ).filter((a) => this._devices.some((d) => d.address === a));
      this._selected = next.length
        ? next
        : this._devices.slice(0, 1).map((d) => d.address);
      this._loaded = true;
      this._remember();
      this._showLayout();
      this._showCanvas();
      this._$("connection").textContent = this._devices.length
        ? "Choose Picture or Animation, pick a pattern or image, set movement and speed, then Send design."
        : "No loaded Hello Fairy curtains. Add or enable the integration, then press Refresh curtains.";
    } catch (e) {
      this._$("connection").textContent =
        `Curtains could not be loaded: ${e.message || String(e)}. Check that the updated integration is loaded and you are signed in as an administrator, then press Refresh curtains.`;
    } finally {
      this._loading = false;
      this._updateBusy();
    }
  }
  _showLayout() {
    const names = this._selected.map(
      (a) => this._devices.find((d) => d.address === a)?.name || a,
    );
    this._$("summary").textContent = names.length
      ? `Display layout: ${names.join(" → ")}`
      : "Your Hello Fairy curtains";
    // Selected curtains are listed in their physical order, followed by unused devices.
    const order = [
      ...this._selected,
      ...this._devices
        .filter((d) => !this._selected.includes(d.address))
        .map((d) => d.address),
    ];
    this._$("devices").innerHTML = order
      .map((address) => {
        const d = this._devices.find((d) => d.address === address),
          i = this._selected.indexOf(address);
        return `<div class="device"><label><input type="checkbox" data-address="${escape(address)}" ${i >= 0 ? "checked" : ""}><span>${escape(d.name)}${d.snapshot?.device_info && !d.snapshot.diy_supported ? ' <span class="position">· DIY unavailable for this device type</span>' : !d.discovered ? ' <span class="position">· waiting for Bluetooth discovery</span>' : ""}</span></label>${i >= 0 ? `<span class="position">${i + 1}${i === 0 ? " · leftmost" : ""}</span><div class="move"><button data-move="-1" data-address="${escape(address)}" aria-label="Move ${escape(d.name)} left" ${i === 0 ? "disabled" : ""}>←</button><button data-move="1" data-address="${escape(address)}" aria-label="Move ${escape(d.name)} right" ${i === this._selected.length - 1 ? "disabled" : ""}>→</button></div>` : ""}</div>`;
      })
      .join("");
    for (const checkbox of this.shadowRoot.querySelectorAll(
      "input[data-address]",
    ))
      checkbox.onchange = () => {
        const a = checkbox.dataset.address;
        this._requestLayout(
          checkbox.checked
            ? [...this._selected, a]
            : this._selected.filter((v) => v !== a),
        );
      };
    for (const b of this.shadowRoot.querySelectorAll("[data-move]"))
      b.onclick = () => {
        const next = this._selected.slice(),
          i = next.indexOf(b.dataset.address),
          j = i + Number(b.dataset.move);
        [next[i], next[j]] = [next[j], next[i]];
        this._requestLayout(next);
      };
    this._showOrientations();
    this._updateBusy();
  }
  _applySavedLayout(detail) {
    const addresses = detail?.addresses;
    if (
      !Array.isArray(addresses) ||
      addresses.some((a) => typeof a !== "string")
    ) {
      this._$("library")._message("This saved layout is invalid.");
      return false;
    }
    const next = addresses.map((a) => a.trim().toUpperCase());
    if (
      new Set(next).size !== next.length ||
      next.some((a) => !this._devices.some((d) => d.address === a))
    ) {
      this._$("library")._message(
        "This layout contains duplicate or unloaded curtains. Load its devices in HA first.",
      );
      return false;
    }
    const applied = this._requestLayout(next);
    this._$("library")._message(
      applied
        ? `Layout “${detail.name || "saved layout"}” selected. Nothing was sent to the lights.`
        : "Layout unchanged.",
    );
    return applied;
  }
  _requestLayout(next) {
    if (
      this._libraryImportBusy ||
      this._canvas?._busy ||
      this._canvas?._loading ||
      this._$("device-status")?._busy ||
      this._$("native-controls")?._busy
    ) {
      this._showLayout();
      return false;
    }
    if (!next.length || next.length > 8) {
      this._$("layout-message").textContent =
        "Choose between one and eight curtains.";
      this._showLayout();
      return false;
    }
    if (JSON.stringify(next) === JSON.stringify(this._selected)) return true;
    if (
      (this._canvas?._pixels.some((p) => p !== 254) ||
        this._canvas?._animationFrames?.some(Boolean)) &&
      !window.confirm(
        "Changing the curtain layout clears this preview and saved animation pictures. Save your pictures first if you want to keep them. Continue?",
      )
    ) {
      this._showLayout();
      return false;
    }
    this._selected = next;
    this._$("layout-message").textContent = "";
    this._remember();
    this._showLayout();
    this._showCanvas();
    return true;
  }
  _showCanvas() {
    if (!this._selected.length) {
      this._canvas?.remove();
      this._canvas = null;
      this._layoutSignature = null;
      this._$("native-controls").devices = [];
      this._$("library").addresses = [];
      this._$("library").editor = null;
      this._$("editor").innerHTML =
        '<div class="empty">Your image editor will appear here when a Hello Fairy curtain is loaded.</div>';
      return;
    }
    if (!this._canvas) {
      this._$("editor").replaceChildren();
      this._canvas = document.createElement("hello-fairy-canvas-editor");
      this._$("editor").append(this._canvas);
    }
    const curtains = this._selected.map((a) =>
      this._devices.find((d) => d.address === a),
    );
    const signature = JSON.stringify(
      curtains.map(({ address, name }) => ({ address, name })),
    );
    if (signature !== this._layoutSignature) {
      this._canvas.setConfig({ title: "Curtain Studio", curtains });
      this._layoutSignature = signature;
    }
    this._canvas._capabilityBlocked = curtains.some(
      (c) => c.snapshot?.device_info && !c.snapshot.diy_supported,
    );
    this._canvas._orientations = this._orientations;
    this._canvas.externalBusy = Boolean(this._libraryImportBusy);
    this._canvas.hass = this._hass;
    this._$("device-status").hass = this._hass;
    this._$("device-status").devices = curtains;
    this._$("native-controls").hass = this._hass;
    this._$("native-controls").devices = curtains;
    const library = this._$("library");
    library.hass = this._hass;
    library.editor = this._canvas;
    library.addresses = this._selected.slice();
    library.disabled = Boolean(this._canvas._capabilityBlocked);
  }
  _showOrientations() {
    if (!this._$) return;
    this._$("orientation-settings").innerHTML = this._selected.length
      ? `<p class="help"><strong>Installation corrections</strong> are saved in Home Assistant per curtain. They apply to future Studio uploads, favorites, playlists, messages and clocks. The canvas stays in artwork coordinates. Native movement directions are not remapped.</p>${this._selected
          .map((address) => {
            const name =
              this._devices.find((d) => d.address === address)?.name || address;
            const o = this._orientations[address] || {};
            return `<div class="device"><span>${escape(name)}</span><label style="min-width:120px;flex:0">Rotate <select data-orientation="rotation" data-curtain="${escape(address)}" aria-label="Rotate ${escape(name)}">${[0, 90, 180, 270].map((v) => `<option value="${v}" ${v === (o.rotation || 0) ? "selected" : ""}>${v}° clockwise</option>`).join("")}</select></label><label style="min-width:100px;flex:0"><input type="checkbox" data-orientation="flip_h" data-curtain="${escape(address)}" ${o.flip_h ? "checked" : ""}>Flip left/right</label><label style="min-width:100px;flex:0"><input type="checkbox" data-orientation="flip_v" data-curtain="${escape(address)}" ${o.flip_v ? "checked" : ""}>Flip up/down</label></div>`;
          })
          .join("")}`
      : "";
    for (const field of this.shadowRoot.querySelectorAll("[data-orientation]"))
      field.onchange = () => this._saveOrientation(field.dataset.curtain);
    this._updateBusy();
  }
  async _saveOrientation(address) {
    if (this._savingOrientation) return;
    const fields = Array.from(
      this.shadowRoot.querySelectorAll("[data-orientation]"),
    ).filter((el) => el.dataset.curtain === address);
    const value = { address };
    for (const field of fields)
      value[field.dataset.orientation] =
        field.type === "checkbox" ? field.checked : Number(field.value);
    this._savingOrientation = true;
    this._updateBusy();
    try {
      const result = await this._hass.callWS({
        type: "hello_fairy_ble/studio/library",
        action: "save_orientation",
        payload: value,
      });
      this._orientations = result.orientations || {};
      if (this._canvas) this._canvas._orientations = this._orientations;
      if (this._$("library")._data)
        this._$("library")._data.orientations = this._orientations;
      this._$("layout-message").textContent =
        "Installation correction saved. Nothing was sent to the lights.";
      await this._$("library").refresh();
    } catch (e) {
      this._$("layout-message").textContent = e.message || String(e);
    } finally {
      this._savingOrientation = false;
      this._showOrientations();
      this._updateBusy();
    }
  }
  _updateBusy() {
    if (!this._$) return;
    this._$("library").editorBusy = Boolean(
      this._canvas?._busy ||
        this._canvas?._loading ||
        this._$("device-status")?._busy ||
        this._$("native-controls")?._busy,
    );
    const busy =
      this._loading ||
      this._savingOrientation ||
      this._libraryImportBusy ||
      this._libraryImportBusy ||
      this._canvas?._busy ||
      this._canvas?._loading ||
      this._$("device-status")?._busy ||
      this._$("native-controls")?._busy;
    const nativeBusy = Boolean(this._$("native-controls")?._busy);
    if (this._canvas)
      this._canvas.externalBusy = Boolean(
        this._libraryImportBusy || nativeBusy,
      );
    this._$("device-status").externalBusy = Boolean(
      this._libraryImportBusy || nativeBusy,
    );
    this._$("native-controls").externalBusy = Boolean(
      this._libraryImportBusy ||
        this._canvas?._busy ||
        this._canvas?._loading ||
        this._$("device-status")?._busy,
    );
    this._$("refresh").disabled = Boolean(busy);
    for (const input of this.shadowRoot.querySelectorAll("[data-orientation]"))
      input.disabled = Boolean(busy || this._$("library").running);
    for (const input of this.shadowRoot.querySelectorAll("input[data-address]"))
      input.disabled = Boolean(busy);
    for (const b of this.shadowRoot.querySelectorAll("[data-move]")) {
      const i = this._selected.indexOf(b.dataset.address),
        j = i + Number(b.dataset.move);
      b.disabled = Boolean(busy) || j < 0 || j >= this._selected.length;
    }
  }
}
if (!customElements.get("hello-fairy-studio-panel"))
  customElements.define("hello-fairy-studio-panel", HelloFairyStudioPanel);
