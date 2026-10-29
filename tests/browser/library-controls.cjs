// Offline saved scene, playlist and occasional upload checks (ha-integration-dev skill).
// https://github.com/tonylofgren/aurora-smart-home
const { chromium } = require("playwright");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const http = require("node:http");
const path = require("node:path");
const assets = path.resolve(
  __dirname,
  "../../custom_components/hello_fairy_ble/frontend",
);
const html = `<!doctype html><meta name="viewport" content="width=device-width,initial-scale=1"><hello-fairy-design-library></hello-fairy-design-library><script type="module">
import '/library.js';window.lib=document.querySelector('hello-fairy-design-library');window.calls=[];window.updates=[];
const picture={kind:'picture',width:20,frames:[Array(400).fill(0)]};
window.state={designs:[{id:'red',name:'Red <script>',design:picture},{id:'blue',name:'Blue',design:{...picture,frames:[Array(400).fill(120)]}}],playlists:[{id:'first',name:'Evening',items:[{design_id:'red',seconds:30}],loop:false,shuffle:false,repeat_count:1,end_design_id:null},{id:'second',name:'Morning',items:[{design_id:'blue',seconds:45}],loop:false,shuffle:false,repeat_count:1,end_design_id:null}],selected_playlist_id:'first',favorites:[],orientations:{'AA:BB:CC:DD:EE:01':{flip_x:true}},status:{state:'stopped',message:'Stopped'}};
state.playlist=state.playlists[0];window.failSave=false;window.libraryEvents=0;
lib.addEventListener('studio-library-updated', e=>{libraryEvents++;updates.push(e.detail)});
lib.addresses=['AA:BB:CC:DD:EE:01'];lib.editor={exportDesign:()=>picture};
lib.hass={callWS:async req=>{calls.push(structuredClone(req));const p=req.payload||{},a=req.action;
if(a==='save_playlist'){if(failSave)throw Error('Simulated save failure');const id=p.playlist_id===null?'new':p.playlist_id||state.selected_playlist_id;const data={...p.playlist,id,name:p.name||'Untitled'};const index=state.playlists.findIndex(x=>x.id===id);if(index>=0)state.playlists[index]=data;else state.playlists.push(data);state.selected_playlist_id=id;state.playlist=data;}
if(a==='select_playlist'){state.selected_playlist_id=p.playlist_id;state.playlist=state.playlists.find(x=>x.id===p.playlist_id);}
if(a==='delete_playlist'){state.playlists=state.playlists.filter(x=>x.id!==p.playlist_id);state.playlist=state.playlists[0];state.selected_playlist_id=state.playlist.id;}
if(a==='set_favorite'){state.favorites=state.favorites.filter(x=>x.design_id!==p.design_id);if(p.enabled)state.favorites.push({design_id:p.design_id,addresses:p.addresses});}
if(a==='start')state.status={state:'holding',kind:'playlist',index:0,total:state.playlist.items.length,message:'Running'};
if(a==='start_clock')state.status={state:'holding',kind:'clock',message:'Clock'};
if(a==='stop')state.status={state:'stopped',message:'Stopped'};
return structuredClone(a==='status'?{status:state.status}:state)}};
</script>`;
const server = http.createServer((req, res) => {
  if (req.url === "/library.js") {
    res.setHeader("Content-Type", "text/javascript");
    res.end(fs.readFileSync(path.join(assets, "library.js")));
  } else {
    res.setHeader("Content-Type", "text/html");
    res.end(html);
  }
});
let browser;
const checks = [];
async function check(name, callback) {
  await callback();
  checks.push(name);
  console.log("PASS", name);
}
(async () => {
  await new Promise((r) => server.listen(0, "127.0.0.1", r));
  browser = await chromium.launch({
    headless: true,
    channel: process.env.PW_CHANNEL || undefined,
  });
  const page = await browser.newPage({
    viewport: { width: 1100, height: 1000 },
  });
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("dialog", async (d) =>
    d.accept(d.type() === "prompt" ? "Weekend" : undefined),
  );
  await page.goto("http://127.0.0.1:" + server.address().port);
  const library = page.locator("hello-fairy-design-library");
  const get = (id) => library.locator("#" + id);
  await get("playlist-name").waitFor();
  await page.waitForFunction(() => lib._data?.designs?.length === 2);
  await check(
    "Opening only reads saved state; names are escaped and orientation metadata is reported",
    async () => {
      assert.deepEqual(await page.evaluate(() => calls.map((x) => x.action)), [
        "get",
      ]);
      assert.equal(await library.locator("script").count(), 0);
      assert.equal(await library.locator('[data-open="red"]').count(), 1);
      assert.equal(
        await page.evaluate(
          () => updates[0].orientations["AA:BB:CC:DD:EE:01"].flip_x,
        ),
        true,
      );
    },
  );
  await check(
    "Background refresh fetches compact status instead of full image frames",
    async () => {
      await page.evaluate(() => lib.refresh());
      assert.equal(await page.evaluate(() => calls.at(-1).action), "status");
      assert.equal(await page.evaluate(() => lib._data.designs.length), 2);
    },
  );
  await check(
    "Playlist options save exact shuffle, finite cycles and final design without starting playback",
    async () => {
      await get("playlist-name").fill("Night <blue>");
      await get("repeat-count").fill("3");
      await get("shuffle").check();
      await get("end-design").selectOption("blue");
      await get("save-playlist").click();
      const saved = await page.evaluate(
        () => calls.findLast((x) => x.action === "save_playlist").payload,
      );
      assert.equal(saved.playlist_id, "first");
      assert.equal(saved.name, "Night <blue>");
      assert.equal(saved.playlist.shuffle, true);
      assert.equal(saved.playlist.repeat_count, 3);
      assert.equal(saved.playlist.end_design_id, "blue");
      assert.ok(
        await page.evaluate(() =>
          calls.every(
            (x) =>
              !["start", "recall", "show_message", "start_clock"].includes(
                x.action,
              ),
          ),
        ),
      );
    },
  );
  await check(
    "Refresh preserves an unsaved draft; changing playlist saves it before selecting",
    async () => {
      await get("playlist-name").fill("Unsaved evening");
      await page.evaluate(() => lib.refresh());
      assert.equal(await get("playlist-name").inputValue(), "Unsaved evening");
      await get("playlist-select").selectOption("second");
      await page.waitForFunction(
        () => lib._data.selected_playlist_id === "second",
      );
      const last = await page.evaluate(() =>
        calls.slice(-2).map((x) => x.action),
      );
      assert.deepEqual(last, ["save_playlist", "select_playlist"]);
      assert.equal(await get("playlist-name").inputValue(), "Morning");
    },
  );
  await check(
    "Failed save prevents switching away from a dirty playlist",
    async () => {
      await get("playlist-name").fill("Draft");
      await page.evaluate(() => (failSave = true));
      await get("playlist-select").selectOption("first");
      await page.waitForFunction(() =>
        lib.shadowRoot
          .getElementById("message")
          .textContent.includes("Simulated"),
      );
      assert.equal(
        await page.evaluate(() => state.selected_playlist_id),
        "second",
      );
      assert.equal(await get("playlist-name").inputValue(), "Draft");
      await page.evaluate(() => (failSave = false));
    },
  );
  await check(
    "Creating and deleting named playlists keeps designs and uses explicit new identifier",
    async () => {
      await get("new-playlist").click();
      await page.waitForFunction(
        () => lib._data.selected_playlist_id === "new",
      );
      const req = await page.evaluate(
        () => calls.findLast((x) => x.action === "save_playlist").payload,
      );
      assert.equal(req.playlist_id, null);
      assert.equal(req.name, "Weekend");
      await get("delete-playlist").click();
      await page.waitForFunction(
        () => !lib._data.playlists.some((x) => x.id === "new"),
      );
      assert.equal(await page.evaluate(() => lib._data.designs.length), 2);
    },
  );
  await check(
    "Favorites store explicit selected targets and recall saved targets without using changed editor selection",
    async () => {
      await library.locator('[data-star="red"]').click();
      await library.locator('[data-recall="red"]').waitFor();
      const fav = await page.evaluate(
        () => calls.findLast((x) => x.action === "set_favorite").payload,
      );
      assert.deepEqual(fav.addresses, ["AA:BB:CC:DD:EE:01"]);
      assert.equal(fav.enabled, true);
      await page.evaluate(() => (lib.addresses = ["AA:BB:CC:DD:EE:02"]));
      await library.locator('[data-recall="red"]').click();
      assert.deepEqual(
        await page.evaluate(
          () => calls.findLast((x) => x.action === "recall").payload,
        ),
        { design_id: "red" },
      );
    },
  );
  await check(
    "Favorites require a matching curtain layout before saving",
    async () => {
      await page.evaluate(
        () => (lib.addresses = ["AA:BB:CC:DD:EE:01", "AA:BB:CC:DD:EE:02"]),
      );
      const before = await page.evaluate(() => calls.length);
      await library.locator('[data-star="blue"]').click();
      assert.equal(await page.evaluate(() => calls.length), before);
      assert.match(await get("message").textContent(), /Choose 1 curtain/);
      await page.evaluate(() => (lib.addresses = ["AA:BB:CC:DD:EE:01"]));
    },
  );
  await check(
    "Clock rejects rapid refresh locally and sends complete conservative upload settings",
    async () => {
      await get("clock-interval").fill("10");
      let before = await page.evaluate(() => calls.length);
      await get("start-clock").click();
      assert.equal(await page.evaluate(() => calls.length), before);
      await get("clock-interval").fill("120");
      await get("clock-format").selectOption("12h");
      await get("start-clock").click();
      await page.waitForFunction(() => lib._data.status.kind === "clock");
      assert.deepEqual(
        await page.evaluate(
          () => calls.findLast((x) => x.action === "start_clock").payload,
        ),
        {
          addresses: ["AA:BB:CC:DD:EE:01"],
          format: "12h",
          interval: 120,
          color_byte: 255,
          background_byte: 254,
        },
      );
      assert.equal(await get("next").isDisabled(), true);
      assert.equal(await get("stop").isEnabled(), true);
      await get("stop").click();
    },
  );
  await check(
    "Notification includes chosen icon, duration and optional restore design",
    async () => {
      await get("notification-text").fill("HI");
      await get("notification-icon").selectOption("bell");
      await get("notification-seconds").fill("15");
      await get("restore-design").selectOption("blue");
      await get("show-message").click();
      const req = await page.evaluate(
        () => calls.findLast((x) => x.action === "show_message").payload,
      );
      assert.equal(req.text, "HI");
      assert.equal(req.icon, "bell");
      assert.equal(req.duration, 15);
      assert.equal(req.restore_design_id, "blue");
    },
  );
  await check(
    "Running playback locks editing and permits explicit previous, next and stop",
    async () => {
      await get("start").click();
      await page.waitForFunction(() => lib.running);
      assert.equal(await get("playlist-name").isDisabled(), true);
      assert.equal(await get("start-clock").isDisabled(), true);
      assert.equal(await get("next").isEnabled(), true);
      await get("next").click();
      await get("previous").click();
      await get("stop").click();
      assert.ok(
        await page.evaluate(
          () =>
            calls.some((x) => x.action === "next") &&
            calls.some((x) => x.action === "previous"),
        ),
      );
    },
  );
  await check(
    "Editor transfer interlock blocks every competing transmit control",
    async () => {
      await page.evaluate(() => (lib.editorBusy = true));
      for (const id of [
        "show-message",
        "start-clock",
        "start",
        "next",
        "previous",
      ])
        assert.equal(await get(id).isDisabled(), true);
      assert.equal(
        await library.locator('[data-recall="red"]').isDisabled(),
        true,
      );
      await page.evaluate(() => (lib.editorBusy = false));
    },
  );
  await check(
    "Phone layout fits the viewport without script errors",
    async () => {
      await page.setViewportSize({ width: 390, height: 844 });
      assert.equal(
        await page.evaluate(() => document.documentElement.scrollWidth <= 390),
        true,
      );
      assert.deepEqual(errors, []);
    },
  );
  console.log(checks.length + " library controls checks passed");
})()
  .catch((e) => {
    console.error(e);
    process.exitCode = 1;
  })
  .finally(async () => {
    if (browser) await browser.close();
    server.close();
  });
