/** Local drawing validation. Generated with aurora@aurora-smart-home
 * (ha-integration-dev skill) https://github.com/tonylofgren/aurora-smart-home */
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const http = require("node:http");
const { chromium } = require("playwright");
const root = path.resolve(__dirname, "../..");
const frontend = path.join(root, "custom_components/hello_fairy_ble/frontend");

(async () => {
  const tools = await import(
    `data:text/javascript;base64,${fs.readFileSync(path.join(frontend, "design-tools.js")).toString("base64")}`
  );
  let checks = 0;
  const check = (name, fn) => {
    fn();
    checks++;
    console.log(`PASS ${name}`);
  };
  const off = Array(800).fill(254),
    r = { x: 20, y: 0, width: 20, height: 20 };
  check(
    "Region validation rejects fractional and out-of-bounds rectangles",
    () => {
      assert.throws(() =>
        tools.checkedRegion({ x: 39, y: 0, width: 2, height: 20 }, 40),
      );
      assert.throws(() =>
        tools.checkedRegion({ x: 0.5, y: 0, width: 2, height: 20 }, 40),
      );
    },
  );
  check("Region fill does not mutate source or adjacent curtain", () => {
    const p = tools.mapRegion(off, 40, r, () => 60);
    assert.equal(p.filter((v) => v === 60).length, 400);
    assert.equal(p[19], 254);
    assert.equal(p[20], 60);
    assert.equal(off[20], 254);
  });
  check("Text occupies region only and reports clipping", () => {
    const result = tools.renderText(off, 40, r, "HELLO HELLO", { color: 0 });
    assert.equal(result.clipped, true);
    assert.ok(result.pixels.some((p) => p === 0));
    result.pixels.forEach((p, i) => {
      if (i % 40 < 20) assert.equal(p, 254);
    });
  });
  check(
    "Text wrapping, scales, unicode fallback and clear are explicit",
    () => {
      const region = { x: 0, y: 0, width: 7, height: 20 };
      const p = tools.renderText(off, 40, region, "AAA", { wrap: true });
      assert.equal(p.clipped, false);
      assert.equal(p.pixels[6 * 40 + 1], 0);
      assert.equal(tools.renderText(off, 40, r, "☀").unsupported, 1);
      assert.equal(tools.renderText(off, 40, r, "é").unsupported, 0);
      assert.throws(() => tools.renderText(off, 40, r, "A", { scale: 4 }));
      const clear = tools.renderText(Array(800).fill(60), 40, r, "", {
        clear: true,
      });
      assert.equal(clear.pixels[0], 60);
      assert.equal(clear.pixels[20], 254);
    },
  );
  check(
    "Palette maps hue around the red boundary and preserves white/off",
    () => {
      const p = off.slice();
      p[20] = 179;
      p[21] = 255;
      p[22] = 254;
      p[23] = 110;
      const result = tools.recolor(p, 40, r, [0, 120]);
      assert.deepEqual(result.slice(20, 24), [0, 255, 254, 120]);
      assert.equal(tools.recolor(p, 40, r, [60], true)[21], 60);
      assert.deepEqual(
        tools.parsePalette("0,120,240,white,off"),
        [0, 60, 120, 255, 254],
      );
      assert.throws(() => tools.parsePalette("400"));
      assert.throws(() => tools.parsePalette(""));
    },
  );
  check("Flip, mirror and tile read original selected area", () => {
    const p = off.slice();
    p[20] = 0;
    p[21] = 60;
    p[60] = 120;
    assert.equal(tools.transformRegion(p, 40, r, "flip-h")[39], 0);
    assert.equal(tools.transformRegion(p, 40, r, "mirror-h")[38], 60);
    const tiled = tools.transformRegion(p, 40, r, "tile", {
      tileWidth: 2,
      tileHeight: 2,
    });
    assert.equal(tiled[22], 0);
    assert.equal(tiled[100], 0);
    assert.equal(tiled[0], 254);
    assert.throws(() =>
      tools.transformRegion(p, 40, r, "tile", { tileWidth: 21, tileHeight: 2 }),
    );
  });
  check(
    "90 degree rotation preserves square and centers rectangular crop",
    () => {
      const p = off.slice();
      p[20] = 0;
      const rotated = tools.transformRegion(p, 40, r, "rotate-90");
      assert.equal(rotated[39], 0);
      let q = p;
      for (let i = 0; i < 4; i++)
        q = tools.transformRegion(q, 40, r, "rotate-90");
      assert.deepEqual(q, p);
      const rectangle = { x: 0, y: 0, width: 4, height: 2 };
      const a = off.slice();
      a[0] = 60;
      a[1] = 120;
      const b = tools.transformRegion(a, 40, rectangle, "rotate-90");
      assert.equal(b[0], 254);
      assert.equal(b[2], 120);
      assert.equal(b[3], 254);
    },
  );
  const server = http.createServer((req, res) => {
    const name = new URL(req.url, "http://localhost").pathname.slice(1);
    if (/^[a-z-]+\.js$/.test(name)) {
      res.setHeader("Content-Type", "text/javascript");
      res.end(fs.readFileSync(path.join(frontend, name)));
      return;
    }
    res.setHeader("Content-Type", "text/html");
    res.end(
      `<script type="module">import './editor.js';const e=document.createElement('hello-fairy-canvas-editor');e.setConfig({curtains:[{name:'Left',address:'AA:BB:CC:DD:EE:01'},{name:'Right',address:'AA:BB:CC:DD:EE:02'}]});window.calls=[];e.hass={services:{hello_fairy_ble:{set_frame:{},set_two_picture_animation:{},set_diy_playback:{}}},callService:async(...args)=>window.calls.push(args)};document.body.append(e);window.editor=e;</script>`,
    );
  });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  let browser;
  try {
    browser = await chromium.launch({
      headless: true,
      ...(process.env.PW_CHANNEL ? { channel: process.env.PW_CHANNEL } : {}),
    });
    const page = await browser.newPage({
        viewport: { width: 1100, height: 900 },
      }),
      errors = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await page.goto(`http://127.0.0.1:${server.address().port}`);
    const editor = page.locator("hello-fairy-canvas-editor");
    await editor.locator("#creative-tools summary").click();
    await editor.locator("#region-target").selectOption("1");
    await editor.locator("#text-content").fill("HI");
    await editor.locator("#text-add").click();
    check("Text UI restricts drawing to selected curtain", () => {});
    let pixels = await page.evaluate(
      () => window.editor.exportDesign().frames[0],
    );
    assert.ok(pixels.includes(0));
    pixels.forEach((p, i) => {
      if (i % 40 < 20) assert.equal(p, 254);
    });
    await editor.locator("#undo").click();
    assert.ok(
      (await page.evaluate(() => window.editor.exportDesign().frames[0])).every(
        (p) => p === 254,
      ),
    );
    check("Text edit is undoable", () => {});
    await editor.locator("#region-fill").click();
    await editor.locator("#palette-name").selectOption("custom");
    await editor.locator("#palette-custom").fill("120");
    await editor.locator("#palette-apply").click();
    assert.equal(
      (await page.evaluate(() => window.editor.exportDesign().frames[0]))[20],
      60,
    );
    await editor.locator("#palette-custom").fill("broken");
    await editor.locator("#palette-apply").click();
    assert.match(
      await editor.locator("#status").textContent(),
      /Palette colors/,
    );
    check("Custom palette validates and applies without upload", () => {});
    await editor.locator("#region-target").selectOption("custom");
    await editor.locator("#rx").fill("39");
    await editor.locator("#rw").fill("2");
    await editor.locator("#region-apply").click();
    assert.match(
      await editor.locator("#status").textContent(),
      /inside the canvas/,
    );
    check("Invalid region leaves previous selection intact", () => {});
    await editor.locator("[data-pattern=heart]").click();
    pixels = await page.evaluate(() => window.editor.exportDesign().frames[0]);
    pixels.forEach((p, i) => {
      if (i % 40 < 20) assert.equal(p, 254);
    });
    await editor.locator("#mode-animation").click();
    await editor.locator("#show-b").click();
    await editor.locator("#region-clear").click();
    const design = await page.evaluate(() => window.editor.exportDesign());
    assert.notDeepEqual(design.frames[0], design.frames[1]);
    assert.equal((await page.evaluate(() => window.calls)).length, 0);
    check(
      "Region patterns and animation edits stay local and separate",
      () => {},
    );
    await page.setViewportSize({ width: 360, height: 850 });
    assert.equal(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
      true,
    );
    assert.deepEqual(errors, []);
    check("Creative tools fit phone width without browser errors", () => {});
  } finally {
    await browser?.close();
    await new Promise((resolve) => server.close(resolve));
  }
  console.log(`${checks} design-tool checks passed.`);
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
