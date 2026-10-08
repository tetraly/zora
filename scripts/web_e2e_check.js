// End-to-end check of the web page's flag form, run in the browser console
// (or a browser automation tool) on the served page. Not part of verify.sh.
//
// Setup (the ROM copy is for this check only; stage.sh never publishes one):
//   sh web/stage.sh temp/site
//   cp "Legend of Zelda, The (USA).nes" temp/site/e2e-base.nes
//   python3 -m http.server 8765 --bind 127.0.0.1 --directory temp/site
// Open http://127.0.0.1:8765/, wait for "Ready", paste this file into the
// console, and compare `download.sha1` with Python's output:
//   python3 -c "from zora.api import generate_rom; import hashlib; \
//     print(hashlib.sha1(generate_rom('008hq4BeR1JXo89BJ2!TFpTP02u8UJ3A', 12345, \
//     open('Legend of Zelda, The (USA).nes','rb').read()).rom).hexdigest())"
// Delete temp/site/e2e-base.nes afterwards.
(async () => {
  const FLAGS = "008hq4BeR1JXo89BJ2!TFpTP02u8UJ3A";   // CP-5, pasted with leading zeros
  const SEED = "12345";
  const $ = (id) => document.getElementById(id);
  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
  const until = async (test, limit) => {
    const start = Date.now();
    while (!test()) {
      if (Date.now() - start > limit) throw new Error("timed out");
      await sleep(100);
    }
  };
  $("flags").value = FLAGS;
  $("flags").dispatchEvent(new Event("change"));
  await until(() => $("flags").value !== FLAGS, 10000);       // rewritten to the canonical string
  const rom = new Uint8Array(await (await fetch("e2e-base.nes")).arrayBuffer());
  const files = new DataTransfer();
  files.items.add(new File([rom], "base.nes"));
  $("rom").files = files.files;
  $("rom").dispatchEvent(new Event("change"));
  await until(() => /verified/.test($("status").textContent), 10000);
  $("seed").value = SEED;
  $("seed").dispatchEvent(new Event("input"));
  $("generate").click();
  await until(() => $("download-link"), 120000);
  const link = $("download-link");
  const bytes = await (await fetch(link.href)).arrayBuffer();
  const digest = new Uint8Array(await crypto.subtle.digest("SHA-1", bytes));
  const sha1 = [...digest].map((b) => b.toString(16).padStart(2, "0")).join("");
  const download = { name: link.download, size: bytes.byteLength, sha1, shown: $("result").textContent };
  console.log(download);
  return download;
})();
