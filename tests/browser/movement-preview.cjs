/** Estimated motion tests. Generated with aurora@aurora-smart-home
 * (ha-integration-dev skill) https://github.com/tonylofgren/aurora-smart-home */
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const http = require("node:http");
const { chromium } = require("playwright");
const assets = path.resolve(
  __dirname,
  "../../custom_components/hello_fairy_ble/frontend",
);
let browser,
  server,
  count = 0;
async function check(name, fn) {
  await fn();
  count++;
  console.log("PASS", name);
}
(async () => {
  const { estimateMovement: estimate } = await import(
    `data:text/javascript;base64,${fs.readFileSync(path.join(assets, "movement-preview.js")).toString("base64")}`
  );
  const frame = Array.from({ length: 800 }, (_, i) => (i % 40 < 20 ? 0 : 60));
  const snapshot = JSON.stringify(frame);
  const settings = { movement: "loop_left", speed: 100, brightness: 100 };
  await check(
    "Looping retains independent curtain colors and source pixels",
    () => {
      const result = estimate([frame], 40, settings, 750);
      assert.deepEqual(result.pixels, frame);
      assert.notEqual(result.pixels, frame);
      assert.equal(JSON.stringify(frame), snapshot);
    },
  );
  await check("Non-looping movement clips within each curtain", () => {
    const result = estimate(
      [frame],
      40,
      { ...settings, movement: "left" },
      375,
    );
    assert.equal(result.pixels[0], 0);
    assert.equal(result.pixels[19], 254);
    assert.equal(result.pixels[20], 60);
    assert.equal(result.pixels[39], 254);
    assert.ok(result.pixels.every((p) => [0, 60, 254].includes(p)));
  });
  await check(
    "Two-picture blink and breathe use both pictures without mutation",
    () => {
      const second = Array(800).fill(120);
      for (const movement of ["blink", "breathe"]) {
        const a = estimate(
          [frame, second],
          40,
          { ...settings, movement },
          200,
          true,
        );
        const b = estimate(
          [frame, second],
          40,
          { ...settings, movement },
          1000,
          true,
        );
        assert.equal(a.pixels[0], 0);
        assert.equal(b.pixels[0], 120);
        assert.ok(a.opacity >= 0 && a.opacity <= 1);
      }
      assert.equal(JSON.stringify(frame), snapshot);
    },
  );
  await check(
    "Blink, still and brightness are illustrative opacity only",
    () => {
      assert.equal(
        estimate([frame], 40, { ...settings, movement: "blink" }, 1000).opacity,
        0,
      );
      assert.equal(
        estimate(
          [frame],
          40,
          { ...settings, movement: "still", brightness: 25 },
          1000,
        ).opacity,
        0.25,
      );
      for (const movement of [
        "up",
        "down",
        "left",
        "right",
        "loop_up",
        "loop_down",
        "loop_right",
        "breathe",
      ])
        assert.equal(
          estimate([frame], 40, { ...settings, movement }, 500).pixels.length,
          800,
        );
    },
  );
  server = http.createServer((req, res) => {
    const name = req.url.split("?")[0];
    if (/^\/[a-z-]+\.js$/.test(name)) {
      res.setHeader("Content-Type", "text/javascript");
      res.end(fs.readFileSync(path.join(assets, name.slice(1))));
    } else
      res.end(
        '<!doctype html><meta name="viewport" content="width=device-width"><body style="margin:0"><script type="module">import "/editor.js";window.editor=document.createElement("hello-fairy-canvas-editor");editor.setConfig({curtains:[{name:"Left",address:"AA:BB:CC:DD:EE:01"},{name:"Right",address:"AA:BB:CC:DD:EE:02"}]});window.writes=[];editor.hass={services:{hello_fairy_ble:{set_frame:{},set_two_picture_animation:{},set_diy_playback:{}}},callService:(...args)=>writes.push(args)};document.body.append(editor);</script>',
      );
  });
  await new Promise((r) => server.listen(0, "127.0.0.1", r));
  browser = await chromium.launch({
    headless: true,
    channel: process.env.PW_CHANNEL || undefined,
  });
  const page = await browser.newPage({ viewport: { width: 390, height: 844 } });
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(`http://127.0.0.1:${server.address().port}`);
  await page.waitForFunction(() => window.editor?._$?.("preview-play"));
  await page.waitForTimeout(150);
  await check(
    "No autoplay; explicit simulation and timing labels fit phone",
    async () => {
      assert.equal(await page.evaluate(() => !!editor._previewRunning), false);
      const text = await page.evaluate(() => editor.shadowRoot.textContent);
      assert.match(text, /ESTIMATED LOCAL PREVIEW/);
      assert.match(text, /illustrative/);
      assert.match(text, /Each curtain moves separately/);
      assert.ok(
        await page.evaluate(() => document.documentElement.scrollWidth <= 390),
      );
    },
  );
  await check(
    "Preview writes no services, modifies no draft/history and stays capped",
    async () => {
      await page.evaluate(() => {
        editor._settings.picture.movement = "loop_left";
        window.before = JSON.stringify({
          pixels: editor._pixels,
          frames: editor._animationFrames,
          undo: editor._undo,
        });
        editor._startMovementPreview();
      });
      await page.waitForTimeout(180);
      assert.equal(await page.evaluate(() => editor._previewRunning), true);
      assert.equal(await page.evaluate(() => writes.length), 0);
      assert.equal(
        await page.evaluate(
          () =>
            JSON.stringify({
              pixels: editor._pixels,
              frames: editor._animationFrames,
              undo: editor._undo,
            }) === before,
        ),
        true,
      );
    },
  );
  await check(
    "Painting tools remain usable and editing cancels animation",
    async () => {
      await page.locator("hello-fairy-canvas-editor #grid").focus();
      await page.keyboard.press("Delete");
      assert.equal(await page.evaluate(() => editor._previewRunning), false);
      assert.equal(await page.evaluate(() => editor._previewRAF), undefined);
    },
  );
  await check("Playback setting changes cancel preview", async () => {
    await page.evaluate(() => editor._startMovementPreview());
    await page
      .locator("hello-fairy-canvas-editor #movement")
      .selectOption("right");
    assert.equal(await page.evaluate(() => editor._previewRunning), false);
  });
  await check(
    "Stop cancels RAF, hidden pages stop and disconnect cleans listeners",
    async () => {
      await page.evaluate(() => {
        editor._startMovementPreview();
        editor._stopMovementPreview();
      });
      assert.equal(await page.evaluate(() => editor._previewRAF), undefined);
      await page.evaluate(() => {
        editor._startMovementPreview();
        Object.defineProperty(document, "hidden", {
          configurable: true,
          value: true,
        });
        document.dispatchEvent(new Event("visibilitychange"));
      });
      assert.equal(await page.evaluate(() => editor._previewRunning), false);
      await page.evaluate(() => {
        delete document.hidden;
        editor._startMovementPreview();
        editor.remove();
      });
      assert.equal(await page.evaluate(() => editor._previewRAF), undefined);
      await page.evaluate(() => document.body.append(editor));
      assert.equal(await page.evaluate(() => editor._previewRunning), false);
    },
  );
  await check(
    "Reduced motion renders static output without animation",
    async () => {
      await page.emulateMedia({ reducedMotion: "reduce" });
      await page.evaluate(() => editor._startMovementPreview());
      assert.equal(await page.evaluate(() => editor._previewRunning), false);
      assert.match(
        await page
          .locator("hello-fairy-canvas-editor #preview-state")
          .innerText(),
        /Reduced motion/,
      );
      assert.equal(await page.evaluate(() => writes.length), 0);
      assert.deepEqual(errors, []);
    },
  );
  console.log(`${count} movement preview checks passed`);
})()
  .catch((e) => {
    console.error(e);
    process.exitCode = 1;
  })
  .finally(async () => {
    await browser?.close();
    server?.close();
  });
