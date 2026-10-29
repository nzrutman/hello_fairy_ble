// Integration-owned named layout application checks (ha-integration-dev skill).
// https://github.com/tonylofgren/aurora-smart-home
const { chromium } = require("playwright");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const http = require("node:http");
const root = path.resolve(__dirname, "../..");
const assets = path.join(root, "custom_components/hello_fairy_ble/frontend");
const html = `<!doctype html><meta name="viewport" content="width=device-width,initial-scale=1"><style>body{margin:0}</style><hello-fairy-studio-panel></hello-fairy-studio-panel><script type="module">
import '/panel.js';window.panel=document.querySelector('hello-fairy-studio-panel');window.writes=[];window.wsRequests=[];window.deferNative=false;window.releaseNative=null;
window.devices=[{name:'Left curtain',address:'AA:BB:CC:DD:EE:01',discovered:true,snapshot:{}},{name:'Right curtain',address:'AA:BB:CC:DD:EE:02',discovered:true,snapshot:{}}];
window.library={designs:[],playlist:{items:[],loop:false},playlists:[],favorites:[],orientations:{},layouts:[{id:'one',name:'One curtain',addresses:['AA:BB:CC:DD:EE:01']},{id:'two',name:'Both curtains',addresses:['AA:BB:CC:DD:EE:01','AA:BB:CC:DD:EE:02']}],status:{state:'stopped',message:'Stopped'}};
panel.hass={user:{id:'admin'},services:{hello_fairy_ble:{set_frame:{},set_two_picture_animation:{},set_diy_playback:{}}},callWS:async r=>{wsRequests.push(structuredClone(r));if(r.type.endsWith('/native')){if(deferNative)await new Promise(resolve=>window.releaseNative=resolve);return {native:{profile_verified:true}};}return r.type.endsWith('/devices')?{curtains:devices}:structuredClone(library);},callService:async(...args)=>writes.push(args)};
</script>`;
const server = http.createServer((req, res) => {
  const name = req.url.split("?")[0];
  if (
    /^\/[a-z-]+\.js$/.test(name) &&
    fs.existsSync(path.join(assets, name.slice(1)))
  ) {
    res.setHeader("Content-Type", "text/javascript");
    res.end(fs.readFileSync(path.join(assets, name.slice(1))));
  } else {
    res.setHeader("Content-Type", "text/html");
    res.end(html);
  }
});
let browser;
const checks = [];
async function check(name, fn) {
  await fn();
  checks.push(name);
  console.log("PASS", name);
}
(async () => {
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  browser = await chromium.launch({
    headless: true,
    channel: process.env.PW_CHANNEL || undefined,
  });
  const page = await browser.newPage({
      viewport: { width: 1000, height: 1000 },
    }),
    errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("http://127.0.0.1:" + server.address().port);
  await page.waitForFunction(
    () =>
      panel._canvas?._pixels?.length === 400 &&
      panel.shadowRoot.querySelector("#library")._data,
  );
  const lib = page
    .locator("hello-fairy-studio-panel")
    .locator("hello-fairy-design-library");
  await lib.locator("#library-tools").evaluate((el) => (el.open = true));
  await check(
    "Named layout application is local and never sends frames",
    async () => {
      await page.evaluate(() => {
        panel._canvas._pixels[0] = 0;
      });
      await lib.locator('[data-layout="one"]').click();
      assert.equal(await page.evaluate(() => panel._canvas._pixels[0]), 0);
      assert.equal(await page.evaluate(() => writes.length), 0);
    },
  );
  await check(
    "Cancelling a layout change keeps the draft and selected curtains",
    async () => {
      page.once("dialog", (d) => d.dismiss());
      await lib.locator('[data-layout="two"]').click();
      assert.equal(await page.evaluate(() => panel._selected.length), 1);
      assert.equal(await page.evaluate(() => panel._canvas._pixels[0]), 0);
    },
  );
  await check(
    "Confirmed layout changes update canvas width and ordered targets",
    async () => {
      page.once("dialog", (d) => d.accept());
      await lib.locator('[data-layout="two"]').click();
      await page.waitForFunction(() => panel._canvas._pixels.length === 800);
      assert.deepEqual(await page.evaluate(() => panel._selected), [
        "AA:BB:CC:DD:EE:01",
        "AA:BB:CC:DD:EE:02",
      ]);
      assert.ok(
        await page.evaluate(() =>
          panel._canvas._pixels.every((p) => p === 254),
        ),
      );
      assert.equal(await page.evaluate(() => writes.length), 0);
    },
  );
  await check(
    "Unknown imported layout targets fail without selecting a partial layout",
    async () => {
      await page.evaluate(() =>
        panel._applySavedLayout({
          name: "Missing",
          addresses: ["AA:BB:CC:DD:EE:01", "AA:BB:CC:DD:EE:99"],
        }),
      );
      assert.equal(await page.evaluate(() => panel._selected.length), 2);
      assert.match(
        await lib.locator("#message").textContent(),
        /unloaded curtains/,
      );
      assert.equal(await page.evaluate(() => writes.length), 0);
    },
  );
  await check(
    "Import interlock blocks sends, reads and layout changes until released",
    async () => {
      const editor = page
        .locator("hello-fairy-studio-panel")
        .locator("hello-fairy-canvas-editor");
      const status = page
        .locator("hello-fairy-studio-panel")
        .locator("hello-fairy-device-status");
      await lib.evaluate((el) =>
        el.dispatchEvent(
          new CustomEvent("studio-library-busy", {
            bubbles: true,
            composed: true,
            detail: { busy: true },
          }),
        ),
      );
      assert.ok(await editor.locator("#send").isDisabled());
      await status.locator("details").evaluate((el) => (el.open = true));
      assert.ok(await status.locator("#read").isDisabled());
      await page.evaluate(async () => {
        await panel._canvas._send();
        await panel.shadowRoot.querySelector("#device-status")._read();
        panel._applySavedLayout({
          name: "One",
          addresses: ["AA:BB:CC:DD:EE:01"],
        });
      });
      assert.equal(await page.evaluate(() => writes.length), 0);
      assert.equal(await page.evaluate(() => panel._selected.length), 2);
      await lib.evaluate((el) =>
        el.dispatchEvent(
          new CustomEvent("studio-library-busy", {
            bubbles: true,
            composed: true,
            detail: { busy: false },
          }),
        ),
      );
      assert.ok(await editor.locator("#send").isEnabled());
      assert.ok(await status.locator("#read").isEnabled());
    },
  );
  await check(
    "Native controls appear inside the integrated Studio without automatic BLE queries",
    async () => {
      const native = page
        .locator("hello-fairy-studio-panel")
        .locator("hello-fairy-native-controls");
      assert.equal(await native.count(), 1);
      await native
        .locator("details")
        .first()
        .evaluate((el) => (el.open = true));
      assert.equal(await native.locator("#curtain option").count(), 2);
      assert.equal(
        await page.evaluate(() =>
          wsRequests.some((r) => r.type.endsWith("/native")),
        ),
        false,
      );
    },
  );
  await check(
    "Native inspection locks sends, layout, imports and status while preserving the draft",
    async () => {
      const studio = page.locator("hello-fairy-studio-panel");
      const editor = studio.locator("hello-fairy-canvas-editor");
      const status = studio.locator("hello-fairy-device-status");
      const native = studio.locator("hello-fairy-native-controls");
      await page.evaluate(() => {
        panel._canvas._pixels[2] = 60;
        deferNative = true;
      });
      await native.locator("#inspect").click();
      await page.waitForFunction(() => Boolean(releaseNative));
      assert.ok(await editor.locator("#send").isDisabled());
      assert.ok(await editor.locator("#apply-playback").isDisabled());
      assert.ok(await status.locator("#read").isDisabled());
      assert.ok(await lib.locator("#import-library").isDisabled());
      assert.ok(await studio.locator("#refresh").isDisabled());
      const before = await page.evaluate(() => wsRequests.length);
      await page.evaluate(async () => {
        await panel._canvas._send();
        await panel.shadowRoot.querySelector("#device-status")._read();
        await panel.shadowRoot.querySelector("#library")._importLibrary({
          size: 0,
          text: async () => {
            throw Error("Import should be blocked");
          },
        });
        panel._applySavedLayout({
          name: "One",
          addresses: ["AA:BB:CC:DD:EE:01"],
        });
      });
      assert.equal(await page.evaluate(() => wsRequests.length), before);
      assert.equal(await page.evaluate(() => writes.length), 0);
      assert.equal(await page.evaluate(() => panel._selected.length), 2);
      assert.equal(await page.evaluate(() => panel._canvas._pixels[2]), 60);
      await page.evaluate(() => {
        deferNative = false;
        releaseNative();
        releaseNative = null;
      });
      await page.waitForFunction(
        () =>
          !panel.shadowRoot.querySelector("#native-controls")._busy &&
          !panel._loading,
      );
      assert.ok(await editor.locator("#send").isEnabled());
      assert.ok(await status.locator("#read").isEnabled());
      assert.ok(await lib.locator("#import-library").isEnabled());
      assert.equal(await page.evaluate(() => panel._canvas._pixels[2]), 60);
    },
  );
  await check(
    "Editor activity and library import both interlock native controls without clearing artwork",
    async () => {
      const native = page
        .locator("hello-fairy-studio-panel")
        .locator("hello-fairy-native-controls");
      let before = await page.evaluate(() => wsRequests.length);
      await page.evaluate(async () => {
        panel._canvas._busy = true;
        panel._canvas._updateButtons();
        await panel.shadowRoot
          .querySelector("#native-controls")
          ._send("inspect");
      });
      assert.ok(await native.locator("#inspect").isDisabled());
      assert.equal(await page.evaluate(() => wsRequests.length), before);
      await page.evaluate(() => {
        panel._canvas._busy = false;
        panel._canvas._updateButtons();
      });
      assert.ok(await native.locator("#inspect").isEnabled());
      before = await page.evaluate(() => wsRequests.length);
      await page.evaluate(async () => {
        panel.shadowRoot.querySelector("#library")._importBusy(true);
        await panel.shadowRoot
          .querySelector("#native-controls")
          ._send("inspect");
      });
      assert.ok(await native.locator("#inspect").isDisabled());
      assert.equal(await page.evaluate(() => wsRequests.length), before);
      await page.evaluate(() =>
        panel.shadowRoot.querySelector("#library")._importBusy(false),
      );
      assert.ok(await native.locator("#inspect").isEnabled());
      assert.equal(await page.evaluate(() => panel._canvas._pixels[2]), 60);
      assert.equal(await page.evaluate(() => writes.length), 0);
    },
  );
  assert.deepEqual(errors, []);
  console.log("ALL", checks.length, "PANEL LAYOUT CHECKS PASSED");
})()
  .catch((e) => {
    console.error(e);
    process.exitCode = 1;
  })
  .finally(async () => {
    await browser?.close();
    server.close();
  });
