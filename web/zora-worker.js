// ZORA's generator in a Web Worker, so the page stays responsive while a
// seed generates. Messages in: init {version, wheelUrl or wheelBytes, classic};
// check {id, bytes} (the ROM's identity);
// state {id, flags, zoraFlags}; change {id, previous, values, zoraFlags};
// zoraChange {id, flags, zoraValues}; generate {id, bytes, seed, flags,
// zoraFlags, playerSettings}; report {id, bytes (the finished ROM), seed,
// flags, zoraFlags}; multiworldCheck {id, flags, zoraFlags, playerSettings};
// nameProblem {id, name}; exportYaml {id, name, flags, zoraFlags, playerSettings}.
// Messages out: ready {ms, python, pyodide, metadata, multiworld}; result
// {id, ...} (generate's adds code, the seed code's four item names,
// codeIcons, the same as the file-select screen draws them (16 rows of 16 NES
// palette values each), and zoraFlags, the canonical ZORA string); error {id, message}.
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
import json, sys
from zora_web.api import code_icons, flag_form, generate_rom, identify_rom, multiworld, player_settings_from_page, seed_report

def identify(data):
    return json.dumps(identify_rom(bytes(data.to_py())))

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
            "encoded": result.encode_level_data, "code": [str(name) for name in result.code],
            "codeIcons": code_icons(result.rom)}
    LAST_RESULT = json.dumps(info)
    return result.rom

def report(data, seed, flag_string, zora_flag_string):
    return json.dumps(seed_report(bytes(data.to_py()), flag_string, int(seed), zora_flag_string))

def multiworld_metadata():
    return json.dumps(multiworld.metadata())

def multiworld_check(flag_string, zora_flag_string, player_settings):
    return json.dumps(multiworld.check(flag_string, zora_flag_string, json.loads(player_settings)))

def player_name_problem(name):
    return json.dumps(multiworld.player_name_problem(name))

def export_yaml(name, flag_string, zora_flag_string, player_settings):
    try:
        return json.dumps({"ok": True, **multiworld.export_yaml(name, flag_string, zora_flag_string,
                                                                json.loads(player_settings))})
    except multiworld.ExportRefused as refused:
        return json.dumps({"ok": False, "reasons": refused.reasons})

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
                metadata: JSON.parse(call("form_metadata")), multiworld: JSON.parse(call("multiworld_metadata")) });
}

// The player's ROM: zora_web.api.identify_rom's answer (PRG0 or PRG1, modified graphics or not, or
// refused), with the message the page shows. generate_rom identifies the ROM again itself.
function check({ id, bytes }) {
  postMessage({ type: "result", id, identity: JSON.parse(call("identify", bytes)) });
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

// Multiworld mode (zora_web.multiworld): whether the settings can become an Archipelago YAML, the
// player name's problem (null for none), and the YAML itself.
function multiworldCheck({ id, flags, zoraFlags, playerSettings }) {
  postMessage({ type: "result", id, verdict: JSON.parse(call("multiworld_check", flags, zoraFlags || "",
                                                             JSON.stringify(playerSettings || {}))) });
}

function nameProblem({ id, name }) {
  postMessage({ type: "result", id, problem: JSON.parse(call("player_name_problem", name)) });
}

function exportYaml({ id, name, flags, zoraFlags, playerSettings }) {
  postMessage({ type: "result", id, ...JSON.parse(call("export_yaml", name, flags, zoraFlags || "",
                                                       JSON.stringify(playerSettings || {}))) });
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
    else if (message.type === "multiworldCheck") multiworldCheck(message);
    else if (message.type === "nameProblem") nameProblem(message);
    else if (message.type === "exportYaml") exportYaml(message);
  } catch (err) {
    postMessage({ type: "error", id: message.id, message: String(err) });
  }
};
