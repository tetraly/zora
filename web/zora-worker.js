// ZORA's generator in a Web Worker, so the page stays responsive while a
// seed generates. Messages in: init {version, wheelUrl or wheelBytes, classic};
// check {id, bytes};
// state {id, flags, zoraFlags}; change {id, previous, values, zoraFlags};
// zoraChange {id, flags, zoraValues}; generate {id, bytes, seed, flags,
// zoraFlags, playerSettings}; report {id, bytes (the finished ROM), seed,
// flags, zoraFlags}. Messages out: ready {ms, python, pyodide,
// metadata}; result {id, ...} (generate's adds code, the seed code's four
// item names, and zoraFlags, the canonical ZORA string); error {id, message}.
//
// A MODULE worker (zora-web.js starts it with type "module"): Pyodide's
// 314.x line refuses classic workers ("Classic web workers are not
// supported"), and importScripts hides that behind a NetworkError.
// pyodide.mjs exists for 0.28.3 too, so one loader serves both lines.

// The glue, run inside Pyodide. The flag form comes from zora_web.api.flag_form
// (fields, option labels, rules, support matrix, presets), so the page has
// no field list of its own; generation calls the same entry point as the
// native scripts (zora.generate). Results cross to JavaScript as JSON.
const GLUE = `
import hashlib, json, sys, zlib
from zora_web.api import flag_form, generate_rom, player_settings_from_page, seed_report, EXPECTED_CRC32, EXPECTED_MD5, EXPECTED_SHA1

def check_rom(data):
    data = bytes(data.to_py())
    return (hashlib.md5(data).hexdigest() == EXPECTED_MD5
            and hashlib.sha1(data).hexdigest() == EXPECTED_SHA1
            and (zlib.crc32(data) & 0xFFFFFFFF) == EXPECTED_CRC32)

def form_metadata():
    return json.dumps(flag_form.metadata())

def form_state(flag_string, zora_flag_string):
    return json.dumps(flag_form.form_state(flag_string, zora_flag_string))

def form_change(previous, values, zora_flag_string):
    return json.dumps(flag_form.form_change(previous, json.loads(values), zora_flag_string))

def zora_form_change(flag_string, zora_values):
    return json.dumps(flag_form.zora_form_change(flag_string, json.loads(zora_values)))

LAST_RESULT = "{}"

def generate(data, seed, flag_string, player_settings, zora_flag_string):
    global LAST_RESULT
    settings = player_settings_from_page(json.loads(player_settings))
    result = generate_rom(flag_string, int(seed), bytes(data.to_py()), settings, zora_flag_string)
    info = {"flags": result.flag_string, "zoraFlags": result.zora_flag_string, "seed": str(result.seed),
            "encoded": result.encode_level_data, "code": [str(name) for name in result.code]}
    LAST_RESULT = json.dumps(info)
    return result.rom

def report(data, seed, flag_string, zora_flag_string):
    return json.dumps(seed_report(bytes(data.to_py()), flag_string, int(seed), zora_flag_string))

PYTHON_VERSION = sys.version.split()[0]
`;

let pyodide = null;
const call = (name, ...args) => pyodide.globals.get(name)(...args);

async function init({ version, wheelUrl, wheelBytes, classic }) {
  const t0 = performance.now();
  const base = `https://cdn.jsdelivr.net/pyodide/v${version}/full/`;
  // classic: the single-file beta's worker (a classic one; zora-web.js says
  // why). Pyodide 0.28.3 still supports classic workers through pyodide.js.
  let loadPyodide;
  if (classic) {
    importScripts(`${base}pyodide.js`);
    loadPyodide = self.loadPyodide;
  } else {
    ({ loadPyodide } = await import(`${base}pyodide.mjs`));
  }
  pyodide = await loadPyodide();
  if (wheelBytes) {
    // The single-file beta: the wheel's bytes came with the page. zora has
    // no dependencies, so unpacking it into site-packages installs it, with
    // nothing fetched and no micropip.
    pyodide.unpackArchive(wheelBytes, "wheel");
  } else {
    await pyodide.loadPackage("micropip");
    await pyodide.pyimport("micropip").install(wheelUrl);
  }
  pyodide.runPython(GLUE);
  postMessage({ type: "ready", ms: performance.now() - t0,
                python: pyodide.globals.get("PYTHON_VERSION"), pyodide: pyodide.version,
                metadata: JSON.parse(call("form_metadata")) });
}

function check({ id, bytes }) {
  postMessage({ type: "result", id, ok: call("check_rom", bytes) });
}

function state({ id, flags, zoraFlags }) {
  postMessage({ type: "result", id, state: JSON.parse(call("form_state", flags, zoraFlags || "")) });
}

function change({ id, previous, values, zoraFlags }) {
  postMessage({ type: "result", id,
                state: JSON.parse(call("form_change", previous, JSON.stringify(values), zoraFlags || "")) });
}

function zoraChange({ id, flags, zoraValues }) {
  postMessage({ type: "result", id, state: JSON.parse(call("zora_form_change", flags, JSON.stringify(zoraValues))) });
}

// playerSettings (the Cosmetic tab) go to Python as JSON; zora_web.api maps them
// to PlayerSettings, applied after generation (FP-SET-01).
function generate({ id, bytes, seed, flags, zoraFlags, playerSettings }) {
  const t0 = performance.now();
  const result = call("generate", bytes, String(seed), flags, JSON.stringify(playerSettings || {}), zoraFlags || "");
  const rom = result.toJs();
  result.destroy();
  const info = JSON.parse(pyodide.globals.get("LAST_RESULT"));
  const ms = performance.now() - t0;
  postMessage({ type: "result", id, rom, ms, ...info }, [rom.buffer]);
}

// The seed document and spoiler log of a finished ROM (encoding off only).
function report({ id, bytes, seed, flags, zoraFlags }) {
  postMessage({ type: "result", id, report: JSON.parse(call("report", bytes, String(seed), flags, zoraFlags || "")) });
}

self.onmessage = async (event) => {
  const message = event.data;
  try {
    if (message.type === "init") await init(message);
    else if (message.type === "check") check(message);
    else if (message.type === "state") state(message);
    else if (message.type === "change") change(message);
    else if (message.type === "zoraChange") zoraChange(message);
    else if (message.type === "generate") generate(message);
    else if (message.type === "report") report(message);
  } catch (err) {
    postMessage({ type: "error", id: message.id, message: String(err) });
  }
};
