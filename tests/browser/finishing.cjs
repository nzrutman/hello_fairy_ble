// Offline library finishing checks (HA Integration Dev skill).
// https://github.com/tonylofgren/aurora-smart-home
const { chromium } = require("playwright");
const fs = require("node:fs"),
  http = require("node:http"),
  path = require("node:path"),
  assert = require("node:assert/strict");
const root = path.resolve(__dirname, "../..");
const asset = path.join(
  root,
  "custom_components/hello_fairy_ble/frontend/library.js",
);
const html = `<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"></head><body><hello-fairy-design-library></hello-fairy-design-library><script type="module">
import '/library.js';
window.calls=[]; window.confirmations=[]; window.acceptConfirm=true; window.confirm=message=>{confirmations.push(message);return acceptConfirm};
window.data={designs:[{id:'d1',name:'Heart',design:{width:20,kind:'picture',frames:[Array(400).fill(0)]}}],playlists:[{id:'p1',name:'Evening'}],selected_playlist_id:'p1',playlist:{name:'Evening',items:[{design_id:'d1',seconds:30}],loop:false,repeat_count:1},favorites:[],layouts:[],orientations:{},status:{state:'stopped',message:'Playback stopped'}};
window.backup={format:'hello-fairy-studio-library',version:1,data:{...data}};
window.pendingValidation=false;window.validationError=false;
window.library=document.querySelector('hello-fairy-design-library'); library.addresses=['AA:BB:CC:DD:EE:02','AA:BB:CC:DD:EE:01'];
window.events=[];library.addEventListener('studio-apply-layout',event=>events.push(event.detail));
library.editor={exportDesign:()=>data.designs[0].design};
library.hass={callWS:async request=>{calls.push(structuredClone(request)); const p=request.payload||{};
if(request.action==='save_layout')data.layouts=[{id:'l1',name:p.name,addresses:p.addresses}];
if(request.action==='delete_layout')data.layouts=[];
if(request.action==='export_library')return {backup};
if(request.action==='validate_import'){if(pendingValidation)await new Promise(resolve=>window.finishValidation=resolve);if(validationError)throw new Error('Invalid backup format');return {mode:p.mode,counts:{designs:1,playlists:1,favorites:0,orientations:0,layouts:1}};}
if(request.action==='import_library')data.layouts=[{id:'imported',name:'Imported layout',addresses:['AA:BB:CC:DD:EE:01']}];
if(request.action==='pause')data.status={kind:'playlist',state:'paused',message:'Playback paused',index:0,total:1,hold_remaining_seconds:17,completed_curtains:2,total_curtains:2};
if(request.action==='resume')data.status={kind:'playlist',state:'holding',message:'Playing',hold_remaining_seconds:17};
if(request.action==='stop')data.status={state:'stopped',message:'Playback stopped'};
if(request.action==='delete_playlist'){data.playlists=[];data.selected_playlist_id=null;}
if(request.action==='status')return {status:structuredClone(data.status)};
return structuredClone(data);
}};
</script></body></html>`;
const server = http.createServer((req, res) => {
  res.setHeader(
    "Content-Type",
    req.url.startsWith("/library.js") ? "text/javascript" : "text/html",
  );
  res.end(req.url.startsWith("/library.js") ? fs.readFileSync(asset) : html);
});
let browser;
let count = 0;
(async () => {
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  browser = await chromium.launch({
    headless: true,
    channel: process.env.PW_CHANNEL || undefined,
  });
  const page = await browser.newPage({ acceptDownloads: true });
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("http://127.0.0.1:" + server.address().port);
  await page.locator("#save-layout").waitFor({ state: "attached" });
  const check = async (name, fn) => {
    await fn();
    count++;
    console.log("PASS", name);
  };
  const importFile = async (value) =>
    page.evaluate(async (value) => {
      await library._importLibrary(
        new File(
          [typeof value === "string" ? value : JSON.stringify(value)],
          "backup.json",
          { type: "application/json" },
        ),
      );
    }, value);
  await check(
    "Named layout saves the selected curtains in exact left-to-right order",
    async () => {
      await page
        .locator("#library-tools")
        .evaluate((element) => (element.open = true));
      await page.locator("#layout-name").fill("Both curtains");
      await page.locator("#save-layout").click();
      await page.waitForFunction(() => data.layouts.length === 1);
      assert.deepEqual(await page.evaluate(() => data.layouts[0].addresses), [
        "AA:BB:CC:DD:EE:02",
        "AA:BB:CC:DD:EE:01",
      ]);
    },
  );
  await check(
    "Applying layout emits targets without sending commands or overwriting the editor",
    async () => {
      const before = await page.evaluate(() => calls.length);
      await page.locator("[data-layout]").click();
      assert.equal(await page.evaluate(() => calls.length), before);
      assert.deepEqual(await page.evaluate(() => events[0]), {
        name: "Both curtains",
        addresses: ["AA:BB:CC:DD:EE:02", "AA:BB:CC:DD:EE:01"],
      });
    },
  );
  await check(
    "Complete backup downloads valid structured JSON and leaves playlist draft intact",
    async () => {
      await page.locator("#playlist-name").fill("Unsaved name");
      const downloadPromise = page.waitForEvent("download");
      await page.locator("#export-library").click();
      const download = await downloadPromise;
      assert.match(
        download.suggestedFilename(),
        /^hello-fairy-library-\d{4}-\d{2}-\d{2}\.json$/,
      );
      const stream = await download.createReadStream();
      let text = "";
      for await (const chunk of stream) text += chunk;
      assert.equal(JSON.parse(text).format, "hello-fairy-studio-library");
      assert.equal(await page.evaluate(() => library._dirty), true);
      assert.equal(
        await page.locator("#playlist-name").inputValue(),
        "Unsaved name",
      );
    },
  );
  await check(
    "Malformed JSON and over-limit files never reach server import",
    async () => {
      let before = await page.evaluate(() => calls.length);
      await importFile("{bad");
      assert.equal(await page.evaluate(() => calls.length), before);
      assert.match(
        await page.locator("#message").textContent(),
        /not valid JSON/,
      );
      await page.evaluate(() =>
        library._importLibrary(
          new File(["x".repeat(4 * 1024 * 1024 + 1)], "huge.json"),
        ),
      );
      assert.equal(await page.evaluate(() => calls.length), before);
      assert.match(await page.locator("#message").textContent(), /4 MB/);
    },
  );
  await check(
    "Server validation error preserves draft and performs no write",
    async () => {
      await page.evaluate(() => (validationError = true));
      await importFile({ format: "bad" });
      await page.evaluate(() => (validationError = false));
      assert.equal(
        await page.evaluate(
          () => calls.filter((call) => call.action === "import_library").length,
        ),
        0,
      );
      assert.equal(await page.evaluate(() => library._dirty), true);
      assert.match(
        await page.locator("#message").textContent(),
        /Invalid backup/,
      );
    },
  );
  await check(
    "Validated merge summary asks before discarding unsaved playlist changes",
    async () => {
      await page.evaluate(() => (acceptConfirm = false));
      await importFile({ format: "hello-fairy-studio-library", version: 1 });
      assert.equal(
        await page.evaluate(() => calls.at(-1).action),
        "validate_import",
      );
      assert.match(
        await page.evaluate(() => confirmations.at(-1)),
        /1 designs, 1 playlists/,
      );
      assert.match(
        await page.evaluate(() => confirmations.at(-1)),
        /Unsaved playlist changes/,
      );
      assert.equal(await page.evaluate(() => library._dirty), true);
    },
  );
  await check(
    "Import locks competing writes while validation is pending",
    async () => {
      await page.evaluate(() => {
        pendingValidation = true;
        window.importTask = library._importLibrary(
          new File([JSON.stringify(backup)], "backup.json"),
        );
      });
      await page.waitForFunction(() => !!window.finishValidation);
      assert.equal(await page.locator("#save-layout").isDisabled(), true);
      assert.equal(await page.locator("#save-design").isDisabled(), true);
      await page.evaluate(async () => {
        finishValidation();
        await importTask;
        pendingValidation = false;
      });
    },
  );
  await check(
    "Explicit replace confirms after validation and imports without altering editor picture",
    async () => {
      await page.evaluate(() => (acceptConfirm = true));
      await page.locator("#import-mode").selectOption("replace");
      await importFile({ format: "hello-fairy-studio-library", version: 1 });
      assert.deepEqual(
        await page.evaluate(() =>
          calls.slice(-2).map((call) => [call.action, call.payload.mode]),
        ),
        [
          ["validate_import", "replace"],
          ["import_library", "replace"],
        ],
      );
      assert.match(
        await page.evaluate(() => confirmations.at(-1)),
        /Replace your entire saved library/,
      );
      assert.equal(await page.evaluate(() => library._dirty), false);
      assert.equal(
        await page.evaluate(() => library.editor.exportDesign().frames[0][0]),
        0,
      );
      assert.equal(await page.locator("[data-layout]").count(), 1);
    },
  );
  await check(
    "Pause is queued during playlist upload and paused state blocks editing but allows resume/stop",
    async () => {
      await page.evaluate(() => {
        library._data.status = {
          state: "uploading",
          kind: "playlist",
          message: "Uploading",
          completed_curtains: 1,
          total_curtains: 2,
          design_name: "Heart",
          index: 0,
          total: 2,
          cycle: 1,
        };
        library._status();
        library._buttons();
      });
      assert.equal(await page.locator("#pause").isEnabled(), true);
      assert.match(
        await page.locator("#play-status").textContent(),
        /1 of 2 curtains completed/,
      );
      await page.locator("#pause").click();
      assert.equal(
        await page.locator("#pause").textContent(),
        "Resume playlist",
      );
      assert.equal(await page.locator("#save-design").isDisabled(), true);
      assert.equal(await page.locator("#import-library").isDisabled(), true);
      assert.equal(await page.locator("#next").isDisabled(), true);
      assert.equal(await page.locator("#stop").isEnabled(), true);
      assert.match(
        await page.locator("#play-status").textContent(),
        /17s hold remaining/,
      );
      assert.match(
        await page.locator("#play-status").textContent(),
        /native movement continue/,
      );
      await page.locator("#pause").click();
      assert.equal(await page.evaluate(() => calls.at(-1).action), "resume");
      await page.locator("#stop").click();
    },
  );
  await check(
    "Import is rejected during active playback before reading or sending file",
    async () => {
      await page.evaluate(() => {
        library._data.status = {
          state: "paused",
          kind: "playlist",
          message: "Paused",
        };
        library._buttons();
      });
      const before = await page.evaluate(() => calls.length);
      await importFile({});
      assert.equal(await page.evaluate(() => calls.length), before);
      assert.match(
        await page.locator("#message").textContent(),
        /Stop playback/,
      );
      await page.evaluate(() => {
        library._data.status = { state: "stopped", message: "Stopped" };
        library._buttons();
      });
    },
  );
  await check(
    "Deleting dirty playlist explicitly confirms discarded changes",
    async () => {
      await page.locator("#playlist-name").fill("Draft name");
      await page.evaluate(() => (acceptConfirm = false));
      await page.locator("#delete-playlist").click();
      assert.match(
        await page.evaluate(() => confirmations.at(-1)),
        /discard its unsaved playlist changes/,
      );
      assert.equal(await page.evaluate(() => library._dirty), true);
    },
  );
  await check(
    "Failed upload progress reports completed curtains and legacy status remains readable",
    async () => {
      await page.evaluate(() => {
        library._data.status = {
          state: "error",
          message: "Stopped on write failure",
          completed_curtains: 1,
          total_curtains: 2,
        };
        library._status();
        library._buttons();
      });
      assert.match(
        await page.locator("#play-status").textContent(),
        /1 of 2 curtains completed/,
      );
      await page.evaluate(() => {
        library._data.status = { state: "stopped", message: "Legacy mock" };
        library._status();
        library._buttons();
      });
      assert.equal(
        await page.locator("#play-status").textContent(),
        "Legacy mock",
      );
      assert.deepEqual(errors, []);
    },
  );
  console.log(count + " library finishing checks passed");
})()
  .catch((error) => {
    console.error(error);
    process.exitCode = 1;
  })
  .finally(async () => {
    if (browser) await browser.close();
    server.close();
  });
