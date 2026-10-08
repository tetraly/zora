// ZORA in the browser: the page side. Pyodide and the generator run in a
// Web Worker (zora-worker.js), so the page stays responsive while a seed
// generates. The ROM is read from a file input (never uploaded) and the
// finished ROM is offered as a download. Timings are kept on
// window.zoraTimings for measurement (docs/packaging.md).
//
// The flag controls are built from the metadata the worker sends
// (zora/flag_form.py): this file has no field list, option labels, presets
// or dependency rules of its own. Every edit goes back to Python, which
// answers with the canonical string and, per field, its value, whether it
// can change and why not. The look is web/zora.css ("Deep current",
// docs/design/web-ui-water.md); generic widgets are in widgets.js.

// The Pyodide release; ?pyodide=<version> overrides it (for the
// cross-version check in docs/packaging.md).
const PYODIDE_VERSION = new URLSearchParams(location.search).get("pyodide") || "0.28.3";
// web/build.sh names the wheel after ZORA's version and writes that name here.
const WHEEL_INFO_URL = new URL("dist/wheel.json", location.href).href;
// The single-file beta (scripts/build_site.py --single-file) carries the
// worker, the wheel and a version label inside the page, so it runs when
// opened from disk: the worker starts from a Blob URL and the wheel goes to
// it as bytes. Absent in the served site.
const EMBEDDED = document.getElementById("zora-embedded");
const EMBEDDED_INFO = EMBEDDED ? JSON.parse(EMBEDDED.textContent) : null;
const FLAGS_TYPING_DELAY_MS = 250;
const SEED_CODE_LENGTH = 4;
// A three-state field's values, and the words its segmented control shows
// ("Random" is the page's name for the spec's "possible, decided per seed").
const TOGGLE_OFF = 0;
const TOGGLE_ON = 1;
const TOGGLE_RANDOM = 2;
const TOGGLE_CHOICES = { [TOGGLE_OFF]: "Off", [TOGGLE_ON]: "On", [TOGGLE_RANDOM]: "Random" };
// The flag tabs, in order; web/flag-tabs.json maps each field id to one, and
// to its help text (docs/flag-names.csv, what_it_does). A field it does not
// name goes to the fallback tab. ZORA extras and Look and feel follow them.
const FLAG_TABS = ["Overworld", "Dungeons", "Items", "Monsters", "Misc"];
const FALLBACK_TAB = "Misc";
const ZORA_TAB = "ZORA extras";
const LOOK_TAB = "Look and feel";
const FLAG_TABS_URL = "flag-tabs.json";
const FLAG_TABS_EMBEDDED_ID = "zora-embedded-flag-tabs";
// zora.generate.NOT_PRODUCED_PREFIX: the generator's refusal of values ZORA
// does not produce yet. The page words those per field instead.
const NOT_PRODUCED_REFUSAL = "not produced: ";
const NOT_IMPLEMENTED = "Not yet implemented";
const PASTED_FLAGS = "pasted flags";
// The player's own presets: this many slots, kept in this browser.
const CUSTOM_PRESETS_KEY = "zora.customPresets";
const CUSTOM_SLOT_COUNT = 4;

const $ = (id) => document.getElementById(id);
window.zoraTimings = { seeds: [] };

// Opened from disk, Chrome refuses a MODULE worker from a Blob URL ("Refused
// to cross-origin redirects of the top-level worker script"), so the beta
// starts a classic one, which loads Pyodide with importScripts.
function startWorker() {
  if (!EMBEDDED_INFO) return new Worker("zora-worker.js", { type: "module" });
  const source = document.getElementById("zora-embedded-worker").textContent;
  return new Worker(URL.createObjectURL(new Blob([source], { type: "text/javascript" })));
}

function embeddedWheel() {
  const text = atob(document.getElementById("zora-embedded-wheel").textContent.trim());
  return Uint8Array.from(text, (ch) => ch.charCodeAt(0));
}

const worker = startWorker();
const pending = new Map();      // request id -> {resolve, reject}
let nextId = 0;
let ready = false;
let baseRom = null;             // Uint8Array of the verified base ROM
let metadata = null;            // zora.flag_form.metadata()
let form = null;                // the current zora.flag_form.form_state()
// The state the changed-dots compare with: the last preset or pasted string
// loaded ({fields: id -> value, zora: name -> value}).
let startState = null;
let startName = "";
// field id -> {kind: "select" | "segments", input (a select), buttons (value ->
// button), row, reason, value, field, supported (a Set of the values ZORA
// produces), shown (one of Consternation's fields), tab}
const controls = new Map();
// ZORA extras field name -> {kind, input, buttons, row, reason, value} (metadata.zora.fields)
const zoraControls = new Map();

function status(text, dot = null) {
  $("status").textContent = text;
  setStatusDot($("status-dot"), dot);
}

worker.onmessage = (event) => {
  const message = event.data;
  if (message.type === "ready") {
    ready = true;
    window.zoraTimings.readyMs = performance.now() - bootStart;
    window.zoraTimings.workerInitMs = message.ms;
    window.zoraTimings.python = message.python;
    window.zoraTimings.pyodide = message.pyodide;
    metadata = message.metadata;
    flagTabsRequest.then((flagTabs) => {
      buildForm(flagTabs);
      status(`Ready in ${(window.zoraTimings.readyMs / 1000).toFixed(1)} s ` +
             `(Pyodide ${message.pyodide}, Python ${message.python}). Choose the base ROM.`);
      loadFlags(metadata.defaultFlags, { rewrite: true, start: true });
    });
    return;
  }
  const request = pending.get(message.id);
  if (!request) {
    if (message.type === "error") status(`Could not load Python: ${message.message}`, "error");
    return;
  }
  pending.delete(message.id);
  if (message.type === "error") request.reject(new Error(pythonError(message.message)));
  else request.resolve(message);
};

// A Python exception arrives with its traceback; the last line is the message.
function pythonError(text) {
  const lines = text.trim().split("\n");
  return lines[lines.length - 1];
}

function ask(type, fields) {
  const id = nextId++;
  return new Promise((resolve, reject) => {
    pending.set(id, { resolve, reject });
    worker.postMessage({ type, id, ...fields });
  });
}

function element(tag, props = {}, ...children) {
  const node = Object.assign(document.createElement(tag), props);
  node.append(...children);
  return node;
}

// ---------------------------------------------------------------------------
// Text shown to the player: no spec IDs (owner, 2026-10-07)
// ---------------------------------------------------------------------------

// A field id as Python's texts write it, and a rule id ("FL-DEP-02 rule 1: ").
const FIELD_ID = /\b[BC]\d{2}\b/g;
const FIELD_ID_WITH_NAME = /\b[BC]\d{2} \(([^)]+)\)/g;
const FIELD_IDS_IN_BRACKETS = /\s*\((?:[BC]\d{2}(?:,\s*)?)+\)/g;
const RULE_ID = /(?:;\s*)?\b[A-Z]{2,}-[A-Z]{2,}-\d{2}(?: rule \d+)?(?::\s*)?/g;

// The text without spec IDs: "B10 (Change sword hearts)" keeps the name,
// "(B28, B29)" after a description goes, and a bare id becomes the field's name.
function plainText(text) {
  if (!text) return "";
  const labels = new Map((metadata ? metadata.fields : []).map((field) => [field.id, field.label]));
  return text.replace(RULE_ID, "").replace(FIELD_ID_WITH_NAME, "$1").replace(FIELD_IDS_IN_BRACKETS, "")
    .replace(FIELD_ID, (id) => labels.get(id) || "this setting");
}

// A field's name as shown: its label without spec IDs.
function fieldName(field) {
  return plainText(field.label).trim();
}

// ---------------------------------------------------------------------------
// Building the controls from the metadata
// ---------------------------------------------------------------------------

// field id -> {tab, help, hidden}, from web/flag-tabs.json. `hidden` marks the
// fields that have no effect (FL-DEP-05): they stay in the flag string for
// compatibility, but the page never shows them (owner). The single-file beta
// opened from disk cannot fetch it: it reads the copy embedded under
// FLAG_TABS_EMBEDDED_ID when the build adds one; without either, every field
// goes to the fallback tab, without help text.
async function loadFlagTabs() {
  try {
    const embedded = document.getElementById(FLAG_TABS_EMBEDDED_ID);
    if (embedded) return JSON.parse(embedded.textContent);
    const response = await fetch(FLAG_TABS_URL);
    if (!response.ok) return {};
    const mapping = await response.json();
    return mapping && typeof mapping === "object" ? mapping : {};
  } catch {
    return {};
  }
}
const flagTabsRequest = loadFlagTabs();

function tabOf(flagTabs, fieldId) {
  const tab = flagTabs[fieldId] && flagTabs[fieldId].tab;
  return FLAG_TABS.includes(tab) ? tab : FALLBACK_TAB;
}

function isHiddenField(flagTabs, fieldId) {
  return Boolean(flagTabs[fieldId] && flagTabs[fieldId].hidden);
}

function helpOf(flagTabs, field) {
  return (flagTabs[field.id] && flagTabs[field.id].help) || field.help || "";
}

// Consternation's fields: those the MVP baseline sets, i.e. whose produced
// value is not the zero one. Every other field stays hidden.
function isConsternationField(field) {
  return field.supportedValues.some((value) => value !== 0);
}

// A setting row: changed-dot, name, "?" help, the control; a reason line under it.
function settingRow(name, help, control) {
  const dot = element("span", { className: "setting-dot", ariaHidden: "true" });
  const changed = element("span", { className: "visually-hidden", textContent: " (changed)" });
  const label = element("span", { className: "setting-label", textContent: name });
  const nameBox = element("span", { className: "setting-name" }, label);
  if (help) nameBox.append(helpButton(name, plainText(help)));
  nameBox.append(changed);
  const reason = element("p", { className: "setting-reason" });
  const row = element("div", { className: "setting" }, dot, nameBox,
                      element("span", { className: "setting-control" }, control), reason);
  return { row, reason, changed };
}

let helpCount = 0;
function helpButton(name, text) {
  const tipId = `help-tip-${helpCount++}`;
  const button = element("button", { type: "button", className: "help", textContent: "?",
                                     ariaLabel: `About ${name}` });
  button.setAttribute("aria-describedby", tipId);
  const tip = element("span", { className: "tip", id: tipId, role: "tooltip", textContent: text });
  const wrap = element("span", { className: "help-wrap" }, button, tip);
  initHelpTip(wrap, tip);
  return wrap;
}

// A segmented control: one button per value, labelled by `labelOf`.
function segments(name, values, labelOf, onPick) {
  const group = element("div", { className: "seg", role: "group", ariaLabel: name });
  const buttons = new Map();
  for (const value of values) {
    const button = element("button", { type: "button", textContent: labelOf(value) });
    button.dataset.choice = labelOf(value).toLowerCase();
    button.setAttribute("aria-pressed", "false");
    button.addEventListener("click", () => onPick(value));
    group.append(button);
    buttons.set(value, button);
  }
  return { group, buttons };
}

function selectControl(id, name, values, onChange) {
  const input = element("select", { id, className: "select", ariaLabel: name });
  for (const value of values) {
    input.append(element("option", { value: String(value.value), textContent: value.label }));
  }
  input.addEventListener("change", onChange);
  return input;
}

function fieldRow(field, help, hidden) {
  let input = null;
  let buttons = null;
  let controlNode;
  if (field.kind === "option") {
    input = controlNode = selectControl(`field-${field.id}`, fieldName(field), field.values, onControlChanged);
  } else {
    ({ group: controlNode, buttons } = segments(fieldName(field), field.values.map((entry) => entry.value),
                                               (value) => TOGGLE_CHOICES[value], (value) => onToggled(field.id, value)));
    controlNode.id = `field-${field.id}`;
  }
  const { row, reason, changed } = settingRow(fieldName(field), help, controlNode);
  return { row, control: { kind: field.kind === "option" ? "select" : "segments", input, buttons, row, reason,
                           changed, value: 0, field, supported: new Set(field.supportedValues),
                           shown: !hidden && (field.id === metadata.encodeLevelData || isConsternationField(field)) } };
}

function slug(name) {
  return name.toLowerCase().replace(/[^a-z0-9]+/g, "-");
}

// A tab button and its (empty) panel.
function addTab(name) {
  const panelId = `panel-${slug(name)}`;
  const button = element("button", { type: "button", className: "tab", role: "tab",
                                     id: `tab-${slug(name)}`, textContent: name });
  button.setAttribute("aria-controls", panelId);
  const panel = element("div", { id: panelId, role: "tabpanel", hidden: true });
  panel.setAttribute("aria-labelledby", button.id);
  $("tabs").append(button);
  $("panels").append(panel);
  return panel;
}

function settingGrid() {
  return element("div", { className: "setting-grid" });
}

function buildForm(flagTabs) {
  $("version").textContent = EMBEDDED_INFO ? EMBEDDED_INFO.label : `v${metadata.version}`;
  buildPresets();
  // Each flag tab: its option fields, then its three-state fields (metadata
  // order). Encode level data is a two-state field of the Misc tab (owner).
  const grids = new Map();
  for (const name of FLAG_TABS) {
    const grid = settingGrid();
    addTab(name).append(grid);
    grids.set(name, grid);
  }
  for (const field of metadata.fields) {
    const help = field.id === metadata.encodeLevelData ? metadata.levelEncoding.help : helpOf(flagTabs, field);
    const { row, control } = fieldRow(field, help, isHiddenField(flagTabs, field.id));
    control.tab = tabOf(flagTabs, field.id);
    row.hidden = !control.shown;
    grids.get(control.tab).append(row);
    controls.set(field.id, control);
  }
  buildZoraPanel(addTab(ZORA_TAB));
  buildLookPanel(addTab(LOOK_TAB));
  initTabs($("tabs"));
  $("flags").disabled = false;
  $("zora-flags").disabled = false;
  $("form").hidden = false;
}

// ---------------------------------------------------------------------------
// ZORA extras (the ZORA flag string)
// ---------------------------------------------------------------------------

// The ZORA extras tab, from metadata.zora (zora/flags/zora_form.py): ZORA's
// own flags, carried by the ZORA flag string beside the Z1R one. The first
// switches are on or off (no Random); the owner's 2.0 flags (kind
// "three_state") are Off, On or Random, like the Z1R toggles; the hearts cap is
// a choice.
function buildZoraPanel(panel) {
  panel.append(element("p", { className: "panel-note",
    textContent: "ZORA's own settings, kept in the ZORA flag string beside the Z1R one. " +
                 "Any of them on changes the seed and its code." }));
  const grid = settingGrid();
  for (const field of metadata.zora.fields) {
    let input = null;
    let buttons = null;
    let controlNode;
    if (field.kind === "option") {
      input = controlNode = selectControl(`zora-${field.name}`, field.label, field.values, onZoraControlChanged);
    } else {
      const choices = field.kind === "three_state" ? [TOGGLE_OFF, TOGGLE_ON, TOGGLE_RANDOM] : [TOGGLE_OFF, TOGGLE_ON];
      ({ group: controlNode, buttons } = segments(field.label, choices, (value) => TOGGLE_CHOICES[value],
                                                 (value) => onZoraToggled(field.name, value)));
      controlNode.id = `zora-${field.name}`;
    }
    const { row, reason, changed } = settingRow(field.label, field.help, controlNode);
    grid.append(row);
    zoraControls.set(field.name, { kind: field.kind === "option" ? "select" : "segments", input, buttons, row,
                                   reason, changed, value: 0 });
  }
  panel.append(grid);
}

function zoraValues() {
  const values = {};
  for (const [name, control] of zoraControls) {
    values[name] = control.kind === "select" ? control.input.value : String(control.value);
  }
  return values;
}

async function onZoraControlChanged() {
  if (!form) return;
  const { state } = await ask("zoraChange", { flags: form.flags, zoraValues: zoraValues() });
  showState(state, { rewrite: true });
}

function onZoraToggled(name, value) {
  const control = zoraControls.get(name);
  if (control.value === value) return;
  control.value = value;
  onZoraControlChanged();
}

function paintSegments(buttons, value) {
  for (const [choice, button] of buttons) button.setAttribute("aria-pressed", String(choice === value));
}

function markChanged(control, changed) {
  control.row.classList.toggle("setting--changed", changed);
  control.changed.textContent = changed ? " (changed)" : "";
}

// The ZORA box and tab. Each conflict (the sword hearts, Progressive Items
// with Extra Candles) is shown at every setting it names (ZORA extras fields
// and Z1R fields alike) and blocks generation; nothing is changed for the
// player.
function showZoraState(zora, { rewrite }) {
  $("zora-flags").classList.toggle("flag-bar-input--error", !zora.ok);
  $("zora-flags-error").textContent = zora.ok ? "" : plainText(zora.error);
  if (!zora.ok) return;
  if (rewrite) $("zora-flags").value = zora.flags;
  $("zora-flags-note").textContent = $("zora-flags").value.trim() === zora.flags ? ""
    : zora.flags ? `ZORA string, canonical form: ${zora.flags}` : "ZORA string, canonical form: empty (every ZORA setting off)";
  for (const [name, control] of zoraControls) {
    control.value = zora.values[name];
    if (control.kind === "select") control.input.value = String(control.value);
    else paintSegments(control.buttons, control.value);
    control.row.classList.remove("setting--problem");
    control.reason.textContent = "";
    markChanged(control, startState !== null && startState.zora[name] !== control.value);
  }
  const messages = new Map();      // setting -> the conflicts that name it
  for (const { message, fields } of zora.conflicts) {
    for (const name of fields) messages.set(name, [...(messages.get(name) || []), plainText(message)]);
  }
  for (const [name, texts] of messages) {
    const control = zoraControls.get(name) || controls.get(name);
    if (!control) continue;
    control.row.hidden = false;
    control.row.classList.add("setting--problem");
    control.reason.textContent = texts.join(" ");
  }
}

function currentZoraFlags() {
  return $("zora-flags").value.trim();
}

// ---------------------------------------------------------------------------
// Player settings (the Look and feel tab)
// ---------------------------------------------------------------------------

// The Look and feel tab: the player's own settings (buttons, sound, colours).
// They are not part of the flag string, so two players can race the same
// flags with different settings; the page remembers them per browser, and
// they are not part of a preset. The page sends them with each generate
// request; zora.api maps them to PlayerSettings, written into the finished
// ROM (FP-SET-01).

// The NES (2C02) palette, entries $00 to $3F as RGB, emphasis bits off. Source:
// the first 64 entries of PALETTE_COLORS in src/ppu.cpp of cynes (the emulator
// ZORA's tests use), https://github.com/Youlixx/cynes, commit 6f8d3a4 (read
// 2026-10-06). Used under cynes' licence, which follows:
//
// MIT License
//
// Copyright (c) 2021 - 2025 Combey Theo
//
// Permission is hereby granted, free of charge, to any person obtaining a copy
// of this software and associated documentation files (the "Software"), to deal
// in the Software without restriction, including without limitation the rights
// to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
// copies of the Software, and to permit persons to whom the Software is
// furnished to do so, subject to the following conditions:
//
// The above copyright notice and this permission notice shall be included in all
// copies or substantial portions of the Software.
//
// THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
// IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
// FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
// AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
// LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
// OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
// SOFTWARE.
const NES_PALETTE = [
  "#545454", "#001e74", "#081090", "#300088", "#440064", "#5c0030", "#540400", "#3c1800",
  "#202a00", "#083a00", "#004000", "#003c00", "#00323c", "#000000", "#000000", "#000000",
  "#989698", "#084cc4", "#3032ec", "#5c1ee4", "#8814b0", "#a01464", "#982220", "#783c00",
  "#545a00", "#287200", "#087c00", "#007628", "#006678", "#000000", "#000000", "#000000",
  "#eceeec", "#4c9aec", "#787cec", "#b062ec", "#e454ec", "#ec58b4", "#ec6a64", "#d48820",
  "#a0aa00", "#74c400", "#4cd020", "#38cc6c", "#38b4cc", "#3c3c3c", "#000000", "#000000",
  "#eceeec", "#a8ccec", "#bcbcec", "#d4b2ec", "#ecaeec", "#ecaed4", "#ecb4b0", "#e4c490",
  "#ccd278", "#b4de78", "#a8e290", "#98e2b4", "#a0d6e4", "#a0a2a0", "#000000", "#000000",
];
// $0D is darker than black; some TVs take it for the sync signal.
const BLACKER_THAN_BLACK = 0x0D;
const EXCLUDED_COLOURS = { [BLACKER_THAN_BLACK]: "Not used: can upset TV picture sync" };

const PLAYER_SETTINGS_KEY = "zora-player-settings";

// The choices, in the order the tab shows them: [value, label] pairs, and the help text.
const PLAYER_CHOICES = [
  { key: "selectButton", label: "Select button", default: "toggle",
    choices: [["off", "Off"], ["swap", "Swap only"], ["toggle", "Toggle"]],
    help: "What Select does in play. Off: it pauses the game, as in the original. Swap only: it moves the " +
          "B button to your next item and never pauses. Toggle: you switch between the two on the item screen." },
  { key: "lowHealthBeep", label: "Low-health beep", default: "removed",
    choices: [["removed", "Removed"], ["kept", "Kept"]],
    help: "Whether the warning beep sounds while your hearts are low." },
  { key: "deathWarp", label: "Death-warp", default: "p1-up-a",
    choices: [["p2-up-a", "Controller 2 Up+A"], ["p1-up-a", "Controller 1 Up+A"],
              ["p1-up-select", "Controller 1 Up+Select"]],
    help: "The buttons that, held on the item screen, end the game and go to the Continue question. " +
          "The original game uses controller 2's Up and A." },
  { key: "reduceFlashing", label: "Reduce flashing", default: "off", choices: [["off", "Off"], ["on", "On"]],
    help: "Tones down the screen flashes, for players sensitive to flashing light." },
  { key: "music", label: "Music", default: "on", choices: [["on", "On"], ["off", "Off"]],
    help: "Turns the game's music on or off. Sound effects stay." },
];
// The colour slots, as NES palette indexes, under their headings.
const PLAYER_COLOURS = [
  { heading: "Tunic colours", slots: [
    { key: "greenTunic", label: "Green tunic", default: 0x29,
      help: "The colour of Link's tunic before he finds a ring." },
    { key: "blueRingTunic", label: "Blue ring", default: 0x32,
      help: "The colour of Link's tunic with the blue ring." },
    { key: "redRingTunic", label: "Red ring", default: 0x16,
      help: "The colour of Link's tunic with the red ring." },
  ] },
  { heading: "Heart colour", slots: [{ key: "heart", label: "Hearts", default: 0x16,
                                       help: "The colour of the hearts in the life meter." }] },
];
const COLOUR_SLOTS = PLAYER_COLOURS.flatMap((group) => group.slots);

function defaultPlayerSettings() {
  const settings = {};
  for (const choice of PLAYER_CHOICES) settings[choice.key] = choice.default;
  for (const slot of COLOUR_SLOTS) settings[slot.key] = slot.default;
  return settings;
}

function isPickableColour(value) {
  return Number.isInteger(value) && value >= 0 && value < NES_PALETTE.length && !(value in EXCLUDED_COLOURS);
}

// The saved settings, each value checked; anything unknown or missing takes its default.
function loadPlayerSettings() {
  const settings = defaultPlayerSettings();
  let saved = null;
  try { saved = JSON.parse(localStorage.getItem(PLAYER_SETTINGS_KEY) || "null"); } catch { saved = null; }
  if (!saved || typeof saved !== "object") return settings;
  for (const choice of PLAYER_CHOICES) {
    if (choice.choices.some(([value]) => value === saved[choice.key])) settings[choice.key] = saved[choice.key];
  }
  for (const slot of COLOUR_SLOTS) {
    if (isPickableColour(saved[slot.key])) settings[slot.key] = saved[slot.key];
  }
  return settings;
}

const playerSettings = loadPlayerSettings();

function savePlayerSettings() {
  try { localStorage.setItem(PLAYER_SETTINGS_KEY, JSON.stringify(playerSettings)); } catch { /* not remembered */ }
}

// A copy for the generate message.
function currentPlayerSettings() {
  return { ...playerSettings };
}

// Fills the Look and feel panel: the choices as selects, then the colour slots.
function buildLookPanel(panel) {
  panel.append(element("p", { className: "panel-note",
    textContent: "Look and feel settings change only how the game looks and sounds, so they are not part " +
                 "of the flag strings. This browser remembers them." }));
  const grid = settingGrid();
  for (const choice of PLAYER_CHOICES) {
    const select = selectControl(`player-${choice.key}`, choice.label,
                                 choice.choices.map(([value, label]) => ({ value, label })), () => {
                                   playerSettings[choice.key] = select.value;
                                   savePlayerSettings();
                                 });
    select.value = playerSettings[choice.key];
    grid.append(settingRow(choice.label, choice.help, select).row);
  }
  for (const group of PLAYER_COLOURS) {
    grid.append(element("h3", { className: "colour-heading", textContent: group.heading }));
    for (const slot of group.slots) {
      const host = element("span", { className: "setting-control" });
      initColorPicker(host, {
        palette: NES_PALETTE, excluded: EXCLUDED_COLOURS, value: playerSettings[slot.key],
        label: `${group.heading}: ${slot.label}`,
        onChange: (index) => { playerSettings[slot.key] = index; savePlayerSettings(); },
      });
      host.querySelector(".color-picker-toggle").id = `player-${slot.key}`;
      grid.append(settingRow(slot.label, slot.help, host).row);
    }
  }
  panel.append(grid);
}

// ---------------------------------------------------------------------------
// Presets: the built-in ones (metadata) and the player's own (this browser)
// ---------------------------------------------------------------------------

function presetRow(name, preview, load, extraClass = "") {
  const info = element("div", { className: "preset-info" },
    element("span", { className: "preset-name", textContent: name }),
    element("span", { className: "preset-preview", textContent: preview }));
  const button = element("button", { type: "button", className: "btn btn-tint btn-small", textContent: "Load" });
  button.addEventListener("click", load);
  return { row: element("div", { className: `preset-row ${extraClass}` }, info, button), info, button };
}

function buildPresets() {
  for (const preset of metadata.presets) {
    const { row, info, button } = presetRow(preset.label, preset.flags,
                                            () => loadPreset(preset.label, preset.flags, ""));
    button.disabled = !preset.available;
    button.title = preset.reasons.map(plainText).join("\n");
    if (!preset.available) info.append(element("span", { className: "preset-reason", textContent: plainText(preset.reason) }));
    row.dataset.label = preset.label;
    $("presets-list").append(row);
  }
  renderCustomPresets();
  $("presets-btn").disabled = false;
}

// The saved slots: CUSTOM_SLOT_COUNT entries, each {name, flags, zoraFlags}
// or null; null for the whole list when this browser keeps nothing.
function readCustomPresets() {
  try {
    const probe = `${CUSTOM_PRESETS_KEY}.probe`;
    localStorage.setItem(probe, "1");
    localStorage.removeItem(probe);
    const saved = JSON.parse(localStorage.getItem(CUSTOM_PRESETS_KEY) || "[]");
    const slots = Array.from({ length: CUSTOM_SLOT_COUNT }, (_, i) => (Array.isArray(saved) ? saved[i] : null));
    return slots.map((slot) => (slot && typeof slot.name === "string" && typeof slot.flags === "string"
      ? { name: slot.name, flags: slot.flags, zoraFlags: typeof slot.zoraFlags === "string" ? slot.zoraFlags : "" }
      : null));
  } catch {
    return null;
  }
}

function writeCustomPresets(slots) {
  try {
    localStorage.setItem(CUSTOM_PRESETS_KEY, JSON.stringify(slots));
    return true;
  } catch {
    return false;
  }
}

function renderCustomPresets() {
  const slots = readCustomPresets();
  const list = $("custom-presets");
  list.replaceChildren();
  if (slots === null) {
    $("custom-presets-note").textContent = "Your presets are unavailable: this browser is not keeping data for this page.";
  }
  for (let index = 0; index < CUSTOM_SLOT_COUNT; index++) {
    const slot = slots ? slots[index] : null;
    const number = index + 1;
    const name = element("input", { type: "text", className: "slot-name", value: slot ? slot.name : "",
                                    placeholder: slot ? "Name this preset" : "Empty slot: type a name, then Save",
                                    ariaLabel: `Name for custom preset ${number}`, disabled: slots === null });
    const detail = slot ? `${slot.flags}  ·  ZORA ${slot.zoraFlags || "none"}`
      : slots === null ? "Unavailable" : "Nothing saved yet";
    const load = element("button", { type: "button", className: "btn btn-tint btn-small", textContent: "Load",
                                     disabled: !slot });
    load.addEventListener("click", () => loadPreset(slot.name, slot.flags, slot.zoraFlags));
    const save = element("button", { type: "button", className: "btn btn-solid btn-small",
                                     textContent: slot ? "Overwrite" : "Save here", disabled: slots === null || !form });
    save.addEventListener("click", () => {
      const saved = readCustomPresets();
      if (!saved || !form) return;
      saved[index] = { name: name.value.trim() || `Custom preset ${number}`, flags: form.flags,
                       zoraFlags: form.zora.ok ? form.zora.flags : "" };
      writeCustomPresets(saved);
      renderCustomPresets();
      list.querySelectorAll(".slot-name")[index].focus();
    });
    list.append(element("div", { className: `slot${slot ? " slot--filled" : ""}` },
      element("span", { className: "slot-number", textContent: String(number) }),
      element("div", { className: "slot-info" }, name,
              element("span", { className: "preset-preview", textContent: detail })),
      element("div", { className: "slot-actions" }, load, save)));
  }
}

function openPresets() {
  renderCustomPresets();
  $("presets").showModal();
}

function closePresets() {
  if ($("presets").open) $("presets").close();
}

// A built-in or custom preset: both strings, then a fresh start for the dots.
function loadPreset(name, flags, zoraFlags) {
  closePresets();
  $("zora-flags").value = zoraFlags;
  loadFlags(flags, { rewrite: true, start: true, name });
}

// ---------------------------------------------------------------------------
// Showing a state from Python
// ---------------------------------------------------------------------------

// Whether a reason names a dependency rule (metadata.dependencyRules).
function breaksRule(reason) {
  return metadata.dependencyRules.some((rule) => reason.includes(rule.rule));
}

// Why a value cannot be picked, or undefined when it can. A value ZORA does
// not produce yet stays pickable (generation then says it is not
// implemented); a dependency rule or a missing module still blocks.
function blockedReason(id, field, value) {
  const why = field.blocked[String(value)];
  if (why === undefined) return undefined;
  const control = controls.get(id);
  const notProduced = control && !control.supported.has(value) && !breaksRule(why);
  return notProduced ? undefined : why;
}

// The label of a field's value, as the page shows it.
function valueLabel(control, value) {
  if (control.kind === "segments" && value in TOGGLE_CHOICES) return TOGGLE_CHOICES[value];
  const entry = control.field.values.find((v) => v.value === value);
  return entry ? entry.label : String(value);
}

// The field's value and its label, for "Not yet implemented: ...".
function describeValue(control, value) {
  return `${fieldName(control.field)}: ${valueLabel(control, value)}`;
}

// A value the field offers but ZORA does not produce yet. A value the field
// never offers (a pasted "?" on Encode level data) is refused instead, with
// its own reason.
function isNotImplemented(control, value) {
  return control.field.values.some((entry) => entry.value === value) && !control.supported.has(value);
}

function showField(id, control, field) {
  control.value = field.value;
  const reasons = [];      // why the other values cannot be picked
  let pickable = 0;
  const offer = (value) => {
    const why = value === field.value ? undefined : blockedReason(id, field, value);
    if (why !== undefined) reasons.push(why);
    else if (value !== field.value) pickable++;
    return why;
  };
  if (control.kind === "select") {
    control.input.value = String(field.value);
    for (const option of control.input.options) {
      const value = Number(option.value);
      const why = offer(value);
      option.disabled = why !== undefined;
      option.title = why ? plainText(why) : control.supported.has(value) ? "" : NOT_IMPLEMENTED;
    }
    control.input.disabled = pickable === 0;
  } else {
    paintSegments(control.buttons, field.value);
    for (const [value, button] of control.buttons) {
      const why = offer(value);
      button.disabled = why !== undefined;
      button.title = why ? plainText(why) : control.supported.has(value) ? "" : NOT_IMPLEMENTED;
    }
  }
  const locked = pickable === 0 && !field.problem;
  control.row.classList.toggle("setting--locked", locked);
  control.row.classList.toggle("setting--problem", field.problem);
  // A hidden field shows itself while its value needs changing (a pasted string).
  control.row.hidden = !control.shown && !field.problem;
  control.reason.textContent = field.problem
    ? (isNotImplemented(control, field.value) ? NOT_IMPLEMENTED : plainText(field.reason))
    : locked ? plainText(field.reason || reasons[0] || "") : "";
  markChanged(control, startState !== null && startState.fields[id] !== field.value);
}

// One line per field whose value ZORA does not produce yet.
function notImplementedLines(state) {
  const lines = [];
  for (const [id, control] of controls) {
    if (isNotImplemented(control, state.fields[id].value)) {
      lines.push(`${NOT_IMPLEMENTED}: ${describeValue(control, state.fields[id].value)}`);
    }
  }
  return lines;
}

function setStart(state, name) {
  startState = { fields: {}, zora: {} };
  for (const id of controls.keys()) startState.fields[id] = state.fields[id].value;
  if (state.zora.ok) Object.assign(startState.zora, state.zora.values);
  // At start-up, the preset the default string is (or "pasted flags").
  const preset = metadata.presets.find((entry) => entry.flags === state.flags);
  startName = name || (preset ? preset.label : PASTED_FLAGS);
  $("start-name").textContent = startName;
}

function showState(state, { rewrite, start = false, name = "" }) {
  if (!state.ok) {
    $("flags-error").textContent = plainText(state.error);
    $("flags").classList.add("flag-bar-input--error");
    showZoraState(state.zora, { rewrite: false });
    updateButton();
    return;
  }
  form = state;
  if (start || startState === null) setStart(state, name);
  $("flags").classList.remove("flag-bar-input--error");
  $("flags-error").textContent = state.blockedChange ? `Not changed: ${plainText(state.blockedChange)}` : "";
  if (rewrite) $("flags").value = state.flags;
  $("flags-note").textContent = $("flags").value.trim() === state.flags ? "" : `Z1R string, canonical form: ${state.flags}`;
  for (const row of $("presets-list").querySelectorAll(".preset-row")) {
    row.classList.toggle("preset-row--current", row.dataset.label === startName);
  }

  for (const [id, control] of controls) showField(id, control, state.fields[id]);
  showZoraState(state.zora, { rewrite });

  const notes = [...state.refusals.map((text) => `Rule: ${plainText(text)}`), ...state.adjustments.map(plainText)];
  const refusals = state.generateRefusals.filter((text) => !state.refusals.includes(text)
                                                       && !text.startsWith(NOT_PRODUCED_REFUSAL));
  $("problems").replaceChildren(...[...notImplementedLines(state), ...notes,
                                    ...refusals.map((text) => `Cannot generate: ${plainText(text)}`)]
    .map((text) => element("li", { textContent: text })));
  updateButton();
}

let flagsRequest = 0;
let flagsPending = false;        // the flag box changed and Python has not answered yet
// start: the loaded strings become what the changed-dots compare with, under
// `name` (a preset's), or "pasted flags".
async function loadFlags(flags, { rewrite, start = false, name = "" }) {
  const request = ++flagsRequest;
  flagsPending = true;
  const { state } = await ask("state", { flags, zoraFlags: currentZoraFlags() });
  if (request !== flagsRequest) return;
  flagsPending = false;
  showState(state, { rewrite, start, name });
}

function controlValues() {
  const values = {};
  for (const [id, control] of controls) {
    values[id] = control.kind === "select" ? control.input.value : String(control.value);
  }
  return values;
}

async function onControlChanged() {
  if (!form) return;
  const { state } = await ask("change", { previous: form.flags, values: controlValues(),
                                          zoraFlags: form.zora.ok ? form.zora.flags : currentZoraFlags() });
  showState(state, { rewrite: true });
}

function onToggled(id, value) {
  if (!form || form.fields[id].value === value) return;
  if (blockedReason(id, form.fields[id], value) !== undefined) return;
  controls.get(id).value = value;
  onControlChanged();
}

// Typing or pasting into either box loads the strings as they stand: the
// dots then compare with them ("pasted flags").
let typingTimer = null;
function onFlagsTyped() {
  clearTimeout(typingTimer);
  flagsPending = true;
  typingTimer = setTimeout(() => loadFlags($("flags").value.trim(), { rewrite: false, start: true, name: PASTED_FLAGS }),
                           FLAGS_TYPING_DELAY_MS);
  updateButton();
}

function onFlagsCommitted() {
  clearTimeout(typingTimer);
  loadFlags($("flags").value.trim(), { rewrite: true, start: true, name: PASTED_FLAGS });
}

// ---------------------------------------------------------------------------
// Seed, ROM, generation
// ---------------------------------------------------------------------------

function randomSeed() {
  const [value] = crypto.getRandomValues(new Uint32Array(1));
  $("seed").value = String(value || 1);
  updateButton();
}

function canGenerate() {
  return ready && baseRom && form && !flagsPending && $("flags-error").textContent === ""
    && form.zora.ok && form.generateRefusals.length === 0
    && /^\d+$/.test($("seed").value.trim());
}

function updateButton() {
  $("generate").disabled = !canGenerate();
  $("seed").classList.toggle("seed-input--error", !/^\d*$/.test($("seed").value.trim()));
}

const CHECK_MARK = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" ' +
  'stroke-width="2.8" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12l5 5L20 7"></path></svg>';

// A step's number circle, or a check mark once the step is done.
function markStepDone(id, number, done) {
  const circle = $(id);
  circle.classList.toggle("step-num--done", done);
  if (done) circle.innerHTML = CHECK_MARK;
  else circle.textContent = String(number);
}

async function onRomChosen() {
  baseRom = null;
  markStepDone("step-rom-num", 1, false);
  $("rom-error").textContent = "";
  updateButton();
  const file = $("rom").files[0];
  if (!file || !ready) return;
  const data = new Uint8Array(await file.arrayBuffer());
  if ((await ask("check", { bytes: data })).ok) {
    baseRom = data;
    $("rom-label").textContent = `${file.name} · verified PRG0`;
    $("rom-btn").textContent = "Change";
    markStepDone("step-rom-num", 1, true);
    status("Base ROM verified (PRG0).");
  } else {
    $("rom-label").textContent = file.name;
    $("rom-error").textContent = "That file is not the PRG0 release of The Legend of Zelda (USA); refused.";
    status("Choose the base ROM.", "error");
  }
  updateButton();
}

// Generate one seed in the worker; resolves to the finished ROM bytes.
// Also used by the measurement run described in docs/packaging.md.
async function generateSeed(seed, flags = form.flags, zoraFlags = form.zora.flags) {
  const result = await ask("generate", { bytes: baseRom, seed: String(seed), flags, zoraFlags,
                                         playerSettings: currentPlayerSettings() });
  window.zoraTimings.seeds.push({ seed: String(seed), ms: result.ms });
  return { bytes: result.rom, ms: result.ms, flags: result.flags, zoraFlags: result.zoraFlags, seed: result.seed,
           encoded: result.encoded, code: result.code };
}
window.zoraGenerateSeed = generateSeed;

// ---------------------------------------------------------------------------
// After a seed: "View in visualizer" and "Spoiler log" (encoding off only).
// Both come from one report the worker builds from the finished ROM
// (zora.api.seed_report): the seed document and the spoiler log, which
// therefore cannot disagree. Making it changes nothing in the ROM.
// ---------------------------------------------------------------------------

// The owner's Z1R Visualizer. A test may point the page elsewhere first.
const VISUALIZER_URL = "https://tetraly.github.io/z1r-visualizer/";
const VISUALIZER_PROTOCOL = 1;
// The visualizer says "ready" for up to 30 s; past that, stop listening.
const VISUALIZER_WAIT_MS = 35000;

function seedReport(result) {
  if (!result.report) {
    result.report = ask("report", { bytes: result.bytes, seed: result.seed, flags: result.flags,
                                    zoraFlags: result.zoraFlags }).then(({ report }) => report);
  }
  return result.report;
}

function showAfterSeed(text, kind = "") {
  $("after-seed").textContent = text;
  $("after-seed").className = `after-seed ${kind}`;
}

// The hand-off of docs/seed-format.md section 5, ZORA's side: listen first,
// open the visualizer with an opener (no noopener), post the seed to that
// window on each "ready", then show its answer. The window opens inside the
// click, so pop-up blockers allow it; the seed follows once the worker has it.
function viewInVisualizer(result) {
  let viz = null;
  let json = null;
  let waiting = true;
  const send = () => {
    if (viz && json !== null) viz.postMessage({ type: "z1r-seed", protocol: VISUALIZER_PROTOCOL, json }, "*");
  };
  const stop = () => { waiting = false; window.removeEventListener("message", onMessage); };
  const onMessage = (event) => {
    if (event.source !== viz || !event.data || event.data.protocol !== VISUALIZER_PROTOCOL) return;
    if (event.data.type === "z1r-seed-ready") send();
    if (event.data.type === "z1r-seed-received") {
      stop();
      showAfterSeed(event.data.ok ? "The visualizer is showing this seed."
        : `The visualizer refused the seed: ${String(event.data.error)}`, event.data.ok ? "ready" : "error");
    }
  };
  window.addEventListener("message", onMessage);
  viz = window.open(window.zoraVisualizerUrl || VISUALIZER_URL, "_blank");
  if (!viz) {
    stop();
    showAfterSeed("The browser blocked the visualizer's tab. Allow pop-ups for this page and try again.", "error");
    return;
  }
  showAfterSeed("Opening the visualizer…");
  seedReport(result).then((report) => { json = report.json; send(); })
    .catch((err) => { stop(); showAfterSeed(`No seed document: ${err.message}`, "error"); });
  setTimeout(() => {
    if (waiting) { stop(); showAfterSeed("The visualizer did not answer.", "error"); }
  }, VISUALIZER_WAIT_MS);
}

async function downloadSpoiler(result) {
  try {
    const report = await seedReport(result);
    const url = URL.createObjectURL(new Blob([report.spoiler], { type: "text/plain" }));
    const link = element("a", { href: url, download: report.spoilerName });
    document.body.append(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  } catch (err) {
    showAfterSeed(`No spoiler log: ${err.message}`, "error");
  }
}

const MAP_ICON = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" ' +
  'stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
  '<path d="M9 4L3 6v14l6-2 6 2 6-2V4l-6 2-6-2z"></path><path d="M9 4v14M15 6v14"></path></svg>';

function addSeedReportButtons(result) {
  const spoiler = element("button", { type: "button", id: "download-spoiler", className: "btn btn-outline",
                                      textContent: "Spoiler log" });
  spoiler.addEventListener("click", () => downloadSpoiler(result));
  const view = element("button", { type: "button", id: "view-visualizer", className: "btn btn-outline" });
  view.innerHTML = MAP_ICON;
  view.append("View in visualizer");
  view.addEventListener("click", () => viewInVisualizer(result));
  $("download").append(spoiler, view);
}
window.zoraViewInVisualizer = viewInVisualizer;

async function onGenerate() {
  const seed = $("seed").value.trim();
  // What the player asked for. Owner ruling: the page never shows what a
  // Random field resolved to, so the result shows these and not the resolved
  // flags. Encode level data is on or off, never Random, so `encoded` is the switch.
  const requested = { flags: form.flags, zoraFlags: form.zora.flags,
                      encoded: form.fields[metadata.encodeLevelData].value === TOGGLE_ON };
  const button = $("generate");
  button.disabled = true;
  button.replaceChildren(element("span", { className: "spinner", ariaHidden: "true" }), "Generating…");
  $("generate-result").hidden = true;
  $("download").replaceChildren();
  $("result").replaceChildren();
  $("seed-code").replaceChildren();
  $("seed-code-row").hidden = true;
  showAfterSeed("");
  markStepDone("step-generate-num", 3, false);
  status(`Generating seed ${seed}…`);
  try {
    const result = await generateSeed(seed);
    const url = URL.createObjectURL(new Blob([result.bytes], { type: "application/octet-stream" }));
    const name = `zora-seed-${result.seed}${requested.encoded ? "-encoded" : ""}.nes`;
    $("download").append(element("a", { id: "download-link", className: "btn btn-teal", href: url,
                                        download: name, title: name, textContent: "Download ROM" }));
    // A seed made with "Encode level data" stays unreadable: no spoiler, no visualizer.
    if (!requested.encoded) addSeedReportButtons(result);
    $("result").append(element("dt", { textContent: "Seed" }), element("dd", { textContent: result.seed }),
                       element("dt", { textContent: "Z1R flags" }), element("dd", { textContent: requested.flags }));
    if (requested.zoraFlags) {
      $("result").append(element("dt", { textContent: "ZORA flags" }), element("dd", { textContent: requested.zoraFlags }));
    }
    // The seed code (four item names), once Python reports one.
    if (Array.isArray(result.code) && result.code.length === SEED_CODE_LENGTH) {
      $("seed-code").append(...result.code.map((item) => element("span", { className: "seed-code-item",
                                                                            textContent: item })));
      $("seed-code-row").hidden = false;
    }
    $("gen-time").textContent = `Generated in ${(result.ms / 1000).toFixed(1)} s`;
    $("generate-result").hidden = false;
    markStepDone("step-generate-num", 3, true);
    status(`Seed ${result.seed} generated.`, "ready");
  } catch (err) {
    const notProduced = err.message.indexOf(NOT_PRODUCED_REFUSAL);
    status(notProduced < 0 ? `Generation failed: ${err.message}`
      : `${NOT_IMPLEMENTED}: ${err.message.slice(notProduced + NOT_PRODUCED_REFUSAL.length)}`, "error");
  }
  button.textContent = "Generate";
  updateButton();
}

initThemeToggle();
$("rom-btn").addEventListener("click", () => $("rom").click());
$("rom").addEventListener("change", onRomChosen);
$("presets-btn").addEventListener("click", openPresets);
$("presets-close").addEventListener("click", closePresets);
// A click on the dimmed page around the window closes it.
$("presets").addEventListener("click", (event) => {
  const box = $("presets").getBoundingClientRect();
  const outside = event.clientX < box.left || event.clientX > box.right || event.clientY < box.top || event.clientY > box.bottom;
  if (event.target === $("presets") && outside) closePresets();
});
$("seed").addEventListener("input", updateButton);
$("new-seed").addEventListener("click", randomSeed);
$("flags").addEventListener("input", onFlagsTyped);
$("flags").addEventListener("change", onFlagsCommitted);
$("zora-flags").addEventListener("input", onFlagsTyped);
$("zora-flags").addEventListener("change", onFlagsCommitted);
$("generate").addEventListener("click", onGenerate);
randomSeed();
const bootStart = performance.now();
if (EMBEDDED_INFO) {
  worker.postMessage({ type: "init", version: PYODIDE_VERSION, wheelBytes: embeddedWheel(), classic: true });
} else {
  fetch(WHEEL_INFO_URL).then((response) => response.json()).then(({ wheel }) => worker.postMessage(
    { type: "init", version: PYODIDE_VERSION, wheelUrl: new URL(`dist/${wheel}`, location.href).href }))
    .catch((err) => status(`Could not load Python: no wheel listed in dist/wheel.json (${err.message})`, "error"));
}
