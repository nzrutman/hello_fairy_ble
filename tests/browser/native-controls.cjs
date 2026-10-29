// Explicit native controls never send on initialization or to multiple curtains.
// Generated with aurora@aurora-smart-home (ha-integration-dev skill)
// https://github.com/tonylofgren/aurora-smart-home
const { chromium } = require("playwright");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const http = require("node:http");
const asset = path.resolve(
  __dirname,
  "../../custom_components/hello_fairy_ble/frontend/native-controls.js",
);
const html = `<!doctype html><meta name="viewport" content="width=device-width,initial-scale=1"><style>body{margin:0}</style><hello-fairy-native-controls></hello-fairy-native-controls><script type="module">
import '/native-controls.js';window.control=document.querySelector('hello-fairy-native-controls');window.requests=[];window.fail=false;window.events=[];
window.devices=[{address:'AA:BB:CC:DD:EE:01',name:'Left curtain',snapshot:{native:{}}},{address:'AA:BB:CC:DD:EE:02',name:'Right curtain',snapshot:{native:{profile_verified:true,music_supported:false,scene_speed_supported:false,timers_supported:false}}}];
control.addEventListener('studio-busy',e=>events.push(e.detail.busy));
control.hass={callWS:async request=>{requests.push(structuredClone(request));if(fail)throw new Error('Device connection failed');return {native:{profile_verified:true,music_supported:true,scene_speed_supported:true,timers_supported:true}};}};control.devices=devices;
</script>`;
const server = http.createServer((req, res) => {
  res.setHeader(
    "Content-Type",
    req.url.startsWith("/native-controls.js") ? "text/javascript" : "text/html",
  );
  res.end(
    req.url.startsWith("/native-controls.js") ? fs.readFileSync(asset) : html,
  );
});
let browser;
let count = 0;
async function check(name, fn) {
  await fn();
  count++;
  console.log("PASS", name);
}
(async () => {
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  browser = await chromium.launch({
    headless: true,
    channel: process.env.PW_CHANNEL || undefined,
  });
  const page = await browser.newPage({ viewport: { width: 375, height: 900 } });
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("http://127.0.0.1:" + server.address().port);
  const ui = page.locator("hello-fairy-native-controls");
  await page.waitForFunction(() =>
    control.shadowRoot.querySelector("#inspect"),
  );
  await ui.locator("details").evaluate((el) => (el.open = true));
  await check(
    "Initialization and opening controls do not contact BLE",
    async () => {
      assert.equal(await page.evaluate(() => requests.length), 0);
      assert.equal(await ui.locator("#music button").isDisabled(), true);
      assert.equal(await ui.locator("#timer button").isDisabled(), true);
    },
  );
  await check(
    "Explicit inspection targets one selected curtain and gates controls",
    async () => {
      await ui.locator("#inspect").click();
      await page.waitForFunction(() => !control._busy);
      assert.deepEqual(await page.evaluate(() => requests[0]), {
        type: "hello_fairy_ble/studio/native",
        address: "AA:BB:CC:DD:EE:01",
        action: "inspect",
        payload: {},
      });
      assert.equal(await ui.locator("#music button").isDisabled(), false);
      assert.equal(await ui.locator("#timer button").isDisabled(), false);
    },
  );
  await check(
    "Music submits one bounded request and reports transmission only",
    async () => {
      await ui.locator("#music-mode").selectOption("3");
      await ui.locator("#sensitivity").fill("72");
      await ui.locator("#music button").click();
      await page.waitForFunction(() => !control._busy);
      assert.deepEqual(await page.evaluate(() => requests[1]), {
        type: "hello_fairy_ble/studio/native",
        address: "AA:BB:CC:DD:EE:01",
        action: "music",
        payload: {
          mode: 3,
          auto_color: true,
          sensitivity: 72,
          brightness: 100,
          hue: 0,
          saturation: 100,
        },
      });
      assert.equal(await page.evaluate(() => requests.length), 2);
      assert.match(
        await ui.locator("[role=status]").innerText(),
        /Check the curtain/,
      );
      assert.deepEqual(await page.evaluate(() => events), [
        true,
        false,
        true,
        false,
      ]);
    },
  );
  await check("Invalid numeric values cannot send a command", async () => {
    await ui.locator("#seconds").fill("86401");
    await ui.locator("#countdown button").click();
    assert.equal(await page.evaluate(() => requests.length), 2);
  });
  await check("Timers replace only the explicitly submitted slot", async () => {
    await ui.locator("#slot").fill("3");
    await ui.locator("#hour").fill("21");
    await ui.locator("#minute").fill("15");
    await ui.locator("#day-1").check();
    await ui.locator("#day-5").check();
    await ui.locator("#timer button").click();
    await page.waitForFunction(() => !control._busy);
    assert.deepEqual(await page.evaluate(() => requests.at(-1).payload), {
      slot: 3,
      hour: 21,
      minute: 15,
      power: true,
      enabled: true,
      weekdays: [1, 5],
    });
  });
  await check(
    "Errors remain visible and release the shared busy state",
    async () => {
      await page.evaluate(() => {
        fail = true;
      });
      await ui.locator("#clock-sync button").click();
      await page.waitForFunction(() => !control._busy);
      assert.match(
        await ui.locator("[role=alert]").innerText(),
        /Device connection failed/,
      );
      assert.equal(await page.evaluate(() => events.at(-1)), false);
    },
  );
  await check(
    "External work blocks both UI controls and programmatic writes",
    async () => {
      const before = await page.evaluate(() => requests.length);
      await page.evaluate(async () => {
        control.externalBusy = true;
        await control._send("inspect");
      });
      assert.equal(await ui.locator("#inspect").isDisabled(), true);
      assert.equal(await page.evaluate(() => requests.length), before);
      await page.evaluate(() => {
        control.externalBusy = false;
      });
    },
  );
  await check(
    "A verified profile alone does not enable timers or music",
    async () => {
      const before = await page.evaluate(() => requests.length);
      await ui.locator("#curtain").selectOption("AA:BB:CC:DD:EE:02");
      assert.equal(await ui.locator("#countdown button").isDisabled(), false);
      assert.equal(await ui.locator("#timer button").isDisabled(), true);
      assert.equal(await ui.locator("#music button").isDisabled(), true);
      await page.evaluate(() => control._send("timer", { slot: 0 }));
      assert.equal(await page.evaluate(() => requests.length), before);
    },
  );
  await check(
    "Mobile controls fit the viewport and explain clock limitations",
    async () => {
      assert.equal(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
        true,
      );
      assert.match(
        await ui.locator("details").first().innerText(),
        /fixed UTC offset/,
      );
      assert.match(
        await ui.locator("details").first().innerText(),
        /stop Studio background playback/,
      );
    },
  );
  assert.deepEqual(errors, []);
  console.log(`${count} native controls checks passed`);
})()
  .catch((error) => {
    console.error(error);
    process.exitCode = 1;
  })
  .finally(async () => {
    await browser?.close();
    server.close();
  });
