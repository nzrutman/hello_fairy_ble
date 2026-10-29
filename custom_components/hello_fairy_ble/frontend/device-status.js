/** Device reports and upload history, kept distinct from pixel readback.
 * Generated with aurora@aurora-smart-home (ha-integration-dev skill)
 * https://github.com/tonylofgren/aurora-smart-home */
import { pixelCss } from "./editor.js?v=2.0.0";
const esc = (s) =>
  String(s).replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
const when = (s) => (s ? new Date(s).toLocaleString() : "No report yet");
class DeviceStatus extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._devices = [];
    this._errors = {};
  }
  set externalBusy(value) {
    this._externalBusy = Boolean(value);
    this._render();
  }
  set hass(h) {
    this._hass = h;
  }
  set devices(devices) {
    this._devices = devices;
    this._render();
  }
  async refreshSnapshots() {
    if (!this._hass) return;
    try {
      const result = await this._hass.callWS({
        type: "hello_fairy_ble/studio/devices",
      });
      this._devices = this._devices.map((d) => ({
        ...d,
        snapshot: result.curtains.find((c) => c.address === d.address)
          ?.snapshot,
      }));
      this._render();
    } catch {
      /* Retain the explicitly timestamped history if the UI disconnects. */
    }
  }
  async _read() {
    if (this._busy || this._externalBusy || !this._hass) return;
    this._busy = true;
    this._errors = {};
    this.dispatchEvent(
      new CustomEvent("studio-busy", {
        detail: { busy: true },
        bubbles: true,
        composed: true,
      }),
    );
    this._render();
    try {
      for (const d of this._devices) {
        try {
          d.snapshot = await this._hass.callWS({
            type: "hello_fairy_ble/studio/read_status",
            address: d.address,
          });
        } catch (e) {
          this._errors[d.address] = e.message || String(e);
        }
      }
    } finally {
      this._busy = false;
      this._render();
      this.dispatchEvent(
        new CustomEvent("studio-busy", {
          detail: { busy: false },
          bubbles: true,
          composed: true,
        }),
      );
    }
  }
  _render() {
    const wasOpen = this.shadowRoot.querySelector("details")?.open || false;
    this.shadowRoot.innerHTML = `<style>:host{display:block;margin:0 0 18px;color:var(--primary-text-color,#172536);font:14px/1.5 system-ui}*{box-sizing:border-box}details{background:var(--card-background-color,#fff);border:1px solid var(--divider-color,#dce5e7);border-radius:14px;padding:14px 18px}summary{cursor:pointer;min-height:32px;font-weight:650}button{font:inherit;min-height:44px;padding:8px 14px;border:1px solid var(--divider-color,#dce5e7);border-radius:8px;background:var(--card-background-color,#fff);color:inherit;cursor:pointer}button:focus-visible{outline:3px solid #3998df}p{margin:8px 0;color:var(--secondary-text-color,#526373)}.list{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,260px),1fr));gap:12px}.device{border-top:1px solid var(--divider-color,#dce5e7);padding-top:12px}.history{display:flex;gap:8px;flex-wrap:wrap}canvas{width:80px;height:80px;image-rendering:pixelated;background:#09111e;border-radius:5px}small{display:block;color:var(--secondary-text-color,#526373)}.error{color:var(--error-color,#b42318)}.note{max-width:80ch}</style><details><summary>Device status &amp; last sent</summary><p class="note">Read status asks the curtain for its power and mode. Its full pixel image is not available through the verified readback commands. Pictures below show upload history, not a live view.</p><button id="read" ${this._busy || this._externalBusy ? "disabled" : ""}>${this._busy ? "Reading status…" : "Read device status"}</button><div class="list">${this._devices
      .map((d) => {
        const s = d.snapshot || {},
          r = s.reported,
          u = s.last_upload,
          settings = s.last_playback;
        const mode = r
          ? r.mode === 1
            ? "Solid color"
            : r.mode === 2
              ? `Scene ${r.scene ?? "unknown"}`
              : r.mode === 3
                ? "Music"
                : `Mode ${r.mode}`
          : "Unknown";
        return `<section class="device"><strong>${esc(d.name)}</strong><p>${r ? `Reported: ${r.power ? "On" : "Off"} · ${esc(mode)}${r.brightness_percent !== undefined ? " · " + r.brightness_percent + "% brightness" : ""}` : "No device status report yet."}</p><small>${r ? "Device report: " + esc(when(r.received_at)) : ""}</small>${this._errors[d.address] ? `<p class="error">${esc(this._errors[d.address])}</p>` : ""}${u ? `<p>Last sent: ${u.kind === "animation" ? "two-picture animation" : "picture"}</p><div class="history">${u.frames.map((_, i) => `<canvas data-address="${esc(d.address)}" data-index="${i}" aria-label="Last sent picture ${i + 1}"></canvas>`).join("")}</div><small>Upload completed: ${esc(when(u.sent_at))}. Display may have changed since.</small>` : "<small>No upload history in this HA session.</small>"}${settings ? `<small>Last control sent: ${esc(settings.movement.replaceAll("_", " "))}, speed ${settings.speed}%, brightness ${settings.brightness}%. Not device readback.</small>` : ""}</section>`;
      })
      .join("")}</div></details>`;
    this.shadowRoot.querySelector("details").open = wasOpen;
    this.shadowRoot.getElementById("read").onclick = () => this._read();
    for (const c of this.shadowRoot.querySelectorAll("canvas")) {
      const u = this._devices.find((d) => d.address === c.dataset.address)
        ?.snapshot?.last_upload;
      const f = u?.frames[Number(c.dataset.index)];
      if (!f || f.length !== 400) continue;
      c.width = 20;
      c.height = 20;
      const ctx = c.getContext("2d");
      f.forEach((p, i) => {
        ctx.fillStyle = p === 254 ? "#09111e" : pixelCss(p);
        ctx.fillRect(i % 20, Math.floor(i / 20), 1, 1);
      });
    }
  }
}
if (!customElements.get("hello-fairy-device-status"))
  customElements.define("hello-fairy-device-status", DeviceStatus);
