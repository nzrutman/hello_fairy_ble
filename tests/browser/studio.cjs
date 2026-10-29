// Offline Studio workflow checks (ha-integration-dev skill).
// https://github.com/tonylofgren/aurora-smart-home
const { chromium } = require("playwright");
const fs = require("node:fs"),
  http = require("node:http"),
  assert = require("node:assert/strict"),
  path = require("node:path");
const root = path.resolve(__dirname, "../.."),
  assets = path.join(root, "custom_components/hello_fairy_ble/frontend");
const html = `<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><style>html,body{margin:0;height:100%;font-family:system-ui}</style></head><body><hello-fairy-studio-panel></hello-fairy-studio-panel><script type="module">import '/panel.js';window.panel=document.querySelector('hello-fairy-studio-panel');window.libraryData={designs:[],playlist:{items:[],loop:false},status:{state:'stopped',message:'Playlist stopped'}};window.libraryCalls=[];window.calls=[];window.requests=[];window.delay=0;window.failStatus=false;window.failSend=false;window.devices=[{name:'Left curtain',address:'AA:BB:CC:DD:EE:01',discovered:true,snapshot:{reported:null,last_upload:null,pixel_readback:false}},{name:'Right curtain',address:'AA:BB:CC:DD:EE:02',discovered:true,snapshot:{reported:null,last_upload:null,pixel_readback:false}}];window.hass={user:{id:'test-admin'},services:{hello_fairy_ble:{set_frame:{},set_two_picture_animation:{},set_diy_playback:{}}},callWS:async r=>{requests.push(r);if(r.type==='hello_fairy_ble/studio/library'){
  libraryCalls.push(r);const p=r.payload||{};
  if(r.action==='save_design'){const d={id:p.design_id||String(libraryData.designs.length+1),name:p.name,design:p.design};const i=libraryData.designs.findIndex(x=>x.id===d.id);if(i>=0)libraryData.designs[i]=d;else libraryData.designs.push(d);}
  if(r.action==='save_playlist'){if(p.playlist.items.some(i=>!Number.isInteger(i.seconds)||i.seconds<10))throw new Error('Each design must play for at least 10 seconds');libraryData.playlist=structuredClone(p.playlist);}
  if(r.action==='delete_design'){if(libraryData.playlist.items.some(i=>i.design_id===p.design_id))throw new Error('Remove this design from the playlist before deleting it');libraryData.designs=libraryData.designs.filter(d=>d.id!==p.design_id);}
  if(r.action==='start')libraryData.status={state:'holding',index:0,total:libraryData.playlist.items.length,message:'Last transmitted: saved design — physical display unconfirmed'};
  if(r.action==='stop')libraryData.status={state:'stopped',message:'Playlist stopped; last design remains'};
  return structuredClone(r.action==='status'?{status:libraryData.status}:libraryData);
}if(r.type==='hello_fairy_ble/studio/devices')return {version:'2.0.0',curtains:devices};if(r.type==='hello_fairy_ble/studio/read_status'){if(failStatus)throw new Error('No fresh report');const d=devices.find(d=>d.address===r.address);d.snapshot.reported={source:'device_notification',power:true,mode:2,scene:201,brightness_percent:100,received_at:new Date().toISOString()};return d.snapshot;}throw new Error('Unexpected WS');},callService:async(...args)=>{calls.push(args);if(delay)await new Promise(r=>setTimeout(r,delay));if(failSend)throw new Error('Simulated write failure');const [domain,action,p]=args,d=devices.find(d=>d.address===p.address);if(action==='set_frame')d.snapshot.last_upload={kind:'picture',frames:[p.pixels],sent_at:new Date().toISOString(),source:'last_upload'};if(action==='set_two_picture_animation')d.snapshot.last_upload={kind:'animation',frames:p.frames,sent_at:new Date().toISOString(),source:'last_upload'};if(action==='set_diy_playback')d.snapshot.last_playback={...p,source:'last_command'};}};panel.hass=hass;</script></body></html>`;
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
const artifacts = path.resolve(
  process.env.ARTIFACT_DIR || path.join(root, "test-results/browser"),
);
fs.mkdirSync(artifacts, { recursive: true });
let browser;
const checks = [];
async function check(name, fn) {
  await fn();
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
      viewport: { width: 1360, height: 1100 },
      acceptDownloads: true,
    }),
    errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("http://127.0.0.1:" + server.address().port);
  await page.waitForFunction(() => panel._canvas?._pixels?.length === 400);
  const p = page.locator("hello-fairy-studio-panel"),
    e = p.locator("hello-fairy-canvas-editor"),
    status = p.locator("hello-fairy-device-status");
  await check(
    "Opening Studio does not issue a BLE status query or any control writes",
    async () => {
      assert.equal(await page.evaluate(() => calls.length), 0);
      assert.ok(
        await page.evaluate(() =>
          requests.every(
            (r) =>
              r.type.endsWith("/devices") ||
              (r.type.endsWith("/library") && r.action === "get"),
          ),
        ),
      );
      assert.match(
        await status.evaluate((el) => el.shadowRoot.textContent),
        /not a live view/,
      );
    },
  );
  await check(
    "Ready-made patterns load locally and preserve supported colors",
    async () => {
      await e.locator('[data-pattern="heart"]').click();
      assert.equal(await page.evaluate(() => calls.length), 0);
      assert.ok(
        await page.evaluate(
          () =>
            panel._canvas._pixels.includes(0) &&
            panel._canvas._pixels.includes(254),
        ),
      );
    },
  );
  await check(
    "Send design uploads picture then applies chosen native movement and speed",
    async () => {
      await e.locator("#movement").selectOption("left");
      await e.locator("#speed").fill("25");
      await e.locator("#send").click();
      await page.waitForFunction(() => !panel._canvas._busy);
      const c = await page.evaluate(() => calls);
      assert.equal(c.length, 2);
      assert.equal(c[0][1], "set_frame");
      assert.equal(c[1][1], "set_diy_playback");
      assert.deepEqual(
        { ...c[1][2], address: null },
        {
          address: null,
          kind: "picture",
          movement: "left",
          speed: 25,
          brightness: 100,
        },
      );
    },
  );
  await check(
    "Last sent thumbnails are explicitly upload history with no fabricated report",
    async () => {
      await page.waitForFunction(
        () =>
          panel.shadowRoot
            .querySelector("#device-status")
            .shadowRoot.querySelectorAll("canvas").length === 1,
      );
      assert.match(
        await status.evaluate((el) => el.shadowRoot.textContent),
        /No device status report yet/,
      );
      assert.match(
        await status.evaluate((el) => el.shadowRoot.textContent),
        /Display may have changed since/,
      );
    },
  );
  await check(
    "Read device status displays a real report separately from uploaded pixels",
    async () => {
      await status.locator("details").evaluate((d) => (d.open = true));
      await status.locator("#read").click();
      await page.waitForFunction(
        () => !panel.shadowRoot.querySelector("#device-status")._busy,
      );
      assert.match(
        await status.evaluate((el) => el.shadowRoot.textContent),
        /Reported: On.*Scene 201.*100% brightness/,
      );
      assert.ok(
        await page.evaluate(() =>
          requests.some((r) => r.type.endsWith("/read_status")),
        ),
      );
    },
  );
  await check(
    "Animation edits are automatically saved while switching pictures",
    async () => {
      await e.locator("#mode-animation").click();
      await e.locator("#show-b").click();
      await e.locator('[data-pattern="arrow"]').click();
      const b = await page.evaluate(() => panel._canvas._pixels.slice());
      await e.locator("#show-a").click();
      assert.notDeepEqual(await page.evaluate(() => panel._canvas._pixels), b);
      await e.locator("#show-b").click();
      assert.deepEqual(await page.evaluate(() => panel._canvas._pixels), b);
    },
  );
  await check(
    "Animation exposes only the two APK-supported transition choices",
    async () => {
      assert.deepEqual(
        await e
          .locator("#movement option")
          .evaluateAll((a) => a.map((o) => o.value)),
        ["blink", "breathe"],
      );
    },
  );
  await check(
    "Animation send includes both pictures and applies selected speed/transition",
    async () => {
      await e.locator("#movement").selectOption("breathe");
      await e.locator("#speed").fill("30");
      await page.evaluate(() => (calls.length = 0));
      await e.locator("#send").click();
      await page.waitForFunction(() => !panel._canvas._busy);
      const c = await page.evaluate(() => calls);
      assert.equal(c.length, 2);
      assert.equal(c[0][1], "set_two_picture_animation");
      assert.equal(c[0][2].frames.length, 2);
      assert.equal(c[1][2].kind, "animation");
      assert.equal(c[1][2].speed, 30);
      assert.equal(c[1][2].movement, "breathe");
    },
  );
  await check(
    "Apply movement changes controls without another image upload",
    async () => {
      await page.evaluate(() => (calls.length = 0));
      await e.locator("#speed").fill("60");
      await e.locator("#apply-playback").click();
      await page.waitForFunction(() => !panel._canvas._busy);
      const c = await page.evaluate(() => calls);
      assert.equal(c.length, 1);
      assert.equal(c[0][1], "set_diy_playback");
    },
  );
  let saved;
  await check(
    "Save design includes both pictures and playback settings",
    async () => {
      await e.getByText("Save, open & more tools", { exact: true }).click();
      const promise = page.waitForEvent("download");
      await e.locator("#save").click();
      const download = await promise;
      saved = JSON.parse(fs.readFileSync(await download.path(), "utf8"));
      assert.equal(saved.version, 2);
      assert.equal(saved.kind, "animation");
      assert.equal(saved.frames.length, 2);
      assert.equal(saved.settings.speed, 60);
    },
  );
  await check(
    "Opening a saved animation restores both frames without sending",
    async () => {
      await page.evaluate(() => (calls.length = 0));
      await e.locator("#mode-picture").click();
      await e.locator("#pattern-file").setInputFiles({
        name: "design.json",
        mimeType: "application/json",
        buffer: Buffer.from(JSON.stringify(saved)),
      });
      await page.waitForFunction(
        () =>
          !panel._canvas._loading && panel._canvas._designKind === "animation",
      );
      assert.deepEqual(
        await page.evaluate(() => panel._canvas._animationFrames),
        saved.frames,
      );
      assert.equal(await page.evaluate(() => calls.length), 0);
    },
  );
  await check("Old single-picture files remain compatible", async () => {
    await e.locator("#pattern-file").setInputFiles({
      name: "legacy.json",
      mimeType: "application/json",
      buffer: Buffer.from(
        JSON.stringify({
          format: "hello-fairy-pattern",
          version: 1,
          width: 20,
          height: 20,
          pixels: Array(400).fill(120),
        }),
      ),
    });
    await page.waitForFunction(
      () => !panel._canvas._loading && panel._canvas._designKind === "picture",
    );
    assert.ok(
      await page.evaluate(() => panel._canvas._pixels.every((v) => v === 120)),
    );
  });
  await check(
    "Image uploads, keyboard paint, undo and redo still work",
    async () => {
      const png = Buffer.from(
        await page.evaluate(() => {
          const c = document.createElement("canvas");
          c.width = c.height = 20;
          const x = c.getContext("2d");
          x.fillStyle = "#f00";
          x.fillRect(0, 0, 20, 20);
          return c.toDataURL().split(",")[1];
        }),
        "base64",
      );
      await e
        .locator("#image-file")
        .setInputFiles({ name: "red.png", mimeType: "image/png", buffer: png });
      await page.waitForFunction(
        () => !panel._canvas._loading && panel._canvas._pixels[0] === 0,
      );
      await e.locator("canvas#grid").focus();
      await page.keyboard.press("Delete");
      assert.equal(await page.evaluate(() => panel._canvas._pixels[0]), 254);
      await e.locator("#undo").click();
      assert.equal(await page.evaluate(() => panel._canvas._pixels[0]), 0);
      await e.locator("#redo").click();
      assert.equal(await page.evaluate(() => panel._canvas._pixels[0]), 254);
    },
  );
  await check(
    "Device status failures show an error while retaining dated history",
    async () => {
      await page.evaluate(() => (failStatus = true));
      await status.locator("#read").click();
      await page.waitForFunction(
        () => !panel.shadowRoot.querySelector("#device-status")._busy,
      );
      assert.match(
        await status.evaluate((el) => el.shadowRoot.textContent),
        /No fresh report/,
      );
      assert.match(
        await status.evaluate((el) => el.shadowRoot.textContent),
        /Device report:/,
      );
      await page.evaluate(() => (failStatus = false));
    },
  );
  await check(
    "Two-curtain animation splits both pictures correctly and locks layout while sending",
    async () => {
      await p.locator("#summary").click();
      page.once("dialog", (d) => d.accept());
      await p.locator('input[data-address="AA:BB:CC:DD:EE:02"]').check();
      await e.locator("#mode-animation").click();
      await page.evaluate(() => {
        const e = panel._canvas;
        e._animationFrames = [
          Array.from({ length: 800 }, (_, i) => (i % 40 < 20 ? 0 : 120)),
          Array.from({ length: 800 }, (_, i) => (i % 40 < 20 ? 60 : 255)),
        ];
        e._pixels = e._animationFrames[0].slice();
        e._activeFrame = 0;
        e._settings.animation = {
          movement: "blink",
          speed: 100,
          brightness: 100,
        };
        e._updateButtons();
        calls.length = 0;
        delay = 120;
      });
      await e.locator("#send").click();
      assert.ok(await p.locator("#refresh").isDisabled());
      await page.waitForFunction(() => !panel._canvas._busy);
      const c = await page.evaluate(() => calls);
      assert.equal(c.length, 2);
      assert.ok(c[0][2].frames[0].every((v) => v === 0));
      assert.ok(c[0][2].frames[1].every((v) => v === 60));
      assert.ok(c[1][2].frames[0].every((v) => v === 120));
      assert.ok(c[1][2].frames[1].every((v) => v === 255));
      await page.evaluate(() => (delay = 0));
    },
  );
  await check(
    "A failed transfer stops without sending to later curtains or replaying",
    async () => {
      await page.evaluate(() => {
        calls.length = 0;
        failSend = true;
      });
      await e.locator("#send").click();
      await page.waitForFunction(() => !panel._canvas._busy);
      assert.equal(await page.evaluate(() => calls.length), 1);
      assert.match(await e.locator("#status").textContent(), /Stopped: 0 of 2/);
      await page.evaluate(() => (failSend = false));
    },
  );
  await check(
    "Pattern generation works at every supported multi-curtain width",
    async () => {
      const result = await page.evaluate(async () => {
        const m = await import("/patterns.js");
        return [20, 40, 80, 160].every((w) =>
          m.PATTERNS.every(([id]) => {
            const f = m.makePattern(id, w);
            return (
              f.length === w * 20 &&
              f.every((v) => (v >= 0 && v <= 180) || v === 254 || v === 255)
            );
          }),
        );
      });
      assert.ok(result);
    },
  );
  await page.evaluate(() => {
    const e = panel._canvas;
    e._draw();
    e._message(
      "Animation ready. First and second pictures are saved automatically.",
    );
    panel.shadowRoot.querySelector("details").open = false;
    panel.shadowRoot.querySelector(".page").scrollTop = 0;
    panel.shadowRoot
      .querySelector("#device-status")
      .shadowRoot.querySelector("details").open = false;
  });
  await page.screenshot({
    path: path.join(artifacts, "studio-desktop.png"),
    fullPage: true,
  });
  await check(
    "Phone layout exposes modes, patterns and speed with no page overflow",
    async () => {
      await page.setViewportSize({ width: 390, height: 1100 });
      await page.evaluate(() => {
        panel.narrow = true;
        panel.shadowRoot.querySelector(".page").scrollTop = 0;
      });
      assert.equal(
        await page.evaluate(() => document.documentElement.scrollWidth),
        390,
      );
      assert.ok(await e.locator("#mode-animation").isVisible());
      assert.ok(await e.locator("#speed").isVisible());
      assert.ok(await e.locator('[data-pattern="heart"]').isVisible());
      await page.screenshot({
        path: path.join(artifacts, "studio-phone.png"),
        fullPage: true,
      });
    },
  );

  const lib = p.locator("hello-fairy-design-library");
  await check(
    "Named two-picture designs save in HA without sending to curtains",
    async () => {
      await page.evaluate(() => (calls.length = 0));
      await lib.locator("#name").fill("Winter <heart>");
      await lib.locator("#save-design").click();
      await page.waitForFunction(
        () =>
          libraryData.designs.length === 1 &&
          !panel.shadowRoot.querySelector("#library")._busy,
      );
      const d = await page.evaluate(() => libraryData.designs[0]);
      assert.equal(d.design.width, 40);
      assert.equal(d.design.kind, "animation");
      assert.equal(d.design.frames.length, 2);
      assert.equal(await page.evaluate(() => calls.length), 0);
      assert.match(
        await lib.locator("#designs").textContent(),
        /Winter <heart>/,
      );
      assert.equal(await lib.locator("#designs heart").count(), 0);
    },
  );
  await check(
    "Playlist supports ordering, durations and repeat without uploads",
    async () => {
      await lib.locator("[data-add]").click();
      await lib.locator("[data-add]").click();
      await lib.locator('[data-seconds="0"]').fill("45");
      await lib.locator('[data-seconds="1"]').fill("60");
      await lib.locator('[data-down="0"]').click();
      assert.equal(await lib.locator('[data-seconds="0"]').inputValue(), "60");
      await lib.locator("#repeat").check();
      await lib.locator("#save-playlist").click();
      await page.waitForFunction(
        () => !panel.shadowRoot.querySelector("#library")._busy,
      );
      assert.deepEqual(
        await page.evaluate(() =>
          libraryData.playlist.items.map((i) => i.seconds),
        ),
        [60, 45],
      );
      assert.equal(await page.evaluate(() => libraryData.playlist.loop), true);
      assert.equal(await page.evaluate(() => calls.length), 0);
    },
  );
  await check(
    "Invalid duration is shown and does not start a playlist",
    async () => {
      await lib.locator('[data-seconds="0"]').fill("1");
      await lib.locator("#start").click();
      await page.waitForFunction(
        () => !panel.shadowRoot.querySelector("#library")._busy,
      );
      assert.match(await lib.locator("#message").textContent(), /at least 10/);
      assert.equal(
        await page.evaluate(
          () => libraryCalls.filter((r) => r.action === "start").length,
        ),
        0,
      );
      await lib.locator('[data-seconds="0"]').fill("60");
    },
  );
  await check(
    "Start delegates playback to HA and disables library edits until stopped",
    async () => {
      await lib.locator("#start").click();
      await page.waitForFunction(
        () =>
          panel.shadowRoot.querySelector("#library").running &&
          !panel.shadowRoot.querySelector("#library")._busy,
      );
      const start = await page.evaluate(() =>
        libraryCalls.findLast((r) => r.action === "start"),
      );
      assert.deepEqual(start.payload.addresses, [
        "AA:BB:CC:DD:EE:01",
        "AA:BB:CC:DD:EE:02",
      ]);
      assert.ok(await lib.locator("#save-design").isDisabled());
      assert.ok(await lib.locator("#stop").isEnabled());
      assert.match(
        await lib.locator("#play-status").textContent(),
        /physical display unconfirmed/,
      );
      await lib.locator("#stop").click();
      await page.waitForFunction(
        () =>
          !panel.shadowRoot.querySelector("#library").running &&
          !panel.shadowRoot.querySelector("#library")._busy,
      );
      assert.match(
        await lib.locator("#play-status").textContent(),
        /last design remains/,
      );
    },
  );
  await check(
    "Opening a library design restores both pictures without sending",
    async () => {
      await page.evaluate(() => {
        calls.length = 0;
        panel._canvas._pixels.fill(254);
      });
      page.once("dialog", (d) => d.accept());
      await lib.locator("[data-open]").click();
      await page.waitForFunction(() => !panel._canvas._loading);
      assert.deepEqual(
        await page.evaluate(() => panel._canvas._animationFrames),
        await page.evaluate(() => libraryData.designs[0].design.frames),
      );
      assert.equal(await page.evaluate(() => calls.length), 0);
    },
  );
  await check(
    "Referenced design deletion is refused without losing the library",
    async () => {
      page.once("dialog", (d) => d.accept());
      await lib.locator("[data-delete]").click();
      await page.waitForFunction(
        () => !panel.shadowRoot.querySelector("#library")._busy,
      );
      assert.match(
        await lib.locator("#message").textContent(),
        /Remove this design/,
      );
      assert.equal(await page.evaluate(() => libraryData.designs.length), 1);
    },
  );
  await check("Library and saved playlist reload in a new panel", async () => {
    await page.evaluate(async () => {
      const l = panel.shadowRoot.querySelector("#library");
      l._data = null;
      l._dirty = false;
      await l.refresh();
    });
    assert.equal(await lib.locator("[data-open]").count(), 1);
    assert.equal(await lib.locator("[data-seconds]").count(), 2);
    await lib.scrollIntoViewIfNeeded();
    assert.ok(await lib.locator("#start").isVisible());
    assert.equal(
      await lib.evaluate(
        (el) =>
          el.shadowRoot.querySelector("section").scrollWidth <= el.clientWidth,
      ),
      true,
    );
    await lib.screenshot({
      path: path.join(artifacts, "studio-library-phone.png"),
    });
  });
  await check(
    "Known incompatible devices cannot send DIY commands",
    async () => {
      await page.evaluate(async () => {
        devices.forEach((d) => {
          d.snapshot.device_info = { led_count: 200 };
          d.snapshot.diy_supported = false;
        });
        await panel._load();
      });
      assert.ok(await e.locator("#send").isDisabled());
      assert.ok(await e.locator("#apply-playback").isDisabled());
    },
  );
  await check("No browser exceptions", async () =>
    assert.deepEqual(errors, []),
  );
  fs.writeFileSync(
    path.join(artifacts, "browser-check-results.json"),
    JSON.stringify({ live_ha: false, physical_test: false, checks }, null, 2),
  );
  console.log("ALL", checks.length, "CHECKS PASSED");
})()
  .catch((e) => {
    console.error(e);
    process.exitCode = 1;
  })
  .finally(async () => {
    await browser?.close();
    server.close();
  });
