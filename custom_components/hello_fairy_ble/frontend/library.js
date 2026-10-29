/** Saved designs and HA-owned playlists (ha-integration-dev skill).
 * https://github.com/tonylofgren/aurora-smart-home
 */
const esc = (s) =>
  String(s).replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
const active = (s) =>
  ["uploading", "holding", "pausing", "paused", "stopping", "clock"].includes(
    s?.state,
  );
const normalize = (data) => {
  const result = structuredClone(data);
  result.designs ||= [];
  result.playlists ||= [];
  result.favorites ||= [];
  result.layouts ||= [];
  result.playlist ||= { items: [], loop: false };
  result.playlist.items ||= [];
  result.status ||= { state: "stopped", message: "Playback stopped" };
  return result;
};

export class HelloFairyDesignLibrary extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this.addresses = [];
    this._data = null;
    this._busy = false;
    this._editorBusy = false;
    this._dirty = false;
    this._revision = 0;
  }
  connectedCallback() {
    this._render();
    if (this._hass) this.refresh();
  }
  disconnectedCallback() {
    clearTimeout(this._timer);
    this._timer = null;
  }
  set hass(value) {
    const first = !this._hass;
    this._hass = value;
    if (first && this.isConnected) this.refresh();
  }
  set editorBusy(value) {
    this._editorBusy = value;
    this._buttons();
  }
  get running() {
    return active(this._data?.status);
  }
  async _request(action, payload = {}) {
    return this._hass.callWS({
      type: "hello_fairy_ble/studio/library",
      action,
      payload,
    });
  }
  async refresh() {
    if (!this._hass || this._busy || !this.isConnected) return;
    clearTimeout(this._timer);
    const revision = this._revision;
    try {
      // Full frames are read once on opening and after explicit mutations.
      // Background polls fetch only compact playback status.
      let next = await this._request(this._data ? "status" : "get");
      if (this._busy || revision !== this._revision) return;
      if (
        !next.designs &&
        next.library_revision &&
        next.library_revision !== this._data?.library_revision &&
        !this._dirty
      ) {
        next = await this._request("get");
        if (this._busy || revision !== this._revision) return;
      }
      if (next.designs && (!this._data || !this._dirty)) {
        this._data = normalize(next);
        this._list();
      } else {
        this._data.status = next.status;
        if (next.orientations) this._data.orientations = next.orientations;
      }
      this._updated();
      this._status();
    } catch (e) {
      this._message(`Library unavailable: ${e.message || e}`);
    } finally {
      this._buttons();
      if (this.isConnected)
        this._timer = setTimeout(
          () => this.refresh(),
          this.running ? 2000 : 10000,
        );
    }
  }
  _render() {
    if (this._$) return;
    this.shadowRoot.innerHTML = `<style>
    :host{display:block;margin-top:20px;color:var(--primary-text-color,#172536);font:14px/1.5 system-ui}*{box-sizing:border-box}section{background:var(--card-background-color,#fff);border:1px solid var(--divider-color,#dce5e7);border-radius:14px;padding:18px}h2{margin:0 0 8px;font-size:20px}h3{font-size:16px;margin:18px 0 8px}p{margin:8px 0;color:var(--secondary-text-color,#526373)}.tools,.row{display:flex;gap:8px;align-items:center;flex-wrap:wrap}.row{border-bottom:1px solid var(--divider-color,#dce5e7);padding:10px 0}.name{flex:1;min-width:160px}.name small{display:block;color:var(--secondary-text-color,#526373)}button,input{font:inherit;color:inherit;min-height:44px;border:1px solid var(--divider-color,#cdd8db);border-radius:8px;background:var(--card-background-color,#fff);padding:8px 10px}button{cursor:pointer}button:disabled{opacity:.45;cursor:default}button:focus-visible,input:focus-visible{outline:3px solid #3998df;outline-offset:2px}input[type=text]{flex:1;min-width:160px}input[type=number]{width:100px}label{display:inline-flex;gap:8px;align-items:center}#message{color:var(--error-color,#b42318)}#play-status{font-weight:600}#stop{border-color:var(--error-color,#b42318)}canvas{width:80px;height:40px;image-rendering:pixelated;background:#0b1424;border-radius:4px}.muted{font-size:12px}#repeat{width:20px;height:20px} @media(max-width:500px){section{padding:12px}.row .name{min-width:120px}button{padding:8px}canvas{width:60px;height:40px}}
    </style><section><h2>Design library &amp; playlist</h2><p>Save designs in Home Assistant, then play them in order. Playback continues after you close this page.</p>
    <div class="tools"><input id="name" type="text" maxlength="80" aria-label="Design name" placeholder="Name your current design"><button id="save-design">Save current design</button></div>
    <p class="muted">Saving or opening a design does not change the lights. Designs can be used on any matching curtain layout.</p><div id="designs"></div>
    <h3>Favorite scenes</h3><p class="muted">Star a design to create an HA scene button using the curtains currently selected above. Recall uses those saved curtains, even if your editor selection changes.</p><div id="favorites"></div>
    <h3>Playlists</h3><div class="tools"><select id="playlist-select" aria-label="Saved playlist"></select><button id="new-playlist">New playlist</button><button id="delete-playlist">Delete playlist</button></div><div class="tools"><input id="playlist-name" maxlength="80" aria-label="Playlist name" placeholder="Playlist name"></div><p>Each timer starts after all curtains finish uploading. Allow at least 10 seconds per design, plus upload time.</p><div id="steps"></div>
    <div class="tools"><label><input id="repeat" type="checkbox">Repeat forever</label><label>Cycles <input id="repeat-count" type="number" min="1" max="100" value="1"></label><label><input id="shuffle" type="checkbox">Shuffle each cycle</label><label>Finish with <select id="end-design" aria-label="Final design"></select></label></div>
    <div class="tools"><button id="save-playlist">Save playlist</button><button id="start">Start on selected curtains</button><button id="previous">Previous design</button><button id="next">Next design</button><button id="pause">Pause playlist</button><button id="stop">Stop playback</button></div>
    <p id="play-status" role="status" aria-live="polite">Loading library…</p><p class="muted">Stop finishes the current curtain upload and leaves the last design displayed. It does not stop that design’s native movement. Playback will not resume automatically after a Home Assistant restart.</p><p id="message" role="alert"></p></section>`;
    this.shadowRoot.querySelector("style").textContent +=
      "select{font:inherit;max-width:100%;min-height:44px;background:var(--card-background-color,#fff);color:inherit;border:1px solid var(--divider-color,#cdd8db);border-radius:8px;padding:8px}input[type=checkbox]{width:20px;height:20px}.tools{margin:8px 0}";
    const extras = document.createElement("div");
    extras.innerHTML = `<h3>Clock &amp; notifications</h3><p class="muted">These use complete picture uploads on the selected curtains. Clock updates are at least one minute apart. They replace current playback; this is not a live pixel readback.</p><div class="tools"><label>Text color <select id="message-color"><option value="0">Red</option><option value="30">Yellow</option><option value="60">Green</option><option value="90">Cyan</option><option value="120">Blue</option><option value="150">Pink</option><option value="255" selected>White</option></select></label><label>Background <select id="message-background"><option value="254">Off</option><option value="0">Red</option><option value="120">Blue</option></select></label></div><div class="tools"><input id="notification-text" maxlength="160" aria-label="Notification text" placeholder="Short message"><label>Icon <select id="notification-icon"><option value="none">None</option><option value="bell">Bell</option><option value="heart">Heart</option><option value="door">Door</option></select></label><label>Seconds per page <input id="notification-seconds" type="number" value="30" min="10" max="86400"></label><label>Then display <select id="restore-design" aria-label="Design after notification"></select></label><button id="show-message">Show notification</button></div><div class="tools"><label>Clock <select id="clock-format"><option value="24h">24 hour</option><option value="12h">12 hour (no AM/PM)</option></select></label><label>Update seconds <input id="clock-interval" type="number" value="60" min="60" max="86400"></label><button id="start-clock">Start clock</button></div><p class="muted">Long messages use several pages; each page holds for the chosen duration after upload. Supports letters, numbers, spaces and : - . ! ?. A notification leaves its last page displayed unless you choose a saved design afterward. Stop playback also stops clock updates.</p>`;
    this.shadowRoot.querySelector("section").append(extras);
    const automation = document.createElement("details");
    automation.id = "automation-details";
    automation.innerHTML =
      '<summary>Use in Home Assistant automations</summary><p>Favorites create Home Assistant button entities. Use the button action to recall a favorite. For explicit playlist or design actions, use the IDs below.</p><div id="automation-list" style="overflow-wrap:anywhere"></div>';
    this.shadowRoot.querySelector("section").append(automation);
    const finishing = document.createElement("details");
    finishing.id = "library-tools";
    finishing.innerHTML = `<summary>Curtain layouts &amp; library backup</summary><h3>Saved curtain layouts</h3><p class="muted">Remember the selected curtains in left-to-right order. Applying a layout changes the editor selection; it sends nothing to the lights.</p><div class="tools"><input id="layout-name" maxlength="80" aria-label="Curtain layout name" placeholder="Name the current curtain layout"><button id="save-layout">Save selected curtains</button></div><div id="layouts"></div><h3>Complete library backup</h3><p class="muted">Includes designs, playlists, favorites, orientations and curtain layouts. Backups contain private Bluetooth device addresses: keep the file private. The current unsaved editor picture is not included.</p><div class="tools"><button id="export-library">Download library backup</button><label>Import mode <select id="import-mode"><option value="merge">Merge with library</option><option value="replace">Replace entire library</option></select></label><button id="import-library">Choose backup to import</button><input id="import-file" type="file" accept="application/json,.json" hidden></div><p class="muted">Import validates the complete file before asking you to confirm. Stop playback first. Importing never uploads to the curtains.</p>`;
    this.shadowRoot.querySelector("section").append(finishing);
    this._$ = (id) => this.shadowRoot.getElementById(id);
    this._$("save-layout").onclick = () => this._saveLayout();
    this._$("export-library").onclick = () => this._exportLibrary();
    this._$("import-library").onclick = () => this._$("import-file").click();
    this._$("import-file").onchange = async () => {
      const file = this._$("import-file").files[0];
      this._$("import-file").value = "";
      if (file) await this._importLibrary(file);
    };
    this._$("save-design").onclick = () => this._saveDesign();
    this._$("save-playlist").onclick = () => this._savePlaylist();
    this._$("start").onclick = () => this._start();
    this._$("stop").onclick = () => {
      if (this._busy) this._stopQueued = true;
      else this._action("stop");
    };
    this._$("pause").onclick = () =>
      this._action(this._data.status.state === "paused" ? "resume" : "pause");
    this._$("previous").onclick = () => this._action("previous");
    this._$("next").onclick = () => this._action("next");
    this._$("playlist-select").onchange = () => this._selectPlaylist();
    this._$("new-playlist").onclick = () => this._newPlaylist();
    this._$("delete-playlist").onclick = () => {
      if (
        window.confirm(
          this._dirty
            ? "Delete this saved playlist and discard its unsaved playlist changes? Designs will remain in your library."
            : "Delete this saved playlist? Designs will remain in your library.",
        )
      )
        this._action("delete_playlist", {
          playlist_id: this._data.selected_playlist_id,
        });
    };
    this._$("playlist-name").oninput = () => {
      this._dirty = true;
      this._buttons();
    };
    for (const id of ["repeat-count", "shuffle", "end-design"])
      this._$(id).onchange = () => {
        Object.assign(this._data.playlist, {
          repeat_count: Number(this._$("repeat-count").value),
          shuffle: this._$("shuffle").checked,
          end_design_id: this._$("end-design").value || null,
        });
        this._dirty = true;
        this._buttons();
      };
    this._$("show-message").onclick = () => this._showMessage();
    this._$("start-clock").onclick = () => this._clock();
    this._$("repeat").onchange = () => {
      this._data.playlist.loop = this._$("repeat").checked;
      this._dirty = true;
      this._buttons();
    };
    this._buttons();
  }
  _message(text) {
    if (this._$) this._$("message").textContent = text;
  }
  _updated() {
    this.dispatchEvent(
      new CustomEvent("studio-library-updated", {
        bubbles: true,
        composed: true,
        detail: {
          orientations: this._data?.orientations || {},
          layouts: this._data?.layouts || [],
          status: this._data?.status,
        },
      }),
    );
  }
  _list() {
    if (!this._data || !this._$) return;
    this._$("automation-list").innerHTML = [
      ...this._data.playlists.map(
        (p) => `<p>Playlist ${esc(p.name)}: <code>${esc(p.id)}</code></p>`,
      ),
      ...this._data.designs.map(
        (d) => `<p>Design ${esc(d.name)}: <code>${esc(d.id)}</code></p>`,
      ),
    ].join("");
    this._$("designs").innerHTML = this._data.designs.length
      ? this._data.designs
          .map(
            (d) =>
              `<div class="row"><canvas data-thumb="${esc(d.id)}" aria-label="${esc(d.name)} preview"></canvas><span class="name">${esc(d.name)}<small>${d.design.width} × 20 · ${d.design.kind === "animation" ? "Two-picture animation" : "Picture"}</small></span><button data-open="${esc(d.id)}">Open</button><button data-add="${esc(d.id)}">Add to playlist</button><button data-star="${esc(d.id)}" aria-label="Favorite ${esc(d.name)}" aria-pressed="${this._data.favorites.some((f) => f.design_id === d.id)}">${this._data.favorites.some((f) => f.design_id === d.id) ? "★ Unstar" : "☆ Favorite"}</button><button data-delete="${esc(d.id)}" aria-label="Delete ${esc(d.name)}">Delete</button></div>`,
          )
          .join("")
      : "<p>No saved designs yet. Create a design above, give it a name, then save it here.</p>";
    for (const c of this.shadowRoot.querySelectorAll("[data-thumb]")) {
      const d = this._data.designs.find((d) => d.id === c.dataset.thumb).design;
      c.width = d.width;
      c.height = 20;
      const ctx = c.getContext("2d");
      d.frames[0].forEach((v, i) => {
        ctx.fillStyle =
          v === 254 ? "#0b1424" : v === 255 ? "#fff" : `hsl(${v * 2} 100% 50%)`;
        ctx.fillRect(i % d.width, Math.floor(i / d.width), 1, 1);
      });
    }
    for (const b of this.shadowRoot.querySelectorAll("[data-open]"))
      b.onclick = () => this._open(b.dataset.open);
    for (const b of this.shadowRoot.querySelectorAll("[data-add]"))
      b.onclick = () => {
        if (this._data.playlist.items.length >= 50)
          return this._message("The playlist can hold 50 steps.");
        this._data.playlist.items.push({
          design_id: b.dataset.add,
          seconds: 30,
        });
        this._dirty = true;
        this._steps();
      };
    for (const b of this.shadowRoot.querySelectorAll("[data-delete]"))
      b.onclick = async () => {
        const d = this._data.designs.find((d) => d.id === b.dataset.delete);
        if (this._dirty && !(await this._savePlaylist())) return;
        if (window.confirm(`Delete “${d.name}” from the library?`))
          this._action("delete_design", { design_id: d.id });
      };
    this._playlistOptions();
    this._layouts();
    this._favorites();
    this._steps();
  }
  _steps() {
    this._$("steps").innerHTML =
      this._data.playlist.items
        .map((step, i) => {
          const d = this._data.designs.find((d) => d.id === step.design_id);
          return `<div class="row"><span class="name">${i + 1}. ${esc(d?.name || "Missing design")}</span><label>Seconds <input data-seconds="${i}" aria-label="Seconds for step ${i + 1}" type="number" min="10" max="86400" step="1" value="${step.seconds}"></label><button data-up="${i}" aria-label="Move step ${i + 1} up" ${i === 0 ? "disabled" : ""}>↑</button><button data-down="${i}" aria-label="Move step ${i + 1} down" ${i === this._data.playlist.items.length - 1 ? "disabled" : ""}>↓</button><button data-remove="${i}" aria-label="Remove step ${i + 1}">Remove</button></div>`;
        })
        .join("") || "<p>Add a library design to build your playlist.</p>";
    this._$("repeat").checked = this._data.playlist.loop;
    for (const input of this.shadowRoot.querySelectorAll("[data-seconds]"))
      input.oninput = () => {
        this._data.playlist.items[Number(input.dataset.seconds)].seconds =
          Number(input.value);
        this._dirty = true;
        this._buttons();
      };
    for (const b of this.shadowRoot.querySelectorAll(
      "[data-up],[data-down],[data-remove]",
    ))
      b.onclick = () => {
        const list = this._data.playlist.items;
        if (b.dataset.remove !== undefined)
          list.splice(Number(b.dataset.remove), 1);
        else {
          const i = Number(b.dataset.up ?? b.dataset.down),
            j = i + (b.dataset.up !== undefined ? -1 : 1);
          [list[i], list[j]] = [list[j], list[i]];
        }
        this._dirty = true;
        this._steps();
      };
    this._buttons();
  }
  _playlistOptions() {
    const data = this._data;
    this._$("playlist-select").innerHTML = data.playlists.length
      ? data.playlists
          .map((p) => `<option value="${esc(p.id)}">${esc(p.name)}</option>`)
          .join("")
      : '<option value="">Current playlist</option>';
    this._$("playlist-select").value = data.selected_playlist_id || "";
    this._$("playlist-name").value =
      data.playlist.name ||
      data.playlists.find((p) => p.id === data.selected_playlist_id)?.name ||
      "";
    this._$("repeat-count").value = data.playlist.repeat_count || 1;
    this._$("shuffle").checked = Boolean(data.playlist.shuffle);
    for (const id of ["end-design", "restore-design"]) {
      const previous = this._$(id).value;
      this._$(id).innerHTML =
        '<option value="">Leave last picture</option>' +
        data.designs
          .map((d) => `<option value="${esc(d.id)}">${esc(d.name)}</option>`)
          .join("");
      this._$(id).value =
        id === "end-design" ? data.playlist.end_design_id || "" : previous;
    }
  }
  _favorites() {
    this._$("favorites").innerHTML = this._data.favorites.length
      ? this._data.favorites
          .map((f) => {
            const design = this._data.designs.find((d) => d.id === f.design_id);
            return design
              ? `<button data-recall="${esc(f.design_id)}" title="${esc((f.addresses || []).join(", "))}">${esc(design.name)} · ${(f.addresses || []).length} curtain(s)</button>`
              : "";
          })
          .join(" ")
      : "<p>No favorites yet. Use ☆ Favorite beside a saved design.</p>";
    for (const b of this.shadowRoot.querySelectorAll("[data-star]"))
      b.onclick = async () => {
        if (this._dirty && !(await this._savePlaylist())) return;
        const enabled = !this._data.favorites.some(
          (f) => f.design_id === b.dataset.star,
        );
        if (enabled && !this.addresses.length)
          return this._message(
            "Choose curtains above before saving a favorite.",
          );
        const design = this._data.designs.find((d) => d.id === b.dataset.star);
        if (enabled && design.design.width !== this.addresses.length * 20)
          return this._message(
            `Choose ${design.design.width / 20} curtain(s) above to match this favorite’s width.`,
          );
        await this._action("set_favorite", {
          design_id: b.dataset.star,
          addresses: this.addresses.slice(),
          enabled,
        });
      };
    for (const b of this.shadowRoot.querySelectorAll("[data-recall]"))
      b.onclick = async () => {
        if (this._dirty && !(await this._savePlaylist())) return;
        if (
          window.confirm(
            "Display this favorite on its saved curtains? This replaces current playback.",
          )
        )
          await this._action("recall", { design_id: b.dataset.recall });
      };
  }
  async _selectPlaylist() {
    const id = this._$("playlist-select").value;
    if (this._dirty && !(await this._savePlaylist())) {
      this._$("playlist-select").value = this._data.selected_playlist_id || "";
      return;
    }
    await this._action("select_playlist", { playlist_id: id });
  }
  async _newPlaylist() {
    if (this._dirty && !(await this._savePlaylist())) return;
    const name = window.prompt("Name the new playlist:");
    if (!name?.trim()) return;
    await this._action("save_playlist", {
      name: name.trim(),
      playlist_id: null,
      playlist: {
        items: [],
        loop: false,
        shuffle: false,
        repeat_count: 1,
        end_design_id: null,
      },
    });
  }
  _validNumber(id) {
    const field = this._$(id);
    if (!field.reportValidity()) return null;
    const value = Number(field.value);
    return Number.isInteger(value) ? value : null;
  }
  async _showMessage() {
    const seconds = this._validNumber("notification-seconds");
    if (seconds === null)
      return this._message("Enter a whole number of seconds.");
    const text = this._$("notification-text").value.trim();
    const icon = this._$("notification-icon").value;
    if (!text && icon === "none")
      return this._message("Enter a message or choose an icon.");
    if (this._dirty && !(await this._savePlaylist())) return;
    await this._action("show_message", {
      addresses: this.addresses.slice(),
      text,
      icon,
      duration: seconds,
      color_byte: Number(this._$("message-color").value),
      background_byte: Number(this._$("message-background").value),
      ...(this._$("restore-design").value
        ? { restore_design_id: this._$("restore-design").value }
        : {}),
    });
  }
  async _clock() {
    const interval = this._validNumber("clock-interval");
    if (interval === null)
      return this._message(
        "Clock updates require a whole number of seconds, at least 60.",
      );
    if (this._dirty && !(await this._savePlaylist())) return;
    await this._action("start_clock", {
      addresses: this.addresses.slice(),
      format: this._$("clock-format").value,
      interval,
      color_byte: Number(this._$("message-color").value),
      background_byte: Number(this._$("message-background").value),
    });
  }
  _buttons() {
    if (!this._$) return;
    const locked =
      this._busy || this.running || this._editorBusy || !this._data;
    for (const el of this.shadowRoot.querySelectorAll("button,input,select"))
      el.disabled = locked;
    this._$("stop").disabled = !this.running;
    const status = this._data?.status || {};
    const playlist = (status.kind || status.mode) === "playlist";
    this._$("pause").textContent =
      status.state === "paused"
        ? "Resume playlist"
        : status.pause_requested || status.state === "pausing"
          ? "Pause requested…"
          : "Pause playlist";
    this._$("pause").disabled =
      this._busy ||
      this._editorBusy ||
      !playlist ||
      !["uploading", "holding", "paused"].includes(status.state) ||
      status.pause_requested;
    this._$("save-layout").disabled = locked || !this.addresses.length;
    this._$("export-library").disabled = this._busy || !this._data;

    const steps = this._data?.playlist.items || [];
    for (const b of this.shadowRoot.querySelectorAll("[data-up]"))
      b.disabled = locked || Number(b.dataset.up) === 0;
    for (const b of this.shadowRoot.querySelectorAll("[data-down]"))
      b.disabled = locked || Number(b.dataset.down) === steps.length - 1;
    this._$("start").disabled =
      locked || !steps.length || !this.addresses?.length || this.disabled;
    this._$("save-design").disabled = locked || !this.editor;
    this._$("repeat-count").disabled = locked || this._$("repeat").checked;
    this._$("delete-playlist").disabled =
      locked || !this._data?.selected_playlist_id;
    const transportLocked =
      this._busy || this._editorBusy || !this._data || this.disabled;
    for (const id of ["next", "previous"])
      this._$(id).disabled =
        transportLocked ||
        !this.running ||
        this._data?.status?.state !== "holding" ||
        (this._data?.status?.kind || this._data?.status?.mode) !== "playlist";
    for (const id of ["show-message", "start-clock"])
      this._$(id).disabled = locked || !this.addresses?.length || this.disabled;
    for (const b of this.shadowRoot.querySelectorAll("[data-recall]"))
      b.disabled = transportLocked;
    this._$("save-playlist").textContent = this._dirty
      ? "Save playlist changes"
      : "Save playlist";
  }
  _status() {
    const s = this._data.status;
    const detail = [];
    if (s.design_name) detail.push(s.design_name);
    if (Number.isInteger(s.cycle)) detail.push(`Cycle ${s.cycle}`);
    if (
      Number.isInteger(s.completed_curtains) &&
      Number.isInteger(s.total_curtains)
    )
      detail.push(
        `${s.completed_curtains} of ${s.total_curtains} curtains completed`,
      );
    if (
      Number.isFinite(s.hold_remaining_seconds) &&
      ["holding", "paused"].includes(s.state)
    )
      detail.push(
        `${Math.ceil(Math.max(0, s.hold_remaining_seconds))}s hold remaining`,
      );
    if (s.state === "paused")
      detail.push(
        "No new uploads; the displayed design and native movement continue",
      );
    if (s.state === "pausing" || s.pause_requested)
      detail.push("Pauses after the current upload finishes");
    this._$("play-status").textContent =
      (s.index !== undefined
        ? `Step ${s.index + 1}${s.total ? ` of ${s.total}` : ""}: `
        : "") +
      (s.message || "Playback stopped") +
      (detail.length ? " · " + detail.join(" · ") : "") +
      (this.running ? " · Runs in Home Assistant" : "");
  }
  async _action(action, payload = {}) {
    if (this._busy) return false;
    this._revision++;
    this._busy = true;
    this._buttons();
    this._message("");
    try {
      this._data = normalize(await this._request(action, payload));
      this._updated();
      this._dirty = false;
      this._list();
      this._status();
      return true;
    } catch (e) {
      this._message(e.message || String(e));
      return false;
    } finally {
      this._busy = false;
      this._buttons();
      if (this._stopQueued) {
        this._stopQueued = false;
        this._action("stop");
      }
      clearTimeout(this._timer);
      if (this.isConnected)
        this._timer = setTimeout(() => this.refresh(), 2000);
    }
  }
  _layouts() {
    this._$("layouts").innerHTML = this._data.layouts.length
      ? this._data.layouts
          .map(
            (layout) =>
              `<div class="row"><span class="name">${esc(layout.name)}<small>${layout.addresses.length} curtain(s), in saved order</small></span><button data-layout="${esc(layout.id)}">Apply layout</button><button data-delete-layout="${esc(layout.id)}" aria-label="Delete layout ${esc(layout.name)}">Delete</button></div>`,
          )
          .join("")
      : "<p>No saved curtain layouts yet.</p>";
    for (const button of this.shadowRoot.querySelectorAll("[data-layout]"))
      button.onclick = () => {
        const layout = this._data.layouts.find(
          (item) => item.id === button.dataset.layout,
        );
        this.dispatchEvent(
          new CustomEvent("studio-apply-layout", {
            bubbles: true,
            composed: true,
            detail: { addresses: layout.addresses.slice(), name: layout.name },
          }),
        );
      };
    for (const button of this.shadowRoot.querySelectorAll(
      "[data-delete-layout]",
    ))
      button.onclick = async () => {
        if (this._dirty && !(await this._savePlaylist())) return;
        const layout = this._data.layouts.find(
          (item) => item.id === button.dataset.deleteLayout,
        );
        if (window.confirm(`Delete saved curtain layout “${layout.name}”?`))
          await this._action("delete_layout", { layout_id: layout.id });
      };
  }
  async _saveLayout() {
    if (this._busy || this.running || this._editorBusy) return;
    const name = this._$("layout-name").value.trim();
    if (!name || !this.addresses.length)
      return this._message("Choose curtains above and give the layout a name.");
    if (this._dirty && !(await this._savePlaylist())) return;
    const existing = this._data.layouts.find((layout) => layout.name === name);
    if (existing && !window.confirm(`Replace saved curtain layout “${name}”?`))
      return;
    if (
      await this._action("save_layout", {
        name,
        addresses: this.addresses.slice(),
        ...(existing ? { layout_id: existing.id } : {}),
      })
    )
      this._message("Curtain layout saved. Nothing was sent to the lights.");
  }
  async _exportLibrary() {
    if (this._busy || !this._data) return;
    this._busy = true;
    this._buttons();
    this._message("");
    try {
      const result = await this._request("export_library");
      const url = URL.createObjectURL(
        new Blob([JSON.stringify(result.backup, null, 2)], {
          type: "application/json",
        }),
      );
      const link = document.createElement("a");
      link.href = url;
      link.download = `hello-fairy-library-${new Date().toISOString().slice(0, 10)}.json`;
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      this._message(
        "Library backup downloaded. Unsaved editor and playlist changes are not included; keep the file private.",
      );
    } catch (error) {
      this._message(error.message || String(error));
    } finally {
      this._busy = false;
      this._buttons();
      if (this._stopQueued) {
        this._stopQueued = false;
        this._action("stop");
      }
    }
  }
  _importBusy(busy) {
    this.dispatchEvent(
      new CustomEvent("studio-library-busy", {
        bubbles: true,
        composed: true,
        detail: { busy },
      }),
    );
  }
  async _importLibrary(file) {
    if (this._busy || this.running || this._editorBusy)
      return this._message(
        "Stop playback and wait for the editor before importing.",
      );
    if (file.size > 4 * 1024 * 1024)
      return this._message("Choose a library backup smaller than 4 MB.");
    const mode = this._$("import-mode").value;
    this._revision++;
    this._busy = true;
    this._importBusy(true);
    this._buttons();
    this._message("");
    try {
      let backup;
      try {
        backup = JSON.parse(await file.text());
      } catch {
        throw new Error(
          "This file is not valid JSON. Choose a Hello Fairy library backup.",
        );
      }
      const summary = await this._request("validate_import", { backup, mode });
      const counts = summary.counts || summary;
      const description = [
        "designs",
        "playlists",
        "favorites",
        "orientations",
        "layouts",
      ]
        .filter((key) => Number.isInteger(counts[key]))
        .map((key) => `${counts[key]} ${key}`)
        .join(", ");
      if (
        !window.confirm(
          `${mode === "replace" ? "Replace your entire saved library" : "Merge this backup into your library"}${description ? ` (${description})` : ""}?${this._dirty ? " Unsaved playlist changes will be discarded." : ""} The current editor picture is kept. Nothing will be sent to the lights.`,
        )
      )
        return;
      this._data = normalize(
        await this._request("import_library", { backup, mode }),
      );
      this._dirty = false;
      this._list();
      this._updated();
      this._status();
      this._message(
        "Library imported. The editor picture was kept; nothing was sent to the lights.",
      );
    } catch (error) {
      this._message(error.message || String(error));
    } finally {
      this._busy = false;
      this._importBusy(false);
      this._buttons();
    }
  }
  async _saveDesign() {
    if (!this.editor || this._editorBusy || this.running) return;
    if (this._dirty && !(await this._savePlaylist())) return;
    const name = this._$("name").value.trim();
    if (!name) return this._message("Give your design a name first.");
    const existing = this._data.designs.find((d) => d.name === name);
    if (existing && !window.confirm(`Replace saved design “${name}”?`)) return;
    if (
      await this._action("save_design", {
        name,
        design: this.editor.exportDesign(),
        ...(existing ? { design_id: existing.id } : {}),
      })
    )
      this._message("Design saved in Home Assistant.");
  }
  async _savePlaylist() {
    const count = this._validNumber("repeat-count");
    if (count === null) {
      this._message("Enter a whole number of playlist cycles.");
      return false;
    }
    return this._action("save_playlist", {
      playlist: structuredClone(this._data.playlist),
      ...(this._data.selected_playlist_id
        ? { playlist_id: this._data.selected_playlist_id }
        : {}),
      ...(this._$("playlist-name").value.trim()
        ? { name: this._$("playlist-name").value.trim() }
        : {}),
    });
  }
  async _start() {
    if (await this._savePlaylist())
      await this._action("start", { addresses: this.addresses.slice() });
  }
  async _open(id) {
    if (!this.editor || this._editorBusy || this.running) return;
    const d = this._data.designs.find((d) => d.id === id);
    if (d.design.width !== this.addresses.length * 20)
      return this._message(
        `Choose ${d.design.width / 20} curtain(s) above to open this design.`,
      );
    if (
      !window.confirm(
        "Replace the current editor preview with this saved design?",
      )
    )
      return;
    await this.editor._loadPattern(
      new Blob([JSON.stringify(d.design)], { type: "application/json" }),
    );
    this._$("name").value = d.name;
    this._message(
      "Design opened in the editor. Nothing was sent to the lights.",
    );
  }
}
if (!customElements.get("hello-fairy-design-library"))
  customElements.define("hello-fairy-design-library", HelloFairyDesignLibrary);
