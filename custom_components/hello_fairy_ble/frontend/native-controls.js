/** Device-native controls with explicit inspection and one target per request.
 * Generated with aurora@aurora-smart-home (ha-integration-dev skill)
 * https://github.com/tonylofgren/aurora-smart-home */
const esc = (value) =>
  String(value ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
class NativeControls extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._devices = [];
    this._address = "";
    this._busy = false;
    this._externalBusy = false;
    this._draft = {};
  }
  set hass(value) {
    this._hass = value;
  }
  set externalBusy(value) {
    this._externalBusy = Boolean(value);
    this._render();
  }
  set devices(value) {
    this._remember();
    this._devices = Array.isArray(value) ? value : [];
    if (!this._devices.some((d) => d.address === this._address)) {
      this._address = this._devices[0]?.address || "";
      this._draft = {};
    }
    this._render();
  }
  _remember() {
    for (const el of this.shadowRoot.querySelectorAll("[data-field]")) {
      this._draft[el.id] = el.type === "checkbox" ? el.checked : el.value;
    }
  }
  _number(id) {
    return Number(this.shadowRoot.getElementById(id).value);
  }
  _checked(id) {
    return this.shadowRoot.getElementById(id).checked;
  }
  _input(id, label, min, max, value) {
    return `<label>${label}<input data-field id="${id}" type="number" min="${min}" max="${max}" step="1" value="${esc(this._draft[id] ?? value)}" required></label>`;
  }
  _check(id, label, value = false) {
    return `<label class="check"><input data-field id="${id}" type="checkbox" ${(this._draft[id] ?? value) ? "checked" : ""}>${label}</label>`;
  }
  async _send(action, payload = {}) {
    if (this._busy || this._externalBusy || !this._hass || !this._address)
      return;
    const device = this._devices.find((d) => d.address === this._address);
    const native = device?.snapshot?.native || {};
    const gate = {
      music: "music_supported",
      scene_speed: "scene_speed_supported",
      clock_sync: "profile_verified",
      countdown: "profile_verified",
      timer: "timers_supported",
    }[action];
    if (gate && !native[gate]) {
      this._error =
        "Inspect this curtain first. This control is not available for its reported capabilities.";
      this._render();
      return;
    }
    this._remember();
    this._busy = true;
    this._error = "";
    this._message = "";
    this.dispatchEvent(
      new CustomEvent("studio-busy", {
        detail: { busy: true },
        bubbles: true,
        composed: true,
      }),
    );
    this._render();
    try {
      const result = await this._hass.callWS({
        type: "hello_fairy_ble/studio/native",
        address: this._address,
        action,
        payload,
      });
      device.snapshot = { ...device.snapshot, ...result };
      this._message =
        action === "inspect"
          ? "Device capabilities received. This is not a view of its pixels."
          : "Command transmitted. Check the curtain to confirm the result.";
      this.dispatchEvent(
        new CustomEvent("studio-sent", { bubbles: true, composed: true }),
      );
    } catch (e) {
      this._error = e.message || String(e);
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
    this._remember();
    const open = this.shadowRoot.querySelector("details")?.open || false;
    const n =
      this._devices.find((d) => d.address === this._address)?.snapshot
        ?.native || {};
    const blocked = this._busy || this._externalBusy || !this._address;
    const disabled = (supported) => (blocked || !supported ? "disabled" : "");
    const reasons =
      n.unavailable || n.unavailable_reasons || n.unsupported_reasons || {};
    const reasonText =
      typeof reasons === "string"
        ? reasons
        : Array.isArray(reasons)
          ? reasons.join(" · ")
          : Object.values(reasons).join(" · ");
    this.shadowRoot.innerHTML = `<style>
      :host{display:block;margin:0 0 18px;color:var(--primary-text-color,#172536);font:14px/1.5 system-ui}*{box-sizing:border-box}details{background:var(--card-background-color,#fff);border:1px solid var(--divider-color,#dce5e7);border-radius:14px;padding:14px 18px}summary{cursor:pointer;min-height:32px;font-weight:650}p{margin:8px 0;color:var(--secondary-text-color,#526373)}form{margin:12px 0;padding:12px 0;border-top:1px solid var(--divider-color,#dce5e7)}h3{font-size:15px;margin:0 0 8px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,150px),1fr));gap:10px}label{display:grid;gap:4px;min-width:0}input,select,button{font:inherit;color:inherit;background:var(--card-background-color,#fff);border:1px solid var(--divider-color,#dce5e7);border-radius:8px;min-height:44px;padding:8px;max-width:100%;min-width:0}input,select{width:100%}button{cursor:pointer;padding:8px 14px;margin-top:8px}button:disabled,fieldset:disabled{opacity:.55}fieldset{border:0;padding:0;margin:0;min-width:0}.check{display:flex;align-items:center;gap:8px}.check input{width:20px;min-height:24px}.weekdays{display:flex;flex-wrap:wrap;gap:8px}.weekdays label{display:flex;align-items:center;gap:4px}.weekdays input{width:18px;min-height:24px}button:focus-visible,input:focus-visible,select:focus-visible{outline:3px solid #3998df}.error{color:var(--error-color,#b42318)}.message{color:var(--success-color,#237543)}small{display:block;color:var(--secondary-text-color,#526373);overflow-wrap:anywhere}
      </style><details><summary>Native curtain controls · experimental</summary>
      <p>Inspect one curtain to check its capabilities. Changes stop Studio background playback before sending. These controls run on the curtain.</p>
      <label>Curtain<select id="curtain" ${blocked ? "disabled" : ""}>${this._devices.map((d) => `<option value="${esc(d.address)}" ${d.address === this._address ? "selected" : ""}>${esc(d.name)}</option>`).join("")}</select></label>
      <button id="inspect" ${disabled(true)}>${this._busy ? "Working…" : "Inspect capabilities"}</button>
      <p>${n.profile_verified ? "400-LED curtain profile verified." : "Capabilities have not been verified for this curtain."}</p>
      ${reasonText ? `<small>${esc(reasonText)}</small>` : ""}
      <form id="music"><h3>Built-in music response</h3><small>${n.music_supported ? "Uses the curtain’s microphone. Home Assistant does not stream audio." : "Unavailable until the curtain reports compatible music support."}</small><fieldset ${disabled(n.music_supported)}><div class="grid"><label>Pattern<select id="music-mode" data-field>${["Energy", "Rhythm", "Roll", "Spectrum"].map((name, i) => `<option value="${i + 1}" ${Number(this._draft["music-mode"] ?? 1) === i + 1 ? "selected" : ""}>${name}</option>`).join("")}</select></label>${this._input("sensitivity", "Sensitivity (%)", 1, 100, 50)}${this._input("brightness", "Brightness (%)", 1, 100, 100)}${this._input("hue", "Hue (°)", 0, 360, 0)}${this._input("saturation", "Saturation (%)", 0, 100, 100)}</div>${this._check("auto-color", "Automatic colors", true)}<button>Start music response</button></fieldset></form>
      <form id="scene-speed"><h3>Preset speed</h3><fieldset ${disabled(n.scene_speed_supported)}>${this._input("speed", "Speed (%)", 0, 100, 50)}<button>Set preset speed</button></fieldset><small>${n.scene_speed_supported ? "Adjusts the active preset. DIY designs use their own speed control." : "Unavailable until compatible preset-speed support is reported."}</small></form>
      <form id="clock-sync"><h3>Device clock</h3><fieldset ${disabled(n.profile_verified)}><button>Sync curtain clock</button></fieldset><small>The curtain stores a fixed UTC offset. Sync again after a daylight-saving change; Home Assistant schedules handle time-zone changes more reliably.</small></form>
      <form id="countdown"><h3>One-time power countdown</h3><fieldset ${disabled(n.profile_verified)}>${this._input("seconds", "Seconds (0 cancels)", 0, 86400, 600)}${this._check("countdown-power", "Turn on when countdown ends")}<button>Set countdown</button></fieldset></form>
      ${Array.isArray(n.timers) ? `<details class="timer-reports"><summary>Reported device schedule slots</summary>${n.timers.map((t) => `<small>Slot ${esc(t.slot)}: ${esc(String(t.hour).padStart(2, "0"))}:${esc(String(t.minute).padStart(2, "0"))} · ${t.enabled ? "Enabled" : "Disabled"} · ${t.power ? "On" : "Off"} · ${Array.isArray(t.weekdays) && t.weekdays.length ? esc(t.weekdays.map((d) => ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][d - 1] || "?").join(", ")) : "Once"}</small>`).join("")}<small>Times use the reported fixed UTC offset ${esc(n.utc_offset_minutes ?? "unknown")} minutes.</small></details>` : ""}
      ${n.font_report ? `<small>Font capability report: version ${esc(n.font_report.font_protocol_version)}. Native text upload remains unverified.</small>` : ""}
      <form id="timer"><h3>Device schedule · one slot</h3><small>${n.timers_supported ? "Inspect first, then choose the slot to replace. Unchecked days mean a one-time schedule." : "Unavailable until the curtain returns valid timer banks. No schedule is written by inspecting."}</small><fieldset ${disabled(n.timers_supported)}><div class="grid">${this._input("slot", "Slot (0–7)", 0, 7, 0)}${this._input("hour", "Hour (0–23)", 0, 23, 18)}${this._input("minute", "Minute", 0, 59, 0)}</div>${this._check("timer-enabled", "Enable this slot", true)}${this._check("timer-power", "Turn on", true)}<div class="weekdays">${["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].map((day, i) => this._check(`day-${i + 1}`, day)).join("")}</div><button>Replace selected schedule slot</button></fieldset></form>
      <small>Native text upload, stored design management, full pixel readback and synchronized curtains remain unavailable until their protocols are verified for this model.</small>
      <p class="error" role="alert">${esc(this._error)}</p><p class="message" role="status">${esc(this._message)}</p></details>`;
    this.shadowRoot.querySelector("details").open = open;
    this.shadowRoot.getElementById("curtain").onchange = (e) => {
      this._address = e.target.value;
      this._draft = {};
      this._error = "";
      this._message = "";
      this.shadowRoot
        .querySelectorAll("[data-field]")
        .forEach((el) => el.removeAttribute("data-field"));
      this._render();
    };
    this.shadowRoot.getElementById("inspect").onclick = () =>
      this._send("inspect");
    const submit = (id, action, payload) => {
      this.shadowRoot.getElementById(id).onsubmit = (e) => {
        e.preventDefault();
        if (!e.target.reportValidity()) return;
        this._send(action, payload());
      };
    };
    submit("music", "music", () => ({
      mode: this._number("music-mode"),
      auto_color: this._checked("auto-color"),
      sensitivity: this._number("sensitivity"),
      brightness: this._number("brightness"),
      hue: this._number("hue"),
      saturation: this._number("saturation"),
    }));
    submit("scene-speed", "scene_speed", () => ({
      speed: this._number("speed"),
    }));
    submit("clock-sync", "clock_sync", () => ({}));
    submit("countdown", "countdown", () => ({
      seconds: this._number("seconds"),
      power: this._checked("countdown-power"),
    }));
    submit("timer", "timer", () => ({
      slot: this._number("slot"),
      hour: this._number("hour"),
      minute: this._number("minute"),
      power: this._checked("timer-power"),
      enabled: this._checked("timer-enabled"),
      weekdays: [1, 2, 3, 4, 5, 6, 7].filter((day) =>
        this._checked(`day-${day}`),
      ),
    }));
  }
}
if (!customElements.get("hello-fairy-native-controls"))
  customElements.define("hello-fairy-native-controls", NativeControls);
