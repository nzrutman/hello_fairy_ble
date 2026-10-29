// Studio installation correction checks (ha-integration-dev skill).
// https://github.com/tonylofgren/aurora-smart-home
const { chromium } = require("playwright");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const http = require("node:http");
const path = require("node:path");
const root = path.resolve(__dirname, "../..");
const assets = path.join(root, "custom_components/hello_fairy_ble/frontend");
const artifacts = path.join(root, "test-results/browser");
fs.mkdirSync(artifacts, { recursive: true });
const html = `<!doctype html><meta name="viewport" content="width=device-width,initial-scale=1"><style>body{margin:0}</style><hello-fairy-studio-panel></hello-fairy-studio-panel><script type="module">
import '/panel.js';window.panel=document.querySelector('hello-fairy-studio-panel');window.writes=[];window.requests=[];
window.state={designs:[],playlist:{items:[],loop:false},playlists:[],favorites:[],orientations:{},status:{state:'stopped',message:'Stopped'}};
panel.hass={user:{id:'admin'},services:{hello_fairy_ble:{set_frame:{},set_two_picture_animation:{},set_diy_playback:{}}},
callWS:async r=>{requests.push(r);if(r.type.endsWith('/devices'))return {curtains:[{address:'AA:BB:CC:DD:EE:01',name:'Test curtain',discovered:true,snapshot:{}}]};
if(r.action==='save_orientation'){const {address,...correction}=r.payload;state.orientations[address]=correction;}return structuredClone(state);},
callService:async(...args)=>writes.push(args)};
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
  const p = page.locator("hello-fairy-studio-panel"),
    e = p.locator("hello-fairy-canvas-editor");
  await p.locator("#summary").click();
  await check("Opening installation settings sends no BLE commands", async () =>
    assert.equal(await page.evaluate(() => writes.length), 0),
  );
  await check(
    "Saving rotation preserves the draft and only writes HA settings",
    async () => {
      await page.evaluate(() => {
        panel._canvas._pixels.fill(254);
        panel._canvas._pixels[0] = 0;
        panel._canvas._draw();
      });
      await p.locator('[data-orientation="rotation"]').selectOption("90");
      await page.waitForFunction(
        () =>
          !panel._savingOrientation &&
          state.orientations["AA:BB:CC:DD:EE:01"]?.rotation === 90,
      );
      assert.equal(await page.evaluate(() => panel._canvas._pixels[0]), 0);
      assert.equal(await page.evaluate(() => panel._canvas._pixels[19]), 254);
      assert.equal(await page.evaluate(() => writes.length), 0);
    },
  );
  await check(
    "Manual picture upload applies correction once at transport",
    async () => {
      await e.locator("#send").click();
      await page.waitForFunction(() => !panel._canvas._busy);
      const sent = await page.evaluate(
        () => writes.find((c) => c[1] === "set_frame")[2].pixels,
      );
      assert.equal(sent[19], 0);
      assert.equal(sent[0], 254);
      assert.equal(sent.filter((v) => v === 0).length, 1);
      assert.equal(
        await page.evaluate(() => panel._canvas.exportDesign().frames[0][0]),
        0,
      );
    },
  );
  await check(
    "Orientation reload retains logical canvas and saved installation",
    async () => {
      await page.evaluate(async () => {
        await panel.shadowRoot.querySelector("#library").refresh();
        await panel._load();
      });
      assert.equal(
        await p.locator('[data-orientation="rotation"]').inputValue(),
        "90",
      );
      assert.equal(await page.evaluate(() => panel._canvas._pixels[0]), 0);
    },
  );
  await check(
    "Browser and Python transform conventions match known corners",
    async () => {
      const result = await page.evaluate(async () => {
        const { transformCurtain } = await import("/orientation.js");
        const f = Array(400).fill(254);
        f[0] = 0;
        return [0, 90, 180, 270].map((rotation) =>
          transformCurtain(f, { rotation }).indexOf(0),
        );
      });
      assert.deepEqual(result, [0, 19, 399, 380]);
    },
  );
  assert.deepEqual(errors, []);
  fs.writeFileSync(
    path.join(artifacts, "orientation-results.json"),
    JSON.stringify({ checks, physical_test: false }, null, 2),
  );
  console.log("ALL", checks.length, "ORIENTATION CHECKS PASSED");
})()
  .catch((e) => {
    console.error(e);
    process.exitCode = 1;
  })
  .finally(async () => {
    await browser?.close();
    server.close();
  });
