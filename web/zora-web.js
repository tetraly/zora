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
// A switch's "on" and "off" values. Each switch's states and their words (Off, On, Random) come with the
// metadata, in field.values, like an option field's.
const TOGGLE_ON = 1;
const TOGGLE_OFF = 0;
// The flag tabs, in order; web/flag-tabs.json maps each field id to one, and
// to its help text (docs/flag-names.csv, what_it_does). A field it does not
// name goes to the fallback tab. ZORA extras and Look and feel follow them.
const START_TAB = "Starting Items";
const FLAG_TABS = ["Overworld", "Dungeons", "Items", START_TAB, "Monsters", "Misc"];
const FALLBACK_TAB = "Misc";
const ZORA_TAB = "ZORA extras";
const LOOK_TAB = "Look and feel";
const CONFLICT_TAB_NOTE = "Holds a setting that conflicts with another; see the red note.";
const FLAG_TABS_URL = "flag-tabs.json";
const FLAG_TABS_EMBEDDED_ID = "zora-embedded-flag-tabs";
// zora.generate.NOT_PRODUCED_PREFIX: the generator's refusal of values ZORA
// does not produce yet. The page words those per field instead.
const NOT_PRODUCED_REFUSAL = "not produced: ";
// Generate's time limit (owner decision, 2026-10-28): most seeds take 2-3 s, and players will not wait
// much longer. A seed the page chose (the player typed none) is replaced quietly while time is left;
// a typed or linked seed is reported. Generation stops between attempts (zora/generate/deadline.py),
// so a seed that finishes in time is the same ROM with or without the limit.
const GENERATION_LIMIT_MS = 15000;
// A page-chosen seed's share: a seed that has not finished by then is replaced, so three get a try.
// (The browser is about 1.7 times slower than native Python; 5 s here is about 3 s there.)
const CHOSEN_SEED_MS = 5000;
const RETRY_MIN_MS = 1000;            // too little left for another seed: stop
const STOPPED = /GenerationStopped/;
const GENERATION_FAILED = /generation failed after/;
const NOT_IMPLEMENTED = "Not yet implemented";
// A music problem (zora.rom.music's MusicError: a library, playlist or size problem) as Python names it.
const MUSIC_PROBLEM = /^zora\.rom\.music\.(?:library|importer|playlist)\.\w+: /;
const PASTED_FLAGS = "pasted flags";
// The player's own presets: this many slots, kept in this browser. 8 since 2026-10-17 (owner; 4 before):
// a list saved with fewer slots reads as its slots followed by empty ones (readCustomPresets).
const CUSTOM_PRESETS_KEY = "zora.customPresets";
const CUSTOM_SLOT_COUNT = 8;
// How the player plays: single player (the default: generate a ROM here) or multiworld (export an
// Archipelago YAML, zora_web/multiworld.py). A shared link carries it, with both flag strings:
// ?flags=...&zora=...&mode=multiworld (and &seed=... in single player, LINK_SEED below); a default
// part is left out, so the default page's address stays bare.
const SINGLE = "single";
const MULTIWORLD = "multiworld";
const LINK_FLAGS = "flags";
const LINK_ZORA_FLAGS = "zora";
const LINK_MODE = "mode";
// The seed a shared link names (single player only): a decimal whole number below ZORA's limit,
// 2^64 (zora/generate/pipeline.py SEED_LIMIT); anything else is ignored and the seed stays random.
const LINK_SEED = "seed";
const SEED_LIMIT = 2n ** 64n;
const SHARED_LINK = "the shared link";
// zora.apworld's link comes with the metadata (zora_web.multiworld.apworld_url: this version's GitHub
// release asset). The test channel has no GitHub release until promotion: its page links the
// zora.apworld and release notes published beside it (TEST_CHANNEL_ASSETS, from the same commit;
// docs/releasing.md "Channels"). The Archipelago guide is a page beside this one (scripts/guide_page.py,
// from docs/archipelago-guide.md); a single file opened from disk has none beside it, so it links its
// channel's on the site.
const SITE_URL = "https://zora.gg/";
const CHANNEL_URL = PAGE_CHANNEL === TEST_CHANNEL ? `${SITE_URL}${TEST_CHANNEL}/` : SITE_URL;
const GUIDE_PAGE = "archipelago-guide.html";
const TEST_CHANNEL_ASSETS = { apworld: "zora.apworld", notes: "zora-apworld-notes.txt" };
const besideThisPage = (file) => (location.protocol === "file:" ? CHANNEL_URL + file : file);
const ARCHIPELAGO_GUIDE_URL = besideThisPage(GUIDE_PAGE);
const PLAYER_NAME_KEY = "zora.playerName";
const THEME_KEY = "zora-theme";         // widgets.js initThemeToggle
const TAB_KEY = "zora-tab";             // widgets.js initTabs

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
let baseRom = null;             // Uint8Array of the recognized base ROM
let romIdentity = null;         // its zora_web.api.identify_rom answer
let romChecks = 0;              // ROMs taken so far (chosen, restored or forgotten); a newer one wins
const BASE_ROM_DB = "zora-base-rom";     // IndexedDB: the remembered base ROM, this browser only
const BASE_ROM_KEY = "rom";
const ROM_LABEL = $("rom-label").textContent;     // the step's line before a ROM is chosen
const REMEMBERED_NOW = "Remembered in this browser for your next visit (never uploaded).";
const REMEMBERED_BEFORE = "Remembered from your last visit (kept in this browser, never uploaded).";
let metadata = null;            // zora.flag_form.metadata()
let form = null;                // the current zora.flag_form.form_state()
// The state the changed-dots compare with: the last preset or pasted string
// loaded ({fields: id -> value, zora: name -> value}).
let startState = null;
let startName = "";
// The start-item fields and Max Start Items, from web/flag-tabs.json (startItemRules); null without it.
let startRules = null;
let flagTabsMap = {};           // web/flag-tabs.json, once loaded (buildForm)
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
    metadata.multiworld = message.multiworld;
    showWorldLinks();
    restoreBaseRom();
    flagTabsRequest.then((flagTabs) => {
      buildForm(flagTabs);
      status(`Ready in ${(window.zoraTimings.readyMs / 1000).toFixed(1)} s ` +
             `(Pyodide ${message.pyodide}, Python ${message.python}). ` +
             (mode === MULTIWORLD ? "Choose your settings and player name."
              : baseRom ? "Base ROM remembered from your last visit." : "Choose the base ROM."));
      if (sharedLink.flags !== null || sharedLink.zoraFlags !== null) {
        $("zora-flags").value = sharedLink.zoraFlags || "";
        loadFlags(sharedLink.flags || metadata.defaultFlags, { rewrite: true, start: true, name: SHARED_LINK });
      } else {
        loadFlags(metadata.defaultFlags, { rewrite: true, start: true });
      }
      checkPlayerName();
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

// The label the metadata gives a value of a field (`values` is the field's value list).
function labelIn(values, value) {
  const entry = values.find((v) => v.value === value);
  return entry ? entry.label : String(value);
}

// The note the metadata gives a value, where its label alone could mislead ("" for none).
function noteIn(values, value) {
  const entry = values.find((v) => v.value === value);
  return (entry && entry.note) || "";
}

// A segmented control: one button per value, labeled by `labelOf`.
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
  let note = null;
  if (field.kind === "option") {
    input = controlNode = selectControl(`field-${field.id}`, fieldName(field), field.values, onControlChanged);
    if (field.values.some((entry) => entry.note)) {        // the chosen value's note, beside the select
      note = element("span", { className: "value-note" });
      controlNode = element("span", { className: "value-noted" }, note, input);
    }
  } else {
    ({ group: controlNode, buttons } = segments(fieldName(field), field.values.map((entry) => entry.value),
                                               (value) => labelIn(field.values, value),
                                               (value) => onToggled(field.id, value)));
    controlNode.id = `field-${field.id}`;
  }
  const { row, reason, changed } = settingRow(fieldName(field), help, controlNode);
  return { row, control: { kind: field.kind === "option" ? "select" : "segments", input, buttons, note, row, reason,
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
  panel.setAttribute("aria-labeledby", button.id);
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
  flagTabsMap = flagTabs;
  startRules = startItemRules(flagTabs);
  for (const name of FLAG_TABS) {
    const grid = settingGrid();
    const panel = addTab(name);
    if (name === START_TAB) panel.append(...startItemNotes());
    panel.append(grid);
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
  initFlagSummary();
  $("flags").disabled = false;
  $("zora-flags").disabled = false;
  $("form").hidden = false;
}

// ---------------------------------------------------------------------------
// Starting Items: how the start fields and Max Start Items work together (FP-START-02)
// ---------------------------------------------------------------------------

const START_ITEMS_INTRO = "Each Start setting at On adds its item to a new file; at Random, a coin decides for " +
                          "each seed. Max Start Items then sets how many of those items the player really gets: " +
                          "All keeps every one, a number keeps at most that many (picked at random, all equally " +
                          "likely), and Random draws a limit from 0 to 20 for each seed.";
const START_LIMIT_NOTE = "Max Start Items is 0, so the player starts with none of the items chosen here. " +
                         "Set Max Start Items to All or to a number to keep them.";

// flag-tabs.json marks each start-item field ("startItem") and Max Start Items, with its value that
// keeps no start items ("keepsNoStartItems"). Null when it marks no limit (the tabs did not load).
function startItemRules(flagTabs) {
  const ids = Object.keys(flagTabs);
  const limit = ids.find((id) => flagTabs[id].keepsNoStartItems !== undefined);
  if (limit === undefined) return null;
  return { items: ids.filter((id) => flagTabs[id].startItem), limit, keepsNone: flagTabs[limit].keepsNoStartItems };
}

// Whether a start field is On or Random while Max Start Items keeps none of them (`fields`: a
// form state's fields, id -> {value}).
function startItemsAllDropped(rules, fields) {
  return rules !== null && fields[rules.limit].value === rules.keepsNone
    && rules.items.some((id) => fields[id] && fields[id].value !== TOGGLE_OFF);
}

function startItemNotes() {
  return [element("p", { className: "panel-note", textContent: START_ITEMS_INTRO }),
          element("p", { id: "start-limit-note", className: "callout", role: "status", hidden: true,
                         textContent: START_LIMIT_NOTE })];
}

// ---------------------------------------------------------------------------
// The flag summary: the settings in words, one section per tab (a player request, 2026-10-26)
// ---------------------------------------------------------------------------

const SUMMARY_KEY = "zora-flag-summary";      // whether the summary is open, this browser only
// The sections' order: the tabs', but Starting Items just before Misc (owner, 2026-10-26), ZORA extras last.
const SUMMARY_ORDER = ["Overworld", "Dungeons", "Items", "Monsters", START_TAB, "Misc", ZORA_TAB];
// ZORA extras' one line when every one is Off.
const SUMMARY_NO_EXTRAS = "None";

// Each (min, max) pair (flag-tabs.json's summaryRange on the min field: its max field, and the switch it
// needs) reads as one line, "White Sword Hearts (min)" and "(max)" as "White Sword Hearts: 4 to 6". A
// pair is left out while it has no effect: the sword hearts with Change Sword Hearts Off (the caves ask
// for the usual number), the Triforce Range while the form locks it (Level 9 Entry reads no range).
// The summary's sections: [{tab, lines}], in SUMMARY_ORDER; ZORA extras always, the other tabs when not empty.
// fields: metadata.fields; flagTabs: web/flag-tabs.json; values: a form state's fields (id -> {value,
// disabled}); zora: {fields: metadata.zora.fields, values (name -> value, or null), forced}. Every
// choice field is listed; a switch only when it is On or Random; a field the page never shows only
// when it is not at its first value; a ZORA extra only when it is not Off.
function flagSummary(fields, flagTabs, values, zora) {
  const value = new Map(fields.map((field) => [field.id, values[field.id].value]));
  for (const forced of zora.forced || []) if (value.has(forced.field)) value.set(forced.field, forced.value);
  const byId = new Map(fields.map((field) => [field.id, field]));
  const name = (field) => plainText(field.label).trim();
  const ranges = new Map(fields.filter((field) => flagTabs[field.id] && flagTabs[field.id].summaryRange)
    .map((field) => [field.id, flagTabs[field.id].summaryRange]));
  const paired = new Set([...ranges.values()].map((range) => range.max));
  const lines = new Map(SUMMARY_ORDER.map((tab) => [tab, []]));
  for (const field of fields) {
    const current = value.get(field.id);
    const shown = field.id === metadata.encodeLevelData || field.supportedValues.some((v) => v !== 0);
    if (paired.has(field.id) || (flagTabs[field.id] && flagTabs[field.id].hidden)) continue;
    if (!shown && current === 0) continue;
    const tab = lines.get(tabOf(flagTabs, field.id));
    const range = ranges.get(field.id);
    if (range) {
      const max = byId.get(range.max);
      const unused = values[field.id].disabled || values[range.max].disabled
        || (range.needs && value.get(range.needs) === TOGGLE_OFF);
      if (unused) continue;
      const [low, high] = [labelIn(field.values, current), labelIn(max.values, value.get(range.max))];
      tab.push(`${name(field).replace(/ \(min\)$/, "")}: ${low === high ? low : `${low} to ${high}`}`);
    } else if (field.kind === "option") {
      tab.push(`${name(field)}: ${labelIn(field.values, current)}`);
    } else if (current !== TOGGLE_OFF) {
      tab.push(current === TOGGLE_ON ? name(field) : `${name(field)}: ${labelIn(field.values, current)}`);
    }
  }
  // A ZORA (min, max) pair (its min field's summaryRange) is one line too, left out while the extra it
  // needs is Off: Swordlish's pieces, whose max control stands at 8 with Swordlish Off.
  const zoraByName = new Map((zora.values ? zora.fields : []).map((field) => [field.name, field]));
  const zoraPaired = new Set([...zoraByName.values()].filter((field) => field.summaryRange)
    .map((field) => field.summaryRange.max));
  for (const field of zora.values ? zora.fields : []) {
    const current = Number(zora.values[field.name]);
    if (field.summaryRange) {
      const range = field.summaryRange;
      if (Number(zora.values[range.needs]) === 0) continue;
      const max = zoraByName.get(range.max);
      const [low, high] = [labelIn(field.values, current), labelIn(max.values, Number(zora.values[range.max]))];
      lines.get(ZORA_TAB).push(`${field.label.replace(/ \(min\)$/, "")}: ${low === high ? low : `${low} to ${high}`}`);
      continue;
    }
    if (current === 0 || field.hidden || zoraPaired.has(field.name)) continue;  // a hidden field's line is its own tab's
    const label = labelIn(field.values, current);
    lines.get(ZORA_TAB).push(field.kind !== "option" && current === TOGGLE_ON ? field.label : `${field.label}: ${label}`);
  }
  if (!lines.get(ZORA_TAB).length) lines.get(ZORA_TAB).push(SUMMARY_NO_EXTRAS);
  return [...lines].filter(([, tabLines]) => tabLines.length).map(([tab, tabLines]) => ({ tab, lines: tabLines }));
}

// The summary as text to paste (Discord, a race room): the strings, then each section.
function flagSummaryText(sections, flags, zoraFlags) {
  return [`Flags: ${flags}`, ...(zoraFlags ? [`ZORA flags: ${zoraFlags}`] : []),
          ...sections.flatMap(({ tab, lines }) => ["", tab, ...lines.map((line) => `- ${line}`)])].join("\n");
}

let summarySections = [];
function showFlagSummary(state) {
  const zora = { fields: metadata.zora.fields, values: state.zora.ok ? state.zora.values : null,
                 forced: state.zora.ok ? state.zora.forced : [] };
  summarySections = flagSummary(metadata.fields, flagTabsMap, state.fields, zora);
  $("flag-summary-sections").replaceChildren(...summarySections.map(({ tab, lines }) =>
    element("section", { className: "summary-section" }, element("h3", { textContent: tab }),
            element("ul", {}, ...lines.map((line) => element("li", { textContent: line }))))));
}

function initFlagSummary() {
  const details = $("flag-summary");
  details.open = getSetting(SUMMARY_KEY) === "open";
  details.addEventListener("toggle", () => setSetting(SUMMARY_KEY, details.open ? "open" : "closed"));
  $("flag-summary-copy").addEventListener("click", async () => {
    if (!form) return;
    const zoraFlags = form.zora.ok ? form.zora.flags : currentZoraFlags();
    const copied = await copyText(flagSummaryText(summarySections, form.flags, zoraFlags));
    $("flag-summary-note").textContent = copied ? "Copied." : "Your browser did not allow copying.";
  });
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
      const choices = field.values.map((entry) => entry.value);
      ({ group: controlNode, buttons } = segments(field.label, choices, (value) => labelIn(field.values, value),
                                                 (value) => onZoraToggled(field.name, value)));
      controlNode.id = `zora-${field.name}`;
    }
    const { row, reason, changed } = settingRow(field.label, field.help, controlNode);
    // A hidden field is set from another tab (Item Shuffle's Random (No Vanilla)); its control only carries the value.
    row.hidden = Boolean(field.hidden);
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

// The ZORA box and tab. Each conflict (the sword hearts, Add L4 Sword
// without Progressive Items) is shown at every setting it names (ZORA extras fields
// and Z1R fields alike), and every tab holding one of those settings turns
// red, so the player can find both halves; it blocks generation, and nothing
// is changed for the player.
function showZoraState(zora, { rewrite }) {
  markConflictTabs([]);
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
    // Multiworld mode: the values Archipelago does not take yet; single-player mode offers every one.
    const choices = control.kind === "select" ? [...control.input.options] : [...control.buttons.values()];
    const values = control.kind === "select" ? choices.map((option) => Number(option.value)) : [...control.buttons.keys()];
    choices.forEach((choice, index) => {
      const why = values[index] === control.value ? undefined : multiworldReason(name, values[index]);
      choice.disabled = why !== undefined;
      choice.title = why || "";
    });
    const refusedHere = multiworldReason(name, control.value);
    control.row.classList.toggle("setting--problem", refusedHere !== undefined);
    control.reason.textContent = refusedHere !== undefined ? `${refusedHere} Choose another value to export.` : "";
    markChanged(control, startState !== null && startState.zora[name] !== control.value);
  }
  showUnavailable(zora.unavailable || []);
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
  showWarnings(zora.warnings || [], messages);
  showForced(zora.forced || []);
  markConflictTabs(conflictTabs(zora.conflicts));
  musicLocked = Number(zora.values.disable_custom_music) === 1;     // Disable Custom Music
  refreshMusicRows();
}

// Z1R settings a ZORA setting sets whatever the Z1R string holds (Randomize Dead Woods turns Add Lost
// Woods Shortcut on): shown at that value, locked, with the note. showState repaints every Z1R
// setting first, so one no longer forced shows its own value again.
function showForced(forced) {
  for (const { field, value, message } of forced) {
    const control = controls.get(field);
    if (!control || control.kind === "select") continue;
    paintSegments(control.buttons, value);
    for (const button of control.buttons.values()) button.disabled = true;
    control.row.hidden = false;
    control.row.classList.add("setting--locked");
    control.reason.textContent = plainText(message);
  }
}

// ZORA settings that do nothing under the Z1R settings now chosen (Recorder Warping without both of the
// recorder's warps): greyed out, with the note, until the settings they need are on. The value stays.
function showUnavailable(unavailable) {
  for (const control of zoraControls.values()) control.row.classList.remove("setting--locked");
  for (const { field, message } of unavailable) {
    const control = zoraControls.get(field);
    if (!control) continue;
    const choices = control.kind === "select" ? [control.input] : [...control.buttons.values()];
    for (const choice of choices) choice.disabled = true;
    control.row.classList.add("setting--locked");
    control.reason.textContent = plainText(message);
  }
}

// Warnings: accepted settings worth a note beside each setting they name, in the plain note color (not
// red). A setting a conflict names keeps only its red note; a note already shown is not repeated.
function showWarnings(warnings, refused) {
  for (const { message, fields } of warnings) {
    const text = plainText(message);
    for (const name of fields) {
      const control = zoraControls.get(name) || controls.get(name);
      if (!control || refused.has(name) || control.reason.textContent.includes(text)) continue;
      control.row.hidden = false;
      control.reason.textContent = [control.reason.textContent, text].filter(Boolean).join(" ");
    }
  }
}

// The tabs holding a setting some conflict names: ZORA extras for ZORA's own, the flag's tab for a Z1R one.
function conflictTabs(conflicts) {
  const tabs = new Set();
  for (const { fields } of conflicts) {
    for (const name of fields) {
      if (zoraControls.has(name)) tabs.add(ZORA_TAB);
      else if (controls.has(name)) tabs.add(controls.get(name).tab);
    }
  }
  return [...tabs];
}

// The tabs named get the conflict mark; every other tab loses it.
function markConflictTabs(tabNames) {
  const marked = new Set(tabNames.map((name) => `tab-${slug(name)}`));
  for (const tab of $("tabs").querySelectorAll(".tab")) {
    const conflict = marked.has(tab.id);
    tab.classList.toggle("tab--conflict", conflict);
    tab.title = conflict ? CONFLICT_TAB_NOTE : "";
  }
}

function currentZoraFlags() {
  return $("zora-flags").value.trim();
}

// ---------------------------------------------------------------------------
// Player settings (the Look and feel tab)
// ---------------------------------------------------------------------------

// The Look and feel tab: the player's own settings (buttons, sound, colors).
// They are not part of the flag string, so two players can race the same
// flags with different settings; the page remembers them per browser, and
// they are not part of a preset. The page sends them with each generate
// request; zora_web.api maps them to PlayerSettings, written into the finished
// ROM (FP-SET-01).

// The NES (2C02) palette, entries $00 to $3F as RGB, emphasis bits off. Source:
// the first 64 entries of PALETTE_COLORS in src/ppu.cpp of cynes (the emulator
// ZORA's tests use), https://github.com/Youlixx/cynes, commit 6f8d3a4 (read
// 2026-10-06). Used under cynes' license, which follows:
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
// A color slot's Random: one past the palette (metadata.randomColor, zora/rom/player_settings.py's
// RANDOM_COLOR; needed before the worker answers, to read the saved settings).
const RANDOM_COLOR = NES_PALETTE.length;
const EXCLUDED_COLORS = { [BLACKER_THAN_BLACK]: "Not used: can upset TV picture sync" };

const PLAYER_SETTINGS_KEY = "zora-player-settings";
// The Link sprite's choices and the key of the set this browser keeps (linkSpriteRow).
const LINK_SPRITE_LINK = "link";
const LINK_SPRITE_SET = "set";
const LINK_SPRITE_RANDOM = "random";
const LINK_SPRITES = [LINK_SPRITE_LINK, LINK_SPRITE_SET, LINK_SPRITE_RANDOM];
// A built-in set's choice: this, then its id (metadata.linkSpriteSet.builtIn; the page sends it as "set"
// with the set itself, as a loaded one).
const LINK_SPRITE_BUILT_IN = "built-in:";
const LINK_SPRITE_SET_KEY = "zora-link-sprite-set";

// The choices, in the order the tab shows them: [value, label] pairs, and the help text.
const PLAYER_CHOICES = [
  { key: "selectButton", label: "Select button", default: "toggle",
    choices: [["off", "Off"], ["swap", "Swap only"], ["toggle", "Toggle"]],
    help: "What Select does in play. Off: it pauses the game, as in the original. Swap only: it moves the " +
          "B button to your next item and never pauses. Toggle: you switch between the two on the item screen." },
  { key: "lowHealthBeep", label: "Low-health beep", default: "removed",
    choices: [["removed", "Removed"], ["kept", "Kept"], ["half-speed", "Half speed"],
              ["quarter-speed", "Quarter speed"], ["random", "Random"]],
    help: "Whether the warning beep sounds while your hearts are low, and how often. Half speed: it beeps " +
          "half as often as in the original game. Quarter speed: a quarter as often. Random: removed or kept, picked by the seed number (the " +
          "same seed always gives the same)." },
  { key: "deathWarp", label: "Death-warp", default: "p1-up-a",
    choices: [["p2-up-a", "Controller 2 Up+A"], ["p1-up-a", "Controller 1 Up+A"],
              ["p1-up-select", "Controller 1 Up+Select"]],
    help: "The buttons that, held on the item screen, end the game and go to the Continue question. " +
          "The original game uses controller 2's Up and A." },
  { key: "reduceFlashing", label: "Reduce flashing", default: "off", choices: [["off", "Off"], ["on", "On"]],
    help: "Tones down the screen flashes, for players sensitive to flashing light." },
  { key: "graphicsTheme", label: "Graphics theme", default: "off", choices: [["off", "Off"], ["halloween", "Halloween"]],
    help: "Halloween: ZeroMeaning's Halloween art from Z1M1 for the overworld, the dungeons, the bosses and " +
          "Ganon, with Ganon's own colors. It changes only how the game looks: the same seed plays the same." },
  { key: "music", label: "Music", default: "on", choices: [["on", "On"], ["off", "Off"]],
    help: "Turns the game's music on or off. Sound effects stay." },
];
// Randomized music (docs/design/music-settings.md): Music's random values, which the Music row offers
// outside multiworld mode and not under the ZORA flag Disable Custom Music (Archipelago's Music is the
// list above's On and Off), and the switches shown with them. Not in PLAYER_CHOICES: Archipelago's
// player settings mirror that list, and Archipelago has no randomized music.
const MUSIC_RANDOM_CHOICES = [["random-standard", "Random (standard library)"], ["random-local", "Random (local library)"]];
const RANDOM_MUSIC = MUSIC_RANDOM_CHOICES.map(([value]) => value);
const MUSIC_HELP = "Off: no music; sound effects stay. On: the game's own music. Random (standard library): " +
  "each area (the title screen, the overworld, each level, the ending) gets a FamiTracker track from Quantam's " +
  "library, downloaded from his repository with the first " +
  "seed. Random (local library): tracks from library files you choose. Randomized music changes how often the " +
  "game lags a little, so races may turn it off with the ZORA flag Disable Custom Music.";
const MUSIC_CHOICES = [
  { key: "musicStreamingSafeOnly", label: "Streaming-safe tracks only", default: "on",
    choices: [["on", "On"], ["off", "Off"]],
    help: "Only tracks the library marks safe for streaming. Off adds the others, which may draw copyright " +
          "claims on a stream or video. A local library's track without that mark counts as safe." },
  { key: "musicHideTrackList", label: "Hide track list", default: "off", choices: [["off", "Off"], ["on", "On"]],
    help: "On: the page does not show which tracks the seed got, so you can be surprised; a button shows " +
          "them if you want to look later. It changes nothing in the ROM." },
];
// The statistics screen is no longer a choice: every ROM has it (owner, 2026-10-17). A saved
// statisticsScreen value is not loaded (loadPlayerSettings reads only these keys).
const RANDOM_TUNIC_HELP = "Random: any of the palette's colors, picked by the seed number, never a tunic above's color.";
// The color slots, as NES palette indexes, under their headings.
const PLAYER_COLORS = [
  { heading: "Tunic colors", slots: [
    { key: "greenTunic", label: "Green tunic", default: 0x29,
      help: "The color of Link's tunic before he finds a ring. " + RANDOM_TUNIC_HELP },
    { key: "blueRingTunic", label: "Blue ring", default: 0x32,
      help: "The color of Link's tunic with the blue ring. " + RANDOM_TUNIC_HELP },
    { key: "redRingTunic", label: "Red ring", default: 0x16,
      help: "The color of Link's tunic with the red ring. " + RANDOM_TUNIC_HELP },
  ] },
  // Link's colors 2 and 3 (zora/rom/player_settings.py link_other_colors): for sprite sets drawn in other
  // colors. Advanced (folded away), no Random, single player only.
  { heading: "Playable character's other colors", advanced: true, noRandom: true, slots: [
    { key: "linkColor2", label: "Color 2", default: 0x27,
      help: "The playable character's second color: Link's skin in the original art ($27; level 3 uses the " +
            "lighter $37). Changing it sets it everywhere the character is drawn, and it also changes the items " +
            "and people the game draws in the character's colors." },
    { key: "linkColor3", label: "Color 3", default: 0x17,
      help: "The playable character's third color: Link's hair, belt and shield in the original art ($17; the " +
            "file-select screen uses $07). Changing it sets it everywhere the character is drawn, and it also " +
            "changes the items and people the game draws in the character's colors." },
  ] },
  { heading: "Heart color", slots: [{ key: "heart", label: "Hearts", default: 0x16,
                                       help: "The color of the hearts in the life meter. Random: one of seven " +
                                             "colors, picked by the seed number." }] },
];
const COLOR_SLOTS = PLAYER_COLORS.flatMap((group) => group.slots);
// The Archipelago games' own settings (zora/archipelago.py MULTIWORLD_SETTINGS): shown and sent only
// in multiworld mode, where the exported YAML carries them; they change nothing in the ROM.
const MULTIWORLD_CHOICES = [
  { key: "foreignItemLook", label: "Other players' items look like", default: "rupee",
    choices: [["rupee", "A rupee"], ["logo", "The Archipelago logo"]],
    help: "How items for other players look in your game. A rupee: picking one up gives you one rupee. The " +
          "Archipelago logo: picking one up gives you nothing, and the shops' magical shields become fairies " +
          "(20 to 40 rupees)." },
  { key: "itemArrivalSound", label: "Sound when an item arrives", default: "item-appears",
    choices: [["item-appears", "Item appears"], ["item-taken", "Item taken"], ["none", "None"]],
    help: "When another player sends you an item, the game plays this sound. Item appears: the sound of an " +
          "item appearing in a room. Item taken: the sound of picking up an item. It plays over the music " +
          "and never stops Link." },
];
const ALL_CHOICES = [...PLAYER_CHOICES, ...MUSIC_CHOICES, ...MULTIWORLD_CHOICES];

// The test channel's first load (docs/releasing.md "Channels"): the regular channel's saved settings,
// copied into the test page's own keys in this page's format; the regular keys are only read, never
// written. Marked done, so later loads (or a cleared test setting) copy nothing again.
const COPIED_FROM_REGULAR_KEY = "copiedFromRegular";
function copyRegularChannelSettings(storage = localStorage, channel = PAGE_CHANNEL) {
  if (channel !== TEST_CHANNEL) return [];
  const copied = [];
  try {
    if (storage.getItem(channelKey(COPIED_FROM_REGULAR_KEY, channel)) !== null) return copied;
    const translate = {
      [PLAYER_SETTINGS_KEY]: (value) => JSON.stringify(checkedPlayerSettings(JSON.parse(value))),
      [CUSTOM_PRESETS_KEY]: (value) => JSON.stringify(checkedCustomPresets(JSON.parse(value))),
      [PLAYER_NAME_KEY]: (value) => value, [THEME_KEY]: (value) => value, [TAB_KEY]: (value) => value,
    };
    for (const [key, newer] of Object.entries(translate)) {
      const value = storage.getItem(channelKey(key, REGULAR_CHANNEL));
      if (value === null || storage.getItem(channelKey(key, channel)) !== null) continue;
      try { storage.setItem(channelKey(key, channel), newer(value)); copied.push(key); } catch { /* unreadable: left */ }
    }
    storage.setItem(channelKey(COPIED_FROM_REGULAR_KEY, channel), new Date().toISOString());
  } catch { /* this browser keeps nothing for the page */ }
  return copied;
}

// Playable character's colors (zora/rom/player_settings.py CharacterColors, shown_link_colors): a set's own, the
// default, or the player's. Picking a tunic or other color switches it to My own.
const CHARACTER_COLORS_SET = "set";
const CHARACTER_COLORS_MINE = "mine";
// The tunic and other color slots of the player's settings (defined before the settings load below).
const TUNIC_SLOTS = ["greenTunic", "blueRingTunic", "redRingTunic"];
const LINK_COLOR_SLOTS = ["linkColor2", "linkColor3"];

function defaultPlayerSettings() {
  const settings = {};
  for (const choice of ALL_CHOICES) settings[choice.key] = choice.default;
  for (const slot of COLOR_SLOTS) settings[slot.key] = slot.default;
  settings.levelWord = "LEVEL";        // metadata.levelWord.default
  settings.bossSoundWord = "ROAR";     // metadata.bossSoundWord.default
  settings.linkSprite = LINK_SPRITE_LINK;
  settings.linkSpriteSwap = "off";
  settings.characterColors = CHARACTER_COLORS_SET;
  return settings;
}

function isPickableColor(value) {
  return value === RANDOM_COLOR ||
    (Number.isInteger(value) && value >= 0 && value < NES_PALETTE.length && !(value in EXCLUDED_COLORS));
}

// The saved settings, each value checked; anything unknown or missing takes its default.
function loadPlayerSettings() {
  let saved = null;
  try { saved = JSON.parse(pageStorage.getItem(PLAYER_SETTINGS_KEY) || "null"); } catch { saved = null; }
  return checkedPlayerSettings(saved);
}

// Player settings as this page keeps them, from any earlier page's saved object: each value checked,
// anything unknown or missing at its default.
function checkedPlayerSettings(saved) {
  const settings = defaultPlayerSettings();
  if (!saved || typeof saved !== "object") return settings;
  for (const choice of ALL_CHOICES) {
    if (choice.choices.some(([value]) => value === saved[choice.key])) settings[choice.key] = saved[choice.key];
  }
  if (RANDOM_MUSIC.includes(saved.music)) settings.music = saved.music;
  for (const group of PLAYER_COLORS) {
    for (const slot of group.slots) {
      const allowed = isPickableColor(saved[slot.key]) && !(group.noRandom && saved[slot.key] === RANDOM_COLOR);
      if (allowed) settings[slot.key] = saved[slot.key];
    }
  }
  // Checked against metadata.levelWord when the panel is built (the worker sends the rule).
  if (typeof saved.levelWord === "string") settings.levelWord = saved.levelWord;
  if (typeof saved.bossSoundWord === "string") settings.bossSoundWord = saved.bossSoundWord;
  // The loaded set's choice needs the set this browser keeps (a settings file from another browser may
  // not); a built-in set's is checked against the metadata when the row is built (linkSpriteRow).
  if ((LINK_SPRITES.includes(saved.linkSprite) && (saved.linkSprite !== LINK_SPRITE_SET || loadLinkSpriteSet()))
      || (typeof saved.linkSprite === "string" && saved.linkSprite.startsWith(LINK_SPRITE_BUILT_IN))) {
    settings.linkSprite = saved.linkSprite;
  }
  if (saved.linkSpriteSwap === "on" || saved.linkSpriteSwap === "off") settings.linkSpriteSwap = saved.linkSpriteSwap;
  // A page saved before the choice: its own Link colors, if any, mean My own (player_settings.own_colors_picked).
  if (saved.characterColors === CHARACTER_COLORS_SET || saved.characterColors === CHARACTER_COLORS_MINE) {
    settings.characterColors = saved.characterColors;
  } else if ([...TUNIC_SLOTS, ...LINK_COLOR_SLOTS].some((key) =>
    settings[key] !== COLOR_SLOTS.find((slot) => slot.key === key).default)) {
    settings.characterColors = CHARACTER_COLORS_MINE;
  }
  return settings;
}

copyRegularChannelSettings();
const playerSettings = loadPlayerSettings();

function savePlayerSettings() {
  try { pageStorage.setItem(PLAYER_SETTINGS_KEY, JSON.stringify(playerSettings)); } catch { /* not remembered */ }
  refreshMultiworld();      // the YAML carries them: check them again
}

// A copy for the worker's messages; the multiworld settings only in multiworld mode. The Link sprite
// only outside it (Archipelago's player settings do not offer it), with the loaded set when the choice
// uses it (withSet: the settings file keeps the choice alone).
function currentPlayerSettings(withSet = true) {
  const settings = { ...playerSettings };
  if (mode !== MULTIWORLD) for (const choice of MULTIWORLD_CHOICES) delete settings[choice.key];
  // The swap only with a person set that has one (zora/rom/link_art.py has_swap); Random never swaps.
  if (!linkSpriteHasSwap(settings.linkSprite)) settings.linkSpriteSwap = "off";
  if (mode === MULTIWORLD) {
    delete settings.linkSprite;
    delete settings.linkSpriteSwap;
    delete settings.characterColors;
    for (const key of LINK_COLOR_SLOTS) delete settings[key];
  } else if (settings.linkSprite.startsWith(LINK_SPRITE_BUILT_IN)) {
    const builtIn = builtInLinkSpriteSet(settings.linkSprite);
    settings.linkSprite = builtIn ? LINK_SPRITE_SET : LINK_SPRITE_LINK;
    if (withSet && builtIn) settings.linkSpriteSet = builtIn;
  } else if (withSet && settings.linkSprite !== LINK_SPRITE_LINK) {
    settings.linkSpriteSet = loadLinkSpriteSet();
  }
  return settings;
}

// A choice's select, kept in playerSettings and this browser.
function choiceRow(choice) {
  const select = selectControl(`player-${choice.key}`, choice.label,
                               choice.choices.map(([value, label]) => ({ value, label })), () => {
                                 playerSettings[choice.key] = select.value;
                                 savePlayerSettings();
                               });
  select.value = playerSettings[choice.key];
  return settingRow(choice.label, choice.help, select).row;
}

// Fills the Look and feel panel: the choices as selects, then the Music section, then the Colors section.
function buildLookPanel(panel) {
  panel.append(element("p", { className: "panel-note",
    textContent: "Look and feel settings change only how the game looks and sounds, so they are not part " +
                 "of the flag strings. This browser remembers them." }));
  const grid = settingGrid();
  for (const choice of PLAYER_CHOICES) if (choice.key !== "music") grid.append(choiceRow(choice));
  grid.append(levelWordRow());
  grid.append(bossSoundWordRow());
  grid.append(element("h3", { className: "setting-heading", textContent: "Music" }));
  grid.append(musicRow(PLAYER_CHOICES.find((choice) => choice.key === "music")));
  for (const choice of MUSIC_CHOICES) {
    const row = choiceRow(choice);
    row.classList.add("music-random-only");
    // The playlist editor marks unsafe songs by this switch.
    row.querySelector("select").addEventListener("change", refreshMusicPlaylistEditor);
    grid.append(row);
  }
  grid.append(musicLibraryRow(), musicPlaylistRow());
  // The playable character's sprite and its colors together: the sprite, then the tunic colors, the
  // character's other colors (advanced, folded away), and the hearts.
  grid.append(element("h3", { className: "setting-heading", textContent: "Playable character and colors" }));
  grid.append(linkSpriteRow());
  const markerNote = element("p", { id: "marker-note", className: "panel-note color-note", textContent: MARKER_NOTE });
  for (const group of PLAYER_COLORS) {
    const rows = group.slots.map((slot) => {
      const host = element("span", { className: "setting-control" });
      const show = initColorPicker(host, {
        palette: NES_PALETTE, excluded: EXCLUDED_COLORS, value: playerSettings[slot.key],
        label: `${group.heading}: ${slot.label}`, random: group.noRandom ? null : metadata.randomColor,
        onChange: (index) => {
          playerSettings[slot.key] = index;
          // A Link color picked is the player's own: the set's colors no longer apply.
          if (TUNIC_SLOTS.includes(slot.key) || LINK_COLOR_SLOTS.includes(slot.key)) {
            playerSettings.characterColors = CHARACTER_COLORS_MINE;
          }
          savePlayerSettings();
          showLinkSpriteInfo();
          showColorChange(markerNote);
        },
      });
      colorPickers.set(slot.key, show);
      host.querySelector(".color-picker-toggle").id = `player-${slot.key}`;
      return settingRow(slot.label, slot.help, host).row;
    });
    if (group.advanced) {
      const advanced = element("details", { id: "link-colors-advanced", className: "advanced-colors single-only" },
        element("summary", { textContent: `Advanced: ${group.heading}` }),
        element("p", { className: "panel-note", textContent: "For sprite sets drawn in other colors. These " +
          "also change the items and people the game draws in the playable character's colors." }),
        element("div", { className: "setting-grid" }, ...rows));
      advanced.open = LINK_COLOR_SLOTS.some((key, index) => playerSettings[key] !== metadata.linkSpriteSet.fixedColors[index]);
      grid.append(advanced);
    } else {
      grid.append(...rows);
    }
    if (group.slots.some((slot) => TUNIC_SLOTS.includes(slot.key))) grid.append(markerNote);
  }
  showMarkerNote(markerNote);
  grid.append(element("h3", { className: "setting-heading multiworld-only", textContent: "Multiworld" }));
  for (const choice of MULTIWORLD_CHOICES) {
    const row = choiceRow(choice);
    row.classList.add("multiworld-only");
    grid.append(row);
  }
  panel.append(grid);
  showMultiworldSettings();
}

// The multiworld settings' rows show only in multiworld mode, the single-player ones only outside it.
function showMultiworldSettings() {
  for (const node of document.querySelectorAll(".multiworld-only")) node.hidden = mode !== MULTIWORLD;
  for (const node of document.querySelectorAll(".single-only")) node.hidden = mode === MULTIWORLD;
  refreshMusicRows();
}

// ---------------------------------------------------------------------------
// Randomized music (docs/design/music-settings.md): the Music row, the local library, the playlist
// ---------------------------------------------------------------------------

const MUSIC_PLAYLIST_KEY = "zora-music-playlist";
const MUSIC_TAGGED_ONLY_KEY = "zora-music-playlist-tagged-only";   // the editor's Only show tagged tracks
const MUSIC_LIBRARY_DB = "zora-music-library";     // IndexedDB: the local library's files, this browser only
let musicSelect = null;
let musicLibraryFiles = [];                         // [{name, bytes}], read from the files the player chose
let musicPlaylist = loadMusicPlaylist();            // area key -> a song's title or "original"
let musicPlaylistEditor = null;                     // the Playlist row's editor (hidden until opened)
let musicPlaylistFills = 0;                         // the editor's fills so far: only the latest one shows
let musicTaggedOnly = loadMusicTaggedOnly();        // the editor lists only the songs tagged for each area
let musicLocked = false;                            // the ZORA flag Disable Custom Music is on
let musicPlaylistSummary = null;                    // the Playlist row's "n areas pinned"
let musicLibraryShown = null;                       // the Library row's list of files
let musicLibraryNotes = null;                       // the Library row's problem and warnings
let musicLibraryCheck = null;                       // {problem, warnings} of the chosen files, once checked
let musicLibraryChecks = 0;                         // the checks so far: only the latest one counts

// The Music row: the list's On and Off, then the random values.
function musicRow(choice) {
  const values = [...choice.choices, ...MUSIC_RANDOM_CHOICES].map(([value, label]) => ({ value, label }));
  musicSelect = selectControl(`player-${choice.key}`, choice.label, values, () => {
    playerSettings.music = musicSelect.value;
    savePlayerSettings();
    refreshMusicRows();
    refreshMusicPlaylistEditor();
  });
  musicSelect.value = playerSettings.music;
  return settingRow(choice.label, MUSIC_HELP, musicSelect).row;
}

// Random music is offered outside multiworld mode, and not under Disable Custom Music (a race setting).
function randomMusicAllowed() {
  return mode !== MULTIWORLD && !musicLocked;
}

function randomMusicChosen() {
  return RANDOM_MUSIC.includes(playerSettings.music);
}

// The random values disabled where they are not offered (a chosen one falls back to On), and the rows
// that go with them shown only while one is chosen.
function refreshMusicRows() {
  if (!musicSelect) return;
  const allowed = randomMusicAllowed();
  for (const option of musicSelect.options) {
    if (RANDOM_MUSIC.includes(option.value)) option.disabled = !allowed;
  }
  if (!allowed && randomMusicChosen()) {
    playerSettings.music = "on";
    musicSelect.value = "on";
    try { pageStorage.setItem(PLAYER_SETTINGS_KEY, JSON.stringify(playerSettings)); } catch { /* not remembered */ }
  }
  for (const node of document.querySelectorAll(".music-random-only")) node.hidden = !randomMusicChosen();
  for (const node of document.querySelectorAll(".music-local-only")) node.hidden = playerSettings.music !== "random-local";
  showMusicLibrary();
  updateButton();
}

// The local library: a folder (every .json5 file in it) or files, read into memory and kept in this
// browser (IndexedDB) for the next visit; never uploaded.
function musicLibraryRow() {
  const folder = element("input", { type: "file", hidden: true, multiple: true });
  folder.setAttribute("webkitdirectory", "");
  const files = element("input", { type: "file", hidden: true, multiple: true, accept: ".json5" });
  for (const input of [folder, files]) input.addEventListener("change", () => chooseMusicLibrary(input.files));
  const pickFolder = element("button", { type: "button", className: "btn btn-tint btn-small", textContent: "Choose folder…" });
  const pickFiles = element("button", { type: "button", className: "btn btn-tint btn-small", textContent: "Choose files…" });
  pickFolder.addEventListener("click", () => folder.click());
  pickFiles.addEventListener("click", () => files.click());
  const shown = element("span", { id: "music-library-files", className: "panel-note" });
  musicLibraryShown = shown;
  musicLibraryNotes = element("span", { className: "music-library-notes" });
  const control = element("span", { className: "music-library" }, pickFolder, pickFiles, folder, files, shown,
                          musicLibraryNotes);
  const { row } = settingRow("Library", "FtRandoLib library files (.json5), the format of Quantam's standard " +
    "library: FamiTracker modules with each song's title and the areas it fits (Title for the title screen; a " +
    "library with no Title track leaves the game's own title song there). Zelda II Randomizer's libraries " +
    "work too: their towns play on the overworld, palaces, caves and battles in levels 1-8, the great palace and " +
    "bosses in level 9, the credits at the ending. Recorded audio (MP3, WAV) and plain .ftm files cannot be used. " +
    "The files stay in this browser.", control);
  row.classList.add("music-random-only", "music-local-only", "setting--wide");
  restoreMusicLibrary();
  return row;
}

async function chooseMusicLibrary(fileList) {
  const chosen = [...fileList].filter((file) => file.name.toLowerCase().endsWith(".json5"))
    .sort((a, b) => (a.webkitRelativePath || a.name).localeCompare(b.webkitRelativePath || b.name));
  musicLibraryFiles = await Promise.all(chosen.map(async (file) => ({
    name: file.name, bytes: new Uint8Array(await file.arrayBuffer()) })));
  storeMusicLibrary();
  showMusicLibrary();
  refreshMusicPlaylistEditor();
  updateButton();
  checkMusicLibrary();
}

function showMusicLibrary() {
  const shown = musicLibraryShown;
  if (!shown) return;
  shown.textContent = musicLibraryFiles.length
    ? `${musicLibraryFiles.length} file${musicLibraryFiles.length === 1 ? "" : "s"}: ${musicLibraryFiles.map((file) => file.name).join(", ")}`
    : "No library chosen: choose a folder or files to generate.";
  const check = musicLibraryFiles.length ? musicLibraryCheck : null;
  musicLibraryNotes.replaceChildren(
    ...(check && check.problem ? [element("p", { className: "setting-reason music-library-problem",
                                                 textContent: `This library cannot be used: ${check.problem}` })] : []),
    ...(check ? check.warnings : []).map((warning) => element("p", { className: "setting-reason", textContent: warning })));
}

// The chosen files read as a seed would read them, before Generate: a library with nothing to place
// stops Generate with the reason; tracks or uses left out are listed. A check that cannot run (Python
// still loading) blocks nothing: generating reports the same problem.
async function checkMusicLibrary() {
  const check = ++musicLibraryChecks;
  musicLibraryCheck = null;
  if (musicLibraryFiles.length) {
    let result = null;
    try {
      const answer = await ask("musicSongs", { source: "local", musicLibraries: musicLibraryFiles });
      result = answer.error ? { problem: answer.error, warnings: [] } : { problem: null, warnings: answer.warnings || [] };
    } catch { /* not checked */ }
    if (check !== musicLibraryChecks) return;      // a newer choice replaces this one
    musicLibraryCheck = result;
  }
  showMusicLibrary();
  updateButton();
}

// One of this browser's own databases (IndexedDB), on this machine only. Resolves to null where
// storage is unavailable (a private window, storage turned off) or the request fails.
function browserStore(database, mode, work) {
  return new Promise((resolve) => {
    try {
      const request = indexedDB.open(database, 1);
      request.onupgradeneeded = () => request.result.createObjectStore("files");
      request.onerror = () => resolve(null);
      request.onsuccess = () => {
        try {
          const store = request.result.transaction("files", mode).objectStore("files");
          work(store, resolve);
        } catch { resolve(null); }
      };
    } catch { resolve(null); }
  });
}

function musicLibraryStore(mode, work) {
  return browserStore(MUSIC_LIBRARY_DB, mode, work);
}

function storeMusicLibrary() {
  musicLibraryStore("readwrite", (store, done) => {
    const put = store.put(musicLibraryFiles, "library");
    put.onsuccess = put.onerror = () => done(null);
  });
}

async function restoreMusicLibrary() {
  const saved = await musicLibraryStore("readonly", (store, done) => {
    const get = store.get("library");
    get.onsuccess = () => done(get.result || null);
    get.onerror = () => done(null);
  });
  if (Array.isArray(saved) && !musicLibraryFiles.length) {
    musicLibraryFiles = saved.filter((file) => file && typeof file.name === "string" && file.bytes instanceof Uint8Array);
    showMusicLibrary();
    refreshMusicPlaylistEditor();
    updateButton();
    checkMusicLibrary();
  }
}

// The playlist: songs pinned to areas on top of the random draw. Kept in this browser; imported and
// exported as a JSON5 file ({ version: 1, tracks: { area: title or "original" } }).
function loadMusicPlaylist() {
  try {
    const saved = JSON.parse(pageStorage.getItem(MUSIC_PLAYLIST_KEY) || "null");
    if (saved && typeof saved === "object") {
      return Object.fromEntries(Object.entries(saved).filter(([, value]) => typeof value === "string"));
    }
  } catch { /* none */ }
  return {};
}

function loadMusicTaggedOnly() {
  try { return pageStorage.getItem(MUSIC_TAGGED_ONLY_KEY) === "on"; } catch { return false; }
}

function saveMusicTaggedOnly() {
  try { pageStorage.setItem(MUSIC_TAGGED_ONLY_KEY, musicTaggedOnly ? "on" : "off"); } catch { /* not remembered */ }
}

// The songs an area's select lists, each with its notes: every song, or under Only show tagged tracks
// (TheGobOne's request, 2026-10-25) only those tagged for the area, and the pinned one whatever it is,
// so a pin never disappears from its select.
function playlistChoices(area, songs, taggedOnly, pinned) {
  return songs.map((song) => ({ song, tagged: area.uses.some((use) => song.uses.includes(use)) }))
    .filter(({ song, tagged }) => tagged || !taggedOnly || song.title === pinned)
    .map(({ song, tagged }) => ({ song, notes: [tagged ? "" : "not tagged for this area",
                                                song.safe ? "" : "unsafe for streaming"].filter(Boolean) }));
}

function saveMusicPlaylist() {
  try { pageStorage.setItem(MUSIC_PLAYLIST_KEY, JSON.stringify(musicPlaylist)); } catch { /* not remembered */ }
}

function musicPlaylistText() {
  return Object.keys(musicPlaylist).length ? JSON.stringify({ version: 1, tracks: musicPlaylist }, null, 2) : null;
}

function musicPlaylistRow() {
  const summary = element("span", { id: "music-playlist-summary", className: "panel-note" });
  musicPlaylistSummary = summary;
  const edit = element("button", { type: "button", className: "btn btn-tint btn-small", textContent: "Edit playlist…" });
  const importInput = element("input", { type: "file", hidden: true, accept: ".json5,.json" });
  const importButton = element("button", { type: "button", className: "btn btn-tint btn-small", textContent: "Import…" });
  const exportButton = element("button", { type: "button", className: "btn btn-tint btn-small", textContent: "Export" });
  const clear = element("button", { type: "button", className: "btn btn-tint btn-small", textContent: "Clear" });
  const editor = element("div", { id: "music-playlist-editor", className: "music-playlist", hidden: true });
  musicPlaylistEditor = editor;
  edit.addEventListener("click", () => openMusicPlaylistEditor(editor));
  importButton.addEventListener("click", () => importInput.click());
  importInput.addEventListener("change", () => importMusicPlaylist(importInput, editor));
  exportButton.addEventListener("click", exportMusicPlaylist);
  clear.addEventListener("click", () => {
    musicPlaylist = {};
    saveMusicPlaylist();
    showMusicPlaylist(editor);
  });
  const control = element("span", { className: "music-playlist-buttons" }, edit, importButton, importInput, exportButton,
                          clear, summary);
  const { row } = settingRow("Playlist", "Pin a song to any area: the title screen, the overworld, each level or " +
    "the ending. Areas left on Random are drawn from the library as usual; Original puts the game's own song " +
    "there. A song marked unsafe for streaming needs Streaming-safe tracks only off.",
    element("span", { className: "music-playlist-control" }, control, editor));
  row.classList.add("music-random-only", "setting--wide");
  showMusicPlaylist(editor);
  return row;
}

function showMusicPlaylist(editor) {
  showMusicPlaylistSummary();
  if (!editor.hidden) fillMusicPlaylistEditor(editor);
}

function showMusicPlaylistSummary() {
  const pinned = Object.keys(musicPlaylist).length;
  musicPlaylistSummary.textContent = pinned ? `${pinned} area${pinned === 1 ? "" : "s"} pinned` : "No playlist";
}

async function openMusicPlaylistEditor(editor) {
  editor.hidden = !editor.hidden;
  if (!editor.hidden) await fillMusicPlaylistEditor(editor);
}

// An open editor lists the songs of the library Music chooses, and marks them by Streaming-safe tracks
// only, so it is filled again when either changes or the local library's files do.
function refreshMusicPlaylistEditor() {
  if (musicPlaylistEditor && !musicPlaylistEditor.hidden && randomMusicChosen()) fillMusicPlaylistEditor(musicPlaylistEditor);
}

// Only show tagged tracks, then one select per area: Random, Original, then the chosen library's songs
// (playlistChoices: a song unsafe for streaming disabled while Streaming-safe tracks only is on; one
// not tagged for the area marked so, or left out under Only show tagged tracks).
async function fillMusicPlaylistEditor(editor) {
  const source = playerSettings.music === "random-local" ? "local" : "standard";
  const fill = ++musicPlaylistFills;
  editor.replaceChildren(element("p", { className: "panel-note", textContent: "Loading the library's songs…" }));
  let areas, songs;
  try {
    ({ areas } = await ask("musicAreas", {}));
    const answer = await ask("musicSongs", { source, musicLibraries: musicLibraryFiles });
    if (answer.error) throw new Error(answer.error);
    songs = answer.songs;
  } catch (err) {
    if (fill !== musicPlaylistFills) return;
    editor.replaceChildren(element("p", { className: "setting-reason", textContent: `No songs: ${err.message}` }));
    return;
  }
  if (fill !== musicPlaylistFills) return;      // a newer fill (another library or switch) replaces this one
  const safeOnly = playerSettings.musicStreamingSafeOnly !== "off";
  const taggedOnly = element("input", { type: "checkbox", id: "music-tagged-only", checked: musicTaggedOnly });
  taggedOnly.addEventListener("change", () => {
    musicTaggedOnly = taggedOnly.checked;
    saveMusicTaggedOnly();
    fillMusicPlaylistEditor(editor);
  });
  const rows = areas.map((area) => {
    const select = element("select", { className: "select", ariaLabel: `Playlist: ${area.label}` });
    select.append(element("option", { value: "random", textContent: "Random" }),
                  element("option", { value: "original", textContent: "Original" }));
    const pinned = musicPlaylist[area.key];
    for (const { song, notes } of playlistChoices(area, songs, musicTaggedOnly, pinned)) {
      select.append(element("option", { value: song.title, disabled: safeOnly && !song.safe,
                                        textContent: notes.length ? `${song.title} (${notes.join("; ")})` : song.title }));
    }
    // A pin the chosen library does not have stays visible (generating would refuse it), not shown as Random.
    if (pinned && pinned !== "original" && !songs.some((song) => song.title === pinned)) {
      select.append(element("option", { value: pinned, textContent: `${pinned} (not in this library)` }));
    }
    select.value = pinned || "random";
    select.addEventListener("change", () => {
      if (select.value === "random") delete musicPlaylist[area.key];
      else musicPlaylist[area.key] = select.value;
      saveMusicPlaylist();
      showMusicPlaylistSummary();
    });
    return element("label", { className: "music-playlist-area" }, element("span", { textContent: area.label }), select);
  });
  editor.replaceChildren(element("label", { className: "music-tagged-only" }, taggedOnly, " Only show tagged tracks"),
                         ...rows);
}

async function importMusicPlaylist(input, editor) {
  const [file] = input.files;
  input.value = "";
  if (!file) return;
  try {
    // JSON5 as ZORA writes it is JSON; comments, unquoted keys and trailing commas are read too.
    const text = (await file.text()).replace(/^\s*\/\/.*$/gm, "").replace(/([{,]\s*)([A-Za-z_]\w*)(\s*:)/g, '$1"$2"$3')
      .replace(/,(\s*[}\]])/g, "$1");
    const parsed = JSON.parse(text);
    if (!parsed || typeof parsed.tracks !== "object") throw new Error("not a playlist (no tracks)");
    musicPlaylist = Object.fromEntries(Object.entries(parsed.tracks)
      .filter(([, value]) => typeof value === "string" && value !== "random"));
    saveMusicPlaylist();
    showMusicPlaylist(editor);
    status(`Playlist ${file.name} imported.`, "ready");
  } catch (err) {
    status(`Playlist not imported: ${err.message}`, "error");
  }
}

function exportMusicPlaylist() {
  const text = musicPlaylistText() || JSON.stringify({ version: 1, tracks: {} }, null, 2);
  const url = URL.createObjectURL(new Blob([text + "\n"], { type: "application/json5" }));
  const link = element("a", { href: url, download: "zora-playlist.json5" });
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

// Random (local library) needs a library, one with tracks to place, before a seed can be generated.
function musicReady() {
  if (!(randomMusicChosen() && playerSettings.music === "random-local")) return true;
  return musicLibraryFiles.length > 0 && !(musicLibraryCheck && musicLibraryCheck.problem);
}

// The level label's word (FP-LEVEL-01): a listed word or the player's own. The rule is
// metadata.levelWord, zora/rom/player_settings.py's (tests/test_level_word.py runs this function
// in Node against Python's level_word_problem).
const LEVEL_WORD_HELP = "The word the status bar and the hints show before a level's number in place of LEVEL. " +
                        "Words of up to six characters keep the dash (CASTLE-1); seven-character words drop it to " +
                        "fit (DUNGEON1). Random: one of the listed words, picked by the seed number (the same seed " +
                        "always shows the same word).";

function normalizedLevelWord(text) {
  return text.trim().toUpperCase();
}

function levelWordProblem(word, rule) {
  if (word === rule.random) return null;
  if (!word) return "type a word";
  if (word.length > rule.maxLength) return `at most ${rule.maxLength} characters`;
  const unknown = [...new Set([...word].filter((char) => !rule.characters.includes(char)))].sort();
  if (unknown.length) return `the game's font has no ${unknown.join(" ")}`;
  return null;
}

function levelLabel(word, rule) {
  return `${word}${word.length <= rule.dashMaxLength ? "-" : ""}1`;
}

function levelWordRow() {
  const rule = metadata.levelWord;
  const random = "a listed word, picked by the seed number";
  return wordChoiceRow({
    key: "levelWord", name: "Level name", help: LEVEL_WORD_HELP, maxLength: rule.maxLength,
    defaultWord: rule.default,
    options: [...rule.choices.map((word) => ({ value: word, label: word })), { value: rule.random, label: "Random" }],
    problem: (word) => levelWordProblem(word, rule),
    shows: (word) => (word === rule.random ? `Shows ${random}.` : `Shows as ${levelLabel(word, rule)}` +
                      (word.length > rule.dashMaxLength ? " (seven characters: no room for the dash)." : ".")),
    keeps: (word) => (word === rule.random ? random : levelLabel(word, rule)),
  });
}

// The boss-sound label's word (FP-ROAR-01): " -ROAR-  " in -LIFE-'s place while a dungeon room's
// boss sound plays. ROAR, Random (a listed word chosen by the seed number), a listed word or the
// player's own four characters; the rule is metadata.bossSoundWord (tests/test_boss_sound_word.py
// runs bossSoundWordProblem in Node against Python's).
const BOSS_SOUND_WORD_HELP = "In a dungeon room where you hear a boss, the status bar's -LIFE- label changes to " +
                             "-ROAR-. Choose another four-letter word, your own, or Random: one of the listed " +
                             "words, picked by the seed number (the same seed always shows the same word).";

function bossSoundWordProblem(word, rule) {
  if (word === rule.random) return null;
  if (word.length !== rule.length) return `exactly ${rule.length} characters`;
  const unknown = [...new Set([...word].filter((char) => !rule.characters.includes(char)))].sort();
  if (unknown.length) return `the game's font has no ${unknown.join(" ")}`;
  return null;
}

function bossSoundWordRow() {
  const rule = metadata.bossSoundWord;
  const label = (word) => (word === rule.random ? "a listed word, picked by the seed number" : `-${word}-`);
  return wordChoiceRow({
    key: "bossSoundWord", name: "Boss-sound label", help: BOSS_SOUND_WORD_HELP, maxLength: rule.length,
    defaultWord: rule.default,
    options: [{ value: rule.default, label: rule.default }, { value: rule.random, label: "Random" },
              ...rule.choices.map((word) => ({ value: word, label: word }))],
    problem: (word) => bossSoundWordProblem(word, rule),
    shows: (word) => `Shows ${label(word)}.`,
    keeps: label,
  });
}

// A word setting's row: a list of choices plus "Custom…", whose text box is checked as typed;
// a word that breaks the rule is not used (the setting keeps its last good word).
const CUSTOM_WORD = "custom";

function wordChoiceRow({ key, name, help, maxLength, defaultWord, options, problem, shows, keeps }) {
  if (typeof playerSettings[key] !== "string" || problem(playerSettings[key])) playerSettings[key] = defaultWord;
  const listed = options.some((option) => option.value === playerSettings[key]);
  const select = selectControl(`player-${key}`, name, [...options, { value: CUSTOM_WORD, label: "Custom…" }],
                               () => update());
  select.value = listed ? playerSettings[key] : CUSTOM_WORD;
  const input = element("input", { type: "text", id: `player-${key}-custom`, className: "select level-word-input",
                                   maxLength, spellcheck: false, autocomplete: "off",
                                   ariaLabel: `${name}: your own word`, value: listed ? "" : playerSettings[key] });
  input.addEventListener("input", () => update());
  const control = element("span", { className: "level-word-control" }, select, input);
  const { row, reason } = settingRow(name, help, control);
  function update() {
    const custom = select.value === CUSTOM_WORD;
    input.hidden = !custom;
    const word = custom ? normalizedLevelWord(input.value) : select.value;
    const wrong = problem(word);
    row.classList.toggle("setting--problem", Boolean(wrong));
    input.classList.toggle("level-word-input--error", Boolean(wrong));
    if (wrong) {
      reason.textContent = `Not used: ${wrong}. The game keeps ${keeps(playerSettings[key])}.`;
      return;
    }
    playerSettings[key] = word;
    savePlayerSettings();
    reason.textContent = shows(word);
  }
  update();
  return row;
}

// The Link sprite (FP-LINK-02; zora/rom/link_sprite.py): PRG0's Link, one of ZORA's built-in sets
// (metadata.linkSpriteSet.builtIn), a set the player loads (a JSON file, docs/link-sprite-sets.md), or
// Random: Link, a built-in set or the loaded one, picked by the seed number. The loaded set is kept in
// this browser (not in the settings file, which keeps the choice); Python checks it again when a seed
// is made. Single player only.
const PLAYABLE_CHARACTER = "Playable character";
const LINK_SPRITE_HELP = "Who you play as: Link, one of ZORA's sprite sets, or a sprite set you load (a .json " +
  "sprite-set file with a name, an author and 640 bytes of tile art). Random: Link, one of ZORA's sets or yours, " +
  "picked by the seed number. A set changes only how the character is drawn, in play, on the title story and on " +
  "the file-select screen. A set drawn for its own colors gets them unless you pick your own (Playable " +
  "character's colors, under the sprite): its other two colors, and its tunic colors too when its first color " +
  "draws the character rather than clothing.";

class LinkSpriteSetError extends Error {}

const COLOR_ONE_CLOTHING = "clothing";
const COLOR_ONE_ART = "art";

// A sprite-set file's object, checked as Python checks it (zora/rom/link_sprite.py sprite_set_from_object):
// the format and version, a name and an author, and exactly metadata.linkSpriteSet.size bytes of tiles.
function checkedLinkSpriteSet(data, rule) {
  if (data === null || typeof data !== "object" || Array.isArray(data)) {
    throw new LinkSpriteSetError("a Link sprite set file holds one JSON object");
  }
  if (data.format !== rule.format) {
    throw new LinkSpriteSetError(`not a Link sprite set file (its "format" is not "${rule.format}")`);
  }
  if (data.version !== rule.version) {
    throw new LinkSpriteSetError(`a Link sprite set file of version ${JSON.stringify(data.version)}: this ZORA ` +
                                 `reads version ${rule.version}`);
  }
  for (const field of ["name", "author"]) {
    if (typeof data[field] !== "string" || !data[field].trim()) {
      throw new LinkSpriteSetError(`a Link sprite set needs a ${field}`);
    }
  }
  if (typeof data.tiles !== "string") throw new LinkSpriteSetError('a Link sprite set file needs its tile data ("tiles", base64)');
  let size;
  try { size = atob(data.tiles).length; } catch { throw new LinkSpriteSetError("a Link sprite set's tile data is not base64"); }
  if (size !== rule.size) {
    throw new LinkSpriteSetError(`a Link sprite set holds exactly ${rule.size} bytes of tile data, not ${size}`);
  }
  const colors = data.recommendedColors;
  const color = (value) => Number.isInteger(value) && value >= 0 && value < NES_PALETTE.length && value !== BLACKER_THAN_BLACK;
  const recommended = colors && Array.isArray(colors.tunics) && colors.tunics.length === 3 && Array.isArray(colors.other)
    && colors.other.length === 2 && [...colors.tunics, ...colors.other].every(color)
    ? { tunics: colors.tunics, other: colors.other } : undefined;
  if (recommended && colors.colorOne !== undefined) {
    if (colors.colorOne !== COLOR_ONE_CLOTHING && colors.colorOne !== COLOR_ONE_ART) {
      throw new LinkSpriteSetError(`a Link sprite set's color 1 ("colorOne") is "${COLOR_ONE_CLOTHING}" or ` +
                                   `"${COLOR_ONE_ART}", not ${String(colors.colorOne)}`);
    }
    if (colors.colorOne === COLOR_ONE_ART) recommended.colorOne = COLOR_ONE_ART;
  }
  const fromGame = data.fromGame === undefined ? [] : data.fromGame;
  const tiles = Uint8Array.from(atob(data.tiles), (character) => character.charCodeAt(0));
  if (!Array.isArray(fromGame) || !fromGame.every((pair) => Array.isArray(pair) && pair.length === 2)) {
    throw new LinkSpriteSetError('a Link sprite set\'s "fromGame" is a list of [start, end] pairs');
  }
  let previousEnd = 0;
  for (const [start, end] of fromGame) {
    if (!(Number.isInteger(start) && Number.isInteger(end) && previousEnd <= start && start < end && end <= rule.size)) {
      throw new LinkSpriteSetError(`a Link sprite set's "fromGame" ranges lie in order inside its ${rule.size} bytes, ` +
                                   `apart: not [${start}, ${end}]`);
    }
    if (tiles.subarray(start, end).some((byte) => byte)) {
      throw new LinkSpriteSetError(`a Link sprite set holds zeros where "fromGame" takes the game's bytes (${start} to ${end})`);
    }
    previousEnd = end;
  }
  return { format: data.format, version: data.version, name: data.name, author: data.author,
           provenance: typeof data.provenance === "string" ? data.provenance : "", tiles: data.tiles,
           ...(recommended ? { recommendedColors: recommended } : {}), ...(fromGame.length ? { fromGame } : {}) };
}

function loadLinkSpriteSet() {
  try {
    const saved = JSON.parse(pageStorage.getItem(LINK_SPRITE_SET_KEY) || "null");
    return saved && typeof saved === "object" && typeof saved.tiles === "string" ? saved : null;
  } catch { return null; }
}

// A built-in set by its choice (LINK_SPRITE_BUILT_IN and its id), or null.
function builtInLinkSpriteSet(choice) {
  const id = choice.slice(LINK_SPRITE_BUILT_IN.length);
  return (metadata ? metadata.linkSpriteSet.builtIn : []).find((set) => set.id === id) || null;
}

function linkSpriteRow() {
  const set = loadLinkSpriteSet();
  const options = [{ value: LINK_SPRITE_LINK, label: "Link (original)" },
                   ...metadata.linkSpriteSet.builtIn.map((builtIn) => ({
                     value: LINK_SPRITE_BUILT_IN + builtIn.id, label: builtIn.name }))];
  if (set) options.push({ value: LINK_SPRITE_SET, label: `${set.name} (yours)` });
  options.push({ value: LINK_SPRITE_RANDOM, label: "Random" });
  if (!options.some((option) => option.value === playerSettings.linkSprite)) playerSettings.linkSprite = LINK_SPRITE_LINK;
  const select = selectControl("player-linkSprite", PLAYABLE_CHARACTER, options, () => {
    playerSettings.linkSprite = select.value;
    savePlayerSettings();
    showLinkSpriteInfo();
    refreshLinkSpritePreview();
    refreshLinkSpriteSwap();
  });
  select.value = playerSettings.linkSprite;
  const file = element("input", { type: "file", id: "player-linkSprite-file", hidden: true, accept: ".json,application/json" });
  const load = element("button", { type: "button", id: "player-linkSprite-load", className: "btn btn-tint btn-small",
                                   textContent: "Load a set…" });
  load.addEventListener("click", () => file.click());
  const control = element("span", { className: "link-sprite-control" }, select, load, file);
  const { row, reason } = settingRow(PLAYABLE_CHARACTER, LINK_SPRITE_HELP, control);
  row.classList.add("single-only");
  // Under the row: who drew the sprite and the colors it was drawn for (left), the preview (right).
  row.append(element("div", { className: "link-sprite-details" },
                     element("div", { id: "link-sprite-info", className: "link-sprite-info" }), linkSpritePreview()),
             linkSpriteSwapControl());
  showLinkSpriteInfo(row.querySelector("#link-sprite-info"));
  file.addEventListener("change", async () => {
    const chosen = file.files[0];
    file.value = "";
    if (!chosen) return;
    try {
      let data;
      try { data = JSON.parse(await chosen.text()); } catch {
        throw new LinkSpriteSetError("a Link sprite set file is JSON; this one does not read as JSON");
      }
      const checked = checkedLinkSpriteSet(data, metadata.linkSpriteSet);
      try { pageStorage.setItem(LINK_SPRITE_SET_KEY, JSON.stringify(checked)); } catch {
        throw new LinkSpriteSetError("this browser isn't keeping data for this page, so it can't keep the set");
      }
      playerSettings.linkSprite = LINK_SPRITE_SET;
      savePlayerSettings();
      row.replaceWith(linkSpriteRow());
    } catch (err) {
      if (!(err instanceof LinkSpriteSetError)) throw err;
      row.classList.add("setting--problem");
      reason.textContent = `${chosen.name}: ${err.message}. Not loaded.`;
    }
  });
  return row;
}

// A person set that can also draw the person as Link (its "swap").
function linkSpriteHasSwap(choice) {
  const set = chosenLinkSpriteSet(choice);
  return Boolean(set && Array.isArray(set.swap) && set.swap.length);
}

// Under the sprite: the swap's checkbox, shown only for a person set that has one.
function linkSpriteSwapControl() {
  const box = element("input", { type: "checkbox", id: "player-linkSpriteSwap" });
  const text = element("span");
  const label = element("label", { id: "link-sprite-swap", className: "link-sprite-swap" }, box, text);
  box.addEventListener("change", () => {
    playerSettings.linkSpriteSwap = box.checked ? "on" : "off";
    savePlayerSettings();
  });
  refreshLinkSpriteSwap(label);
  return label;
}

function refreshLinkSpriteSwap(label = $("link-sprite-swap")) {
  if (!label) return;
  const set = chosenLinkSpriteSet(playerSettings.linkSprite);
  label.hidden = !linkSpriteHasSwap(playerSettings.linkSprite);
  label.querySelector("input").checked = !label.hidden && playerSettings.linkSpriteSwap === "on";
  label.querySelector("span").textContent = set ? ` Swap: ${set.name} also looks like Link` : "";
  label.title = "The person you play as also takes Link's place where the game draws them. " +
                "Off by default; Random never swaps.";
}

// The chosen sprite's set (built-in or loaded), or null (Link, Random).
function chosenLinkSpriteSet(choice) {
  if (choice.startsWith(LINK_SPRITE_BUILT_IN)) return builtInLinkSpriteSet(choice);
  return choice === LINK_SPRITE_SET ? loadLinkSpriteSet() : null;
}

function colorSwatch(color) {
  const swatch = element("span", { className: "link-sprite-swatch", title: `$${color.toString(16).toUpperCase().padStart(2, "0")}` });
  swatch.style.background = NES_PALETTE[color];
  return swatch;
}

// Who drew the chosen sprite, and the colors it was drawn for with a button that applies them.
function showLinkSpriteInfo(info = $("link-sprite-info")) {
  if (!info) return;
  const choice = playerSettings.linkSprite;
  const set = chosenLinkSpriteSet(choice);
  if (!set) {
    info.replaceChildren(element("p", { className: "panel-note", textContent: choice === LINK_SPRITE_RANDOM
      ? "The original Link, one of ZORA's sets or yours, picked by the seed number." : "The original Link." }),
      ...(choice === LINK_SPRITE_RANDOM ? [characterColorsControl(null)] : []));
    return;
  }
  const lines = [element("p", { className: "link-sprite-artist" }, "By ", element("strong", { textContent: set.author }),
                         choice === LINK_SPRITE_SET ? " (your set)" : "")];
  if (choice === LINK_SPRITE_SET && set.provenance) lines.push(element("p", { className: "panel-note", textContent: set.provenance }));
  const recommended = set.recommendedColors;
  if (recommended) {
    lines.push(element("div", { className: "link-sprite-colors" },
      element("span", { className: "panel-note", textContent: "Drawn for: tunics" }),
      ...recommended.tunics.map(colorSwatch),
      element("span", { className: "panel-note", textContent: "other colors" }),
      ...recommended.other.map(colorSwatch)));
    lines.push(characterColorsControl(recommended));
  }
  info.replaceChildren(...lines);
}

// Playable character's colors: the set's own (the default) or the player's tunic and other colors.
function characterColorsControl(recommended) {
  const label = "Playable character's colors";
  const select = selectControl("player-characterColors", label, [
    { value: CHARACTER_COLORS_SET, label: "The set's own" }, { value: CHARACTER_COLORS_MINE, label: "My own" }], () => {
    playerSettings.characterColors = select.value;
    savePlayerSettings();
    showColorChange($("marker-note"));
  });
  select.value = playerSettings.characterColors;
  select.title = !recommended
    ? "The set's own: the colors the seed's set was drawn for, if it has any. My own: your tunic and other colors."
    : recommended.colorOne === COLOR_ONE_ART
    ? "The set's own: all five colors above, its first color drawing the character, not clothing. My own: your tunic and other colors."
    : "The set's own: its other two colors, with your tunic colors. My own: your tunic and other colors.";
  return element("label", { className: "link-sprite-colors" }, `${label}: `, select);
}

// The tunic colors and other colors the ROM gets (zora/rom/player_settings.py shown_link_colors): the
// player's, or a chosen set's own (its other colors, and its tunics when its color 1 is art).
function shownLinkColors(set) {
  const mine = { tunics: TUNIC_SLOTS.map((key) => playerSettings[key]), other: LINK_COLOR_SLOTS.map((key) => playerSettings[key]) };
  const recommended = set && set.recommendedColors;
  if (playerSettings.characterColors === CHARACTER_COLORS_MINE || !recommended) return mine;
  return { tunics: recommended.colorOne === COLOR_ONE_ART ? recommended.tunics : mine.tunics, other: recommended.other };
}

// A color changed: the map-marker note and the sprite preview.
function showColorChange(markerNote) {
  if (markerNote) showMarkerNote(markerNote);
  refreshLinkSpritePreview();
}

// The Link sprite's preview: the main pose (walking down, with the small shield) in each tunic color, as the
// game draws it: color 1 the tunic, colors 2 and 3 Link's other colors (the game's unless changed).
// The original Link is read from the player's ROM (its Link groups), so it shows once a ROM is chosen.
const PREVIEW_HALVES = [17, 5];         // the set's 8x16 halves: tile $58 (left, the shield) and $0A (right)
const PREVIEW_SCALE = 4;
const TUNIC_NAMES = { greenTunic: "Green tunic", blueRingTunic: "Blue ring", redRingTunic: "Red ring" };

function base64Bytes(text) {
  return Uint8Array.from(atob(text), (character) => character.charCodeAt(0));
}

// The file offsets in metadata count the 16-byte iNES header; a ROM file without one sits 16 bytes earlier.
function headerShift(rom) {
  return rom[0] === 0x4E && rom[1] === 0x45 && rom[2] === 0x53 && rom[3] === 0x1A ? 0 : -16;
}

// A built-in-art set's 640 bytes, assembled from the player's ROM as Python assembles them
// (zora/rom/link_art.py art_tiles): each of Link's halves is a source half's two tiles, mirrored if
// asked, its colors 1-3 becoming the set's colors; color 0 stays transparent.
function artSetTiles(set, rom) {
  const art = metadata.linkSpriteSet.art;
  const header = headerShift(rom);
  const colors = set.colors || [1, 2, 3];
  const tiles = new Uint8Array(art.halves.length * 32);
  art.halves.forEach((name, index) => {
    const half = set.halves[name];
    const [offset, firstTile] = art.blocks[half.block];
    const source = offset + header + (parseInt(half.tile.slice(1), 16) - firstTile) * 16;
    for (let tile = 0; tile < 2; tile++) {
      for (let row = 0; row < 8; row++) {
        const low = rom[source + tile * 16 + row];
        const high = rom[source + tile * 16 + 8 + row];
        for (let column = 0; column < 8; column++) {
          const bit = 7 - column;
          let color = ((low >> bit) & 1) | (((high >> bit) & 1) << 1);
          if (color) color = colors[color - 1];
          const to = half.mirror ? column : bit;
          tiles[index * 32 + tile * 16 + row] |= (color & 1) << to;
          tiles[index * 32 + tile * 16 + 8 + row] |= (color >> 1) << to;
        }
      }
    }
  });
  return tiles;
}

// The 640 bytes the current choice draws Link from, or null (Random, or the original or a built-in-art
// set without a ROM).
function linkSpritePreviewTiles(choice) {
  if (choice.startsWith(LINK_SPRITE_BUILT_IN)) {
    const builtIn = builtInLinkSpriteSet(choice);
    if (builtIn && builtIn.format === metadata.linkSpriteSet.art.format) {
      return baseRom ? artSetTiles(builtIn, baseRom) : null;
    }
    return builtIn ? setTiles(builtIn) : null;
  }
  if (choice === LINK_SPRITE_SET) {
    const set = loadLinkSpriteSet();
    return set ? setTiles(set) : null;
  }
  if (choice === LINK_SPRITE_LINK && baseRom) {
    const header = headerShift(baseRom);
    return Uint8Array.from(metadata.linkSpriteSet.groups.flatMap(([offset, tiles]) =>
      [...baseRom.subarray(offset + header, offset + header + tiles * 16)]));
  }
  return null;
}

// A 640-byte set's tiles, its fromGame ranges read from the player's ROM's own Link (zora/rom/link_art.py
// sprite_set_tiles), or null when it has some and no ROM is chosen.
function setTiles(set) {
  const tiles = base64Bytes(set.tiles);
  if (!set.fromGame || !set.fromGame.length) return tiles;
  if (!baseRom) return null;
  const original = linkSpritePreviewTiles(LINK_SPRITE_LINK);
  for (const [start, end] of set.fromGame) tiles.set(original.subarray(start, end), start);
  return tiles;
}

// One 16x16 frame of a set's tiles as rows of color indexes (0-3).
function previewFrame(tiles) {
  const rows = Array.from({ length: 16 }, () => []);
  for (const half of PREVIEW_HALVES) {
    for (let y = 0; y < 16; y++) {
      const tile = (2 * half + (y >> 3)) * 16;
      const low = tiles[tile + (y & 7)];
      const high = tiles[tile + 8 + (y & 7)];
      for (let x = 0; x < 8; x++) rows[y].push(((low >> (7 - x)) & 1) | (((high >> (7 - x)) & 1) << 1));
    }
  }
  return rows;
}

function drawPreview(canvas, frame, tunic, other) {
  const context = canvas.getContext("2d");
  const colors = [null, NES_PALETTE[tunic], ...other.map((color) => NES_PALETTE[color])];
  context.clearRect(0, 0, canvas.width, canvas.height);
  frame.forEach((row, y) => row.forEach((index, x) => {
    if (!index) return;
    context.fillStyle = colors[index];
    context.fillRect(x * PREVIEW_SCALE, y * PREVIEW_SCALE, PREVIEW_SCALE, PREVIEW_SCALE);
  }));
}

function linkSpritePreview() {
  const figures = TUNIC_SLOTS.map((key) => element("figure", { className: "link-preview-figure" },
    element("canvas", { width: 16 * PREVIEW_SCALE, height: 16 * PREVIEW_SCALE, ariaLabel: TUNIC_NAMES[key] }),
    element("figcaption", { textContent: TUNIC_NAMES[key] })));
  const note = element("p", { className: "panel-note link-preview-note" });
  const preview = element("div", { id: "link-sprite-preview", className: "link-preview" },
                          element("div", { className: "link-preview-figures" }, ...figures), note);
  refreshLinkSpritePreview(preview);
  return preview;
}

// Redraws the preview (the choice, a tunic color or the ROM changed).
function refreshLinkSpritePreview(preview = $("link-sprite-preview")) {
  if (!preview) return;
  const tiles = linkSpritePreviewTiles(playerSettings.linkSprite);
  const figures = preview.querySelector(".link-preview-figures");
  const note = preview.querySelector(".link-preview-note");
  figures.hidden = tiles === null;
  note.textContent = tiles !== null ? ""
    : playerSettings.linkSprite === LINK_SPRITE_RANDOM ? "Random: the seed number picks the sprite, so there is no preview."
    : playerSettings.linkSprite === LINK_SPRITE_LINK ? "Choose your ROM to preview the original Link."
    : "Choose your ROM to preview this sprite: it is drawn from your ROM's own art.";
  if (tiles === null) return;
  const frame = previewFrame(tiles);
  const shown = shownLinkColors(chosenLinkSpriteSet(playerSettings.linkSprite));
  const randomTunic = shown.tunics.some((color) => color === RANDOM_COLOR);
  if (randomTunic) note.textContent = "A Random tunic color shows here in its default color.";
  TUNIC_SLOTS.forEach((key, index) => {
    const color = shown.tunics[index] === RANDOM_COLOR ? COLOR_SLOTS.find((slot) => slot.key === key).default
      : shown.tunics[index];
    drawPreview(figures.children[index].querySelector("canvas"), frame, color, shown.other);
  });
}

// The map marker note (docs/reports/minimap-marker.md): shown while any tunic color is one
// zora/ draws the marker in Link's skin color for (metadata.markerHidingColors, the same set).
const MARKER_NOTE = "Note: Because one of the selected tunic colors is dark, the player's minimap color " +
                    "will be lighter to ensure it stays visible.";
const colorPickers = new Map();         // color slot key -> its picker's show(value) (initColorPicker)

function showMarkerNote(note) {
  note.hidden = !TUNIC_SLOTS.some((key) => metadata.markerHidingColors.includes(playerSettings[key]));
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
                                            () => loadPreset(preset.label, preset.flags, preset.zoraFlags || ""));
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
    pageStorage.setItem(probe, "1");
    pageStorage.removeItem(probe);
    return checkedCustomPresets(JSON.parse(pageStorage.getItem(CUSTOM_PRESETS_KEY) || "[]"));
  } catch {
    return null;
  }
}

// The slots as this page keeps them, from any earlier page's saved list (fewer slots, no ZORA flags).
function checkedCustomPresets(saved) {
  const slots = Array.from({ length: CUSTOM_SLOT_COUNT }, (_, i) => (Array.isArray(saved) ? saved[i] : null));
  return slots.map((slot) => (slot && typeof slot.name === "string" && typeof slot.flags === "string"
    ? { name: slot.name, flags: slot.flags, zoraFlags: typeof slot.zoraFlags === "string" ? slot.zoraFlags : "" }
    : null));
}

function writeCustomPresets(slots) {
  try {
    pageStorage.setItem(CUSTOM_PRESETS_KEY, JSON.stringify(slots));
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

// ---------------------------------------------------------------------------
// The settings file (owner, 2026-10-17): everything this page remembers, as one YAML file a player
// loads in another browser or after clearing site data. SETTINGS_FORMAT goes up only when a file
// this page writes would be misread by an older page; a page refuses a newer format and keeps
// reading every older one (tests/test_web_settings_file.py pins a format 1 file).
// ---------------------------------------------------------------------------

const SETTINGS_FORMAT_KEY = "zora_page_settings";
const SETTINGS_FORMAT = 1;
const THEMES = ["light", "dark"];
const NOT_A_SETTINGS_FILE = "This isn't a ZORA settings file: it has no zora_page_settings line.";
const YAML_KEY = /^([A-Za-z_][\w-]*)\s*:(?:\s+(.*))?$/;

class SettingsFileError extends Error {}

// What the file holds, in its order: the format and the page that saved it, then the settings.
function pageSettings() {
  return {
    [SETTINGS_FORMAT_KEY]: SETTINGS_FORMAT,
    saved_by: `ZORA ${$("version").textContent}`,
    mode,
    flags: form.flags,
    zora_flags: form.zora.ok ? form.zora.flags : "",
    player_settings: currentPlayerSettings(false),
    custom_presets: readCustomPresets() || [],
    player_name: savedPlayerName(),
    theme: getSetting(THEME_KEY),
    open_tab: getSetting(TAB_KEY),
  };
}

// A value as the file writes it: text double-quoted with JSON's escapes (which YAML reads the same),
// a number or null bare.
function yamlScalar(value) {
  return typeof value === "string" ? JSON.stringify(value) : String(value);
}

function settingsYaml(settings) {
  const lines = ["# ZORA settings: load this file in ZORA's Presets window (Load a file).",
                 "# It holds your flags, mode, cosmetic settings, presets, player name and theme."];
  const entries = (value) => Object.entries(value);
  for (const [key, value] of entries(settings)) {
    if (Array.isArray(value) && value.length) {
      lines.push(`${key}:`);
      for (const item of value) {
        if (item !== null && typeof item === "object" && entries(item).length) {
          entries(item).forEach(([field, inner], i) => lines.push(`${i ? "    " : "  - "}${field}: ${yamlScalar(inner)}`));
        } else {
          lines.push(`  - ${item !== null && typeof item === "object" ? "{}" : yamlScalar(item)}`);
        }
      }
    } else if (value !== null && typeof value === "object" && entries(value).length) {
      lines.push(`${key}:`);
      for (const [field, inner] of entries(value)) lines.push(`  ${field}: ${yamlScalar(inner)}`);
    } else {
      lines.push(`${key}: ${Array.isArray(value) ? "[]" : value !== null && typeof value === "object" ? "{}" : yamlScalar(value)}`);
    }
  }
  return `${lines.join("\n")}\n`;
}

// Reads the YAML this page writes, and the same edited by hand or saved again by another YAML tool:
// block maps and lists, values double-quoted, single-quoted or plain (a whole number, 0x hex, null,
// true or false, else text), comments, and empty {} and []. Anything else is refused with its line.
function parseSettingsYaml(text) {
  const lines = [];
  text.replace(/^﻿/, "").split(/\r?\n/).forEach((raw, index) => {
    if (/^\s*(#|$)/.test(raw)) return;
    if (/^ *\t/.test(raw)) throw new SettingsFileError(`Line ${index + 1}: YAML can't be indented with tabs.`);
    lines.push({ number: index + 1, indent: raw.search(/\S/), text: raw.trim() });
  });
  if (!lines.length) throw new SettingsFileError(NOT_A_SETTINGS_FILE);
  let at = 0;
  const fail = (line, why) => { throw new SettingsFileError(`Line ${line.number}: ${why}`); };
  const isItem = (line) => line.text === "-" || line.text.startsWith("- ");

  function scalar(written, line) {
    const quoted = /^"(?:[^"\\]|\\.)*"|^'(?:[^']|'')*'/.exec(written);
    if (quoted) {
      if (!/^(\s+#.*)?$/.test(written.slice(quoted[0].length))) fail(line, "text after the closing quote.");
      if (quoted[0][0] === "'") return quoted[0].slice(1, -1).replace(/''/g, "'");
      try { return JSON.parse(quoted[0]); } catch { fail(line, "this quoted text can't be read."); }
    }
    const plain = written.replace(/\s+#.*$/, "");
    if (plain === "{}") return {};
    if (plain === "[]") return [];
    if (/^["'{[]/.test(plain)) fail(line, "this value can't be read.");
    if (plain === "" || plain === "~" || plain === "null") return null;
    if (plain === "true" || plain === "false") return plain === "true";
    if (/^-?\d+$/.test(plain)) return Number(plain);
    if (/^0x[0-9a-f]+$/i.test(plain)) return parseInt(plain, 16);
    return plain;
  }

  // The value under a "name:" line with nothing after it: a deeper block, a list at the same
  // indentation (as other YAML tools write lists), or null.
  function nested(indent) {
    if (at < lines.length && lines[at].indent > indent) return block(lines[at].indent);
    if (at < lines.length && lines[at].indent === indent && isItem(lines[at])) return list(indent);
    return null;
  }

  function map(indent) {
    const out = {};
    while (at < lines.length && lines[at].indent === indent && !isItem(lines[at])) {
      const line = lines[at];
      const match = YAML_KEY.exec(line.text);
      if (!match) fail(line, "expected name: value.");
      if (Object.hasOwn(out, match[1])) fail(line, `${match[1]} appears twice.`);
      at++;
      out[match[1]] = match[2] === undefined || match[2] === "" ? nested(indent) : scalar(match[2], line);
    }
    return out;
  }

  function list(indent) {
    const out = [];
    while (at < lines.length && lines[at].indent === indent && isItem(lines[at])) {
      const line = lines[at];
      const rest = line.text.slice(1).trimStart();
      if (YAML_KEY.test(rest)) {
        // "- name: value" opens a map whose other names line up under this first one.
        lines[at] = { ...line, indent: line.indent + line.text.length - rest.length, text: rest };
        out.push(map(lines[at].indent));
      } else {
        at++;
        out.push(rest === "" ? nested(indent) : scalar(rest, line));
      }
    }
    return out;
  }

  function block(indent) {
    return isItem(lines[at]) ? list(indent) : map(indent);
  }

  const settings = block(lines[0].indent);
  if (at < lines.length) fail(lines[at], "unexpected indentation.");
  return settings;
}

// The file's settings, checked: its format first, then each part's kind. A part the file leaves
// out keeps this page's own; each value is checked again where the page reads it
// (loadPlayerSettings, readCustomPresets, the flag form as for a shared link).
function checkedPageSettings(settings) {
  const isMap = (value) => value !== null && typeof value === "object" && !Array.isArray(value);
  if (!isMap(settings) || !Object.hasOwn(settings, SETTINGS_FORMAT_KEY)) throw new SettingsFileError(NOT_A_SETTINGS_FILE);
  const format = settings[SETTINGS_FORMAT_KEY];
  if (!Number.isInteger(format) || format < 1) {
    throw new SettingsFileError(`${SETTINGS_FORMAT_KEY} must be a whole number from 1, not ${JSON.stringify(format)}.`);
  }
  if (format > SETTINGS_FORMAT) {
    const by = typeof settings.saved_by === "string" ? ` (${settings.saved_by})` : "";
    throw new SettingsFileError(`This file was saved by a newer ZORA page${by}, in settings format ${format}. ` +
      `This page reads format ${SETTINGS_FORMAT} and older: load the file on the newer page, or use a newer ZORA.`);
  }
  const expect = (key, check, what) => {
    if (settings[key] !== undefined && settings[key] !== null && !check(settings[key])) {
      throw new SettingsFileError(`${key} must be ${what}.`);
    }
  };
  expect("mode", (value) => value === SINGLE || value === MULTIWORLD, `${SINGLE} or ${MULTIWORLD}`);
  for (const key of ["saved_by", "flags", "zora_flags", "player_name", "open_tab"]) {
    expect(key, (value) => typeof value === "string", "text");
  }
  expect("theme", (value) => THEMES.includes(value), THEMES.join(" or "));
  expect("player_settings", isMap, "a list of name: value lines");
  expect("custom_presets", Array.isArray, "a list of presets");
  return settings;
}

// Keeps the file's settings in this browser, as the page itself would, and returns the address that
// opens the page on its flags and mode (linkSearch, as a shared link does).
function applyPageSettings(settings) {
  const kept = [[PLAYER_SETTINGS_KEY, settings.player_settings && JSON.stringify(settings.player_settings)],
                [CUSTOM_PRESETS_KEY, settings.custom_presets && JSON.stringify(settings.custom_presets)],
                [PLAYER_NAME_KEY, settings.player_name], [THEME_KEY, settings.theme], [TAB_KEY, settings.open_tab]];
  try {
    for (const [key, value] of kept) if (typeof value === "string") pageStorage.setItem(key, value);
  } catch {
    throw new SettingsFileError("This browser isn't keeping data for this page, so it can't load settings.");
  }
  const search = linkSearch(location.search, {
    flags: settings.flags ?? form.flags, zoraFlags: settings.zora_flags ?? (form.zora.ok ? form.zora.flags : ""),
    mode: settings.mode ?? mode }, metadata.defaultFlags);
  return `${location.pathname}${search}${location.hash}`;
}

function showSettingsNote(text, kind = "") {
  $("settings-file-note").textContent = text;
  $("settings-file-note").className = `preset-footnote ${kind}`;
}

function saveSettingsFile() {
  if (!form) return;
  const url = URL.createObjectURL(new Blob([settingsYaml(pageSettings())], { type: "text/yaml" }));
  const today = new Date();       // the player's own date, not UTC's
  const date = [today.getFullYear(), today.getMonth() + 1, today.getDate()].map((part) => String(part).padStart(2, "0"));
  const link = element("a", { href: url, download: `zora-settings-${date.join("-")}.yaml` });
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
  showSettingsNote(`Saved ${link.download}.`);
}

async function loadSettingsFile() {
  const file = $("settings-file").files[0];
  $("settings-file").value = "";
  if (!file || !form) return;
  try {
    const settings = checkedPageSettings(parseSettingsYaml(await file.text()));
    const saved = readCustomPresets();
    if (saved && saved.some(Boolean) && settings.custom_presets
        && !window.confirm("Load the settings in this file? They replace this page's flags, cosmetic settings " +
                           "and your saved presets.")) return;
    location.replace(applyPageSettings(settings));
  } catch (err) {
    if (!(err instanceof SettingsFileError)) throw err;
    showSettingsNote(`${file.name}: ${err.message}`, "preset-footnote--error");
  }
}

function openPresets() {
  renderCustomPresets();
  $("settings-save").disabled = !form;
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
  return labelIn(control.field.values, value);
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

// Multiworld mode: why Archipelago does not take this value of a field (a Z1R field's id, a ZORA
// flag's name), or undefined when it does. Always undefined in single-player mode.
function multiworldReason(id, value) {
  if (mode !== MULTIWORLD) return undefined;
  const fixed = metadata.multiworld.fixed[id];
  if (fixed) return value === fixed.value ? undefined : fixed.reason;
  const offered = metadata.multiworld.offered[id];
  return !offered || offered.includes(value) ? undefined : metadata.multiworld.notOffered;
}

// Why a field offers only its value. In multiworld mode Archipelago's reason comes first (each value's
// own reason lists it first): a field it never offers, or one whose other values it does not take.
function lockedReason(id, field, reasons) {
  if (mode !== MULTIWORLD) return field.reason || reasons[0] || "";
  const fixed = metadata.multiworld.fixed[id];
  return fixed ? fixed.reason : reasons[0] || field.reason || "";
}

function showField(id, control, field) {
  control.value = field.value;
  const reasons = [];      // why the other values cannot be picked
  let pickable = 0;
  const offer = (value) => {
    const why = value === field.value ? undefined : multiworldReason(id, value) ?? blockedReason(id, field, value);
    if (why !== undefined) reasons.push(why);
    else if (value !== field.value) pickable++;
    return why;
  };
  if (control.kind === "select") {
    control.input.value = String(field.value);
    if (control.note) control.note.textContent = noteIn(control.field.values, field.value);
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
  // Multiworld mode: a value Archipelago does not take needs changing, like a refused one.
  const refusedHere = multiworldReason(id, field.value);
  const problem = field.problem || refusedHere !== undefined;
  const locked = pickable === 0 && !problem;
  control.row.classList.toggle("setting--locked", locked);
  control.row.classList.toggle("setting--problem", problem);
  // A hidden field shows itself while its value needs changing (a pasted string).
  control.row.hidden = !control.shown && !problem && !field.notice;
  control.reason.textContent = field.problem
    ? (isNotImplemented(control, field.value) ? NOT_IMPLEMENTED : plainText(field.reason))
    : refusedHere !== undefined ? `${refusedHere} Choose another value to export.`
    : locked ? plainText(lockedReason(id, field, reasons))
    : field.notice ? `${plainText(field.notice)}.` : "";     // a pasted postponed value (B06)
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
  $("start-limit-note").hidden = !startItemsAllDropped(startRules, state.fields);
  showZoraState(state.zora, { rewrite });
  showFlagSummary(state);

  showProblems();
  updateLink();
  updateButton();
  refreshMultiworld();
}

// The list under the button: in single-player mode what blocks generation; in multiworld mode what
// blocks the export (multiworldVerdict, from Python).
function showProblems() {
  if (!form) return;
  const notes = [...(form.notices || []).map((text) => `Notice: ${plainText(text)}.`),
                 ...form.refusals.map((text) => `Rule: ${plainText(text)}`), ...form.adjustments.map(plainText)];
  let lines;
  if (mode === MULTIWORLD) {
    const reasons = multiworldVerdict ? multiworldVerdict.reasons : [];
    lines = [...notes, ...reasons.filter((text) => !form.refusals.some((rule) => text.includes(rule)))
      .map((text) => `Cannot export: ${plainText(text)}`)];
  } else {
    const refusals = form.generateRefusals.filter((text) => !form.refusals.includes(text)
                                                        && !text.startsWith(NOT_PRODUCED_REFUSAL));
    lines = [...notImplementedLines(form), ...notes, ...refusals.map((text) => `Cannot generate: ${plainText(text)}`)];
  }
  $("problems").replaceChildren(...lines.map((text) => element("li", { textContent: text })));
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
// The shared link: both flag strings, the mode and (single player) the seed, in the page's address
// ---------------------------------------------------------------------------

// A seed as a link may carry it, without leading zeros; null unless it is one ZORA takes.
function validSeed(text) {
  if (!text || !/^\d{1,20}$/.test(text)) return null;
  const seed = BigInt(text);
  return seed < SEED_LIMIT ? seed.toString() : null;
}

// What a link's query asks for: each flag string (null when absent), the mode, and the seed (null
// when absent, not valid, or in multiworld mode, where Archipelago draws the seed).
function linkSettings(search) {
  const params = new URLSearchParams(search);
  const mode = params.get(LINK_MODE) === MULTIWORLD ? MULTIWORLD : SINGLE;
  return { flags: params.get(LINK_FLAGS), zoraFlags: params.get(LINK_ZORA_FLAGS), mode,
           seed: mode === SINGLE ? validSeed(params.get(LINK_SEED)) : null };
}

// The query for these settings, keeping any other parameter (?pyodide=) first: the default flag
// string, an empty ZORA string and no seed are left out ("" when nothing is left). The last
// parameter can never end in "!" (owner, beta 5): chat apps often drop a trailing "!", which would
// silently change a flag string. So once the query names any setting it ends with the seed (single
// player, after a generation) or else the mode, written even when single player. Links are read in
// any order (linkSettings).
function linkSearch(search, { flags, zoraFlags, mode, seed = null }, defaultFlags) {
  const params = new URLSearchParams(search);
  for (const name of [LINK_FLAGS, LINK_ZORA_FLAGS, LINK_MODE, LINK_SEED]) params.delete(name);
  if (flags && flags !== defaultFlags) params.append(LINK_FLAGS, flags);
  if (zoraFlags) params.append(LINK_ZORA_FLAGS, zoraFlags);
  if (mode === SINGLE && seed) params.append(LINK_SEED, seed);
  else if (params.has(LINK_FLAGS) || params.has(LINK_ZORA_FLAGS) || mode === MULTIWORLD) params.append(LINK_MODE, mode);
  const query = params.toString();
  return query ? `?${query}` : "";
}

const sharedLink = linkSettings(location.search);

// The address now names the page's settings, so copying it shares them: with the seed of the last
// generation (or the seed the link brought, until the seed changes), none before.
function updateLink() {
  if (!form || !metadata) return;
  const search = linkSearch(location.search, { flags: form.flags, zoraFlags: form.zora.ok ? form.zora.flags : "", mode,
                                               seed: linkSeed }, metadata.defaultFlags);
  if (search === location.search) return;
  try {
    history.replaceState(history.state, "", `${location.pathname}${search}${location.hash}`);
  } catch { /* a page opened from disk may refuse; the strings still copy */ }
}

// ---------------------------------------------------------------------------
// Single player or multiworld (Archipelago)
// ---------------------------------------------------------------------------

let mode = sharedLink.mode;
let linkSeed = sharedLink.seed;     // the seed the address names: the link's, then each generation's
let seedTyped = false;              // the player typed the seed (or a link named it): never replaced
let multiworldVerdict = null;   // zora_web.multiworld.check() for the current settings, in multiworld mode
let multiworldRequest = 0;
let playerNameProblem = "type a player name";

function setMode(next) {
  mode = next;
  const multiworld = mode === MULTIWORLD;
  $("mode-single").setAttribute("aria-pressed", String(!multiworld));
  $("mode-multiworld").setAttribute("aria-pressed", String(multiworld));
  $("step-rom").hidden = multiworld;
  $("step-apworld").hidden = !multiworld;
  $("generate-row").hidden = multiworld;
  $("export-row").hidden = !multiworld;
  $("player-name-error").hidden = !multiworld;
  showMultiworldSettings();
  $("step-generate-title").textContent = multiworld ? "Export your Archipelago YAML" : "Generate the game";
  // Each mode keeps its own last result: a generated ROM, an exported YAML.
  $("generate-result").hidden = multiworld || !$("download").hasChildNodes();
  $("export-result").hidden = !multiworld || !$("yaml-download").hasChildNodes();
  markStepDone("step-generate-num", 3, !$(multiworld ? "export-result" : "generate-result").hidden);
  multiworldVerdict = null;
  if (ready) {
    status(multiworld ? "Multiworld: choose your settings and player name, then export your YAML."
      : baseRom ? romStepText(romIdentity).status : "Choose the base ROM.");
  }
  if (form) showState(form, { rewrite: false });
  updateLink();
}

// The world's links, or the placeholders until they exist (zora.apworld's once Python has started).
function showWorldLinks() {
  if (PAGE_CHANNEL === TEST_CHANNEL) {
    $("apworld-link").replaceChildren(
      element("a", { href: besideThisPage(TEST_CHANNEL_ASSETS.apworld), textContent: "Download zora.apworld" }),
      " (", element("a", { href: besideThisPage(TEST_CHANNEL_ASSETS.notes), textContent: "release notes" }), ")");
  } else {
    const apworldUrl = metadata && metadata.multiworld.apworldUrl;
    if (apworldUrl) $("apworld-link").replaceChildren(element("a", { href: apworldUrl, textContent: "Download zora.apworld" }));
  }
  $("guide-link").replaceChildren(
    element("a", { href: ARCHIPELAGO_GUIDE_URL, target: "_blank", rel: "noopener", className: "guide-link",
                   textContent: "The Archipelago guide for ZORA" }),
    ": how to install the world, generate, host and play.");
  $("export-guide-link").href = ARCHIPELAGO_GUIDE_URL;
}

// Asks Python whether the current settings and player settings can become a YAML; shows the answer.
async function refreshMultiworld() {
  if (mode !== MULTIWORLD || !form || !ready) return;
  const request = ++multiworldRequest;
  const { verdict } = await ask("multiworldCheck", { flags: form.flags, zoraFlags: form.zora.ok ? form.zora.flags : "",
                                                     playerSettings: currentPlayerSettings() });
  if (request !== multiworldRequest || mode !== MULTIWORLD) return;
  multiworldVerdict = verdict;
  showProblems();
  updateButton();
}

function savedPlayerName() {
  try { return pageStorage.getItem(PLAYER_NAME_KEY) || ""; } catch { return ""; }
}

let nameRequest = 0;
let nameTouched = false;
async function checkPlayerName() {
  if (!ready) return;
  const name = $("player-name").value;
  try { pageStorage.setItem(PLAYER_NAME_KEY, name); } catch { /* not remembered */ }
  const request = ++nameRequest;
  const { problem } = await ask("nameProblem", { name });
  if (request !== nameRequest) return;
  playerNameProblem = problem;
  const shown = problem && (nameTouched || name.trim() !== "");
  $("player-name-error").textContent = shown ? `Player name: ${problem}.` : "";
  $("player-name").classList.toggle("seed-input--error", Boolean(shown));
  updateButton();
}

function canExport() {
  return ready && form && !flagsPending && $("flags-error").textContent === "" && form.zora.ok
    && playerNameProblem === null && multiworldVerdict !== null && multiworldVerdict.ok;
}

async function onExport() {
  const button = $("export");
  button.disabled = true;
  $("export-result").hidden = true;
  markStepDone("step-generate-num", 3, false);
  const answer = await ask("exportYaml", { name: $("player-name").value, flags: form.flags,
                                           zoraFlags: form.zora.flags, playerSettings: currentPlayerSettings() });
  if (!answer.ok) {
    status(`Not exported: ${answer.reasons.map(plainText).join("; ")}`, "error");
    updateButton();
    return;
  }
  const url = URL.createObjectURL(new Blob([answer.yaml], { type: "text/yaml" }));
  $("yaml-download").replaceChildren(element("a", { id: "yaml-link", className: "btn btn-teal", href: url,
                                                    download: answer.fileName, title: answer.fileName,
                                                    textContent: "Download YAML" }));
  $("yaml-preview").textContent = answer.yaml;
  $("export-result").hidden = false;
  markStepDone("step-generate-num", 3, true);
  status(`Exported ${answer.fileName}.`, "ready");
  updateButton();
}

// ---------------------------------------------------------------------------
// Seed, ROM, generation
// ---------------------------------------------------------------------------

function randomSeed() {
  const [value] = crypto.getRandomValues(new Uint32Array(1));
  $("seed").value = String(value || 1);
  seedTyped = false;
  updateButton();
}

// The player changed the seed: the address names a seed again only after the next generation.
function onSeedChanged() {
  linkSeed = null;
  updateButton();
  updateLink();
}

function canGenerate() {
  return ready && baseRom && form && !flagsPending && $("flags-error").textContent === ""
    && form.zora.ok && form.generateRefusals.length === 0 && musicReady()
    && /^\d+$/.test($("seed").value.trim());
}

function updateButton() {
  $("export").disabled = !canExport();
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

// What the ROM step shows for identify_rom's answer (zora_web.api, zora/rom/revision.py): an
// unmodified release quietly ("PRG1 ROM recognized"), modified graphics in Python's words ("This is
// a PRG0 ROM with modified graphics"), anything else refused with Python's message.
function romStepText(identity) {
  if (!identity.recognized) return { note: "", error: identity.message, status: "Choose the base ROM." };
  const graphics = identity.modifiedGraphics ? ", modified graphics" : "";
  return { note: identity.modifiedGraphics ? identity.message : `${identity.revision} ROM recognized`,
           error: "", status: `Base ROM verified (${identity.revision}${graphics}).` };
}

// PRG0 or PRG1, with or without modified graphics, is accepted; generation takes its bytes as
// they are (generate_rom identifies the ROM again itself). A refused ROM leaves Generate off.
// `read` gives the ROM's bytes; resolves to them when the ROM is accepted, else null.
async function useRom(name, read) {
  const check = ++romChecks;
  baseRom = null;
  romIdentity = null;
  markStepDone("step-rom-num", 1, false);
  $("rom-identity").textContent = "";
  $("rom-error").textContent = "";
  $("rom-remembered").hidden = true;
  updateButton();
  if (!ready) return null;
  const data = await read();
  const { identity } = await ask("check", { bytes: data });
  if (check !== romChecks) return null;         // another ROM was chosen meanwhile
  const shown = romStepText(identity);
  $("rom-label").textContent = name;
  $("rom-identity").textContent = shown.note;
  $("rom-error").textContent = shown.error;
  if (identity.recognized) {
    baseRom = data;
    romIdentity = identity;
    $("rom-btn").textContent = "Change";
    markStepDone("step-rom-num", 1, true);
    status(shown.status);
  } else {
    status(shown.status, "error");
  }
  updateButton();
  refreshLinkSpritePreview();
  return identity.recognized ? data : null;
}

async function onRomChosen() {
  const file = $("rom").files[0];
  if (!file) return;
  const data = await useRom(file.name, async () => new Uint8Array(await file.arrayBuffer()));
  if (data) showRememberedRom(data, await storeBaseRom(file.name, data), REMEMBERED_NOW);
}

// The base ROM, remembered (player request, 2026-10-24): a browser cannot reopen a file by name, so
// the accepted ROM itself is kept in this browser's own storage (IndexedDB), on this machine only and
// never uploaded, and used on the next visit without asking. Where storage is unavailable (a private
// window) nothing is remembered and the step asks for the file each visit, as before.
function storeBaseRom(name, bytes) {
  return browserStore(BASE_ROM_DB, "readwrite", (store, done) => {
    const put = store.put({ name, bytes }, BASE_ROM_KEY);
    put.onsuccess = () => done(true);
    put.onerror = () => done(false);
  });
}

function forgetBaseRom() {
  return browserStore(BASE_ROM_DB, "readwrite", (store, done) => {
    const removed = store.delete(BASE_ROM_KEY);
    removed.onsuccess = removed.onerror = () => done(null);
  });
}

// The remembered line and its Forget button, for the ROM in use when it was stored.
function showRememberedRom(data, stored, text) {
  if (!stored || baseRom !== data) return;
  $("rom-remembered-text").textContent = text;
  $("rom-remembered").hidden = false;
}

// On load: the remembered ROM, checked again as a chosen file is, unless the player chose one first.
async function restoreBaseRom() {
  const saved = await browserStore(BASE_ROM_DB, "readonly", (store, done) => {
    const get = store.get(BASE_ROM_KEY);
    get.onsuccess = () => done(get.result || null);
    get.onerror = () => done(null);
  });
  if (!saved || typeof saved.name !== "string" || !(saved.bytes instanceof Uint8Array) || romChecks) return;
  const check = romChecks + 1;
  const data = await useRom(saved.name, async () => saved.bytes);
  if (data) showRememberedRom(data, true, REMEMBERED_BEFORE);
  else if (romChecks === check) { await forgetBaseRom(); resetRomStep(); }      // no longer accepted
}

// Forget: the stored ROM removed from this browser, and the step back to asking for a file.
async function onForgetRom() {
  ++romChecks;
  await forgetBaseRom();
  resetRomStep();
  status("Choose the base ROM.");
}

function resetRomStep() {
  baseRom = null;
  refreshLinkSpritePreview();
  romIdentity = null;
  $("rom").value = "";
  $("rom-label").textContent = ROM_LABEL;
  $("rom-identity").textContent = "";
  $("rom-error").textContent = "";
  $("rom-remembered").hidden = true;
  $("rom-btn").textContent = "Choose file";
  markStepDone("step-rom-num", 1, false);
  updateButton();
}

// Generate one seed in the worker; resolves to the finished ROM bytes.
// Also used by the measurement run described in docs/packaging.md.
// limitMs: stop generating after this long (GenerationStopped); none for the measurement run.
async function generateSeed(seed, flags = form.flags, zoraFlags = form.zora.flags, limitMs = null) {
  const settings = currentPlayerSettings();
  const random = RANDOM_MUSIC.includes(settings.music);
  const result = await ask("generate", { bytes: baseRom, seed: String(seed), flags, zoraFlags, playerSettings: settings,
                                         limit: limitMs === null ? null : limitMs / 1000,
                                         musicLibraries: random && settings.music === "random-local" ? musicLibraryFiles : null,
                                         musicPlaylist: random ? musicPlaylistText() : null });
  window.zoraTimings.seeds.push({ seed: String(seed), ms: result.ms });
  return { bytes: result.rom, ms: result.ms, flags: result.flags, zoraFlags: result.zoraFlags, seed: result.seed,
           encoded: result.encoded, code: result.code, codeIcons: result.codeIcons,
           tracks: result.tracks || null, musicWarnings: result.musicWarnings || [],
           musicLibraries: result.musicLibraries || [], reportBytes: result.reportRom || null };
}
window.zoraGenerateSeed = generateSeed;

// ---------------------------------------------------------------------------
// After a seed: "View in visualizer" and "Spoiler log" (encoding off only).
// Both come from one report the worker builds from the finished ROM
// (zora_web.api.seed_report): the seed document and the spoiler log, which
// therefore cannot disagree. Making it changes nothing in the ROM.
// ---------------------------------------------------------------------------

// The owner's Z1R Visualizer. A test may point the page elsewhere first.
const VISUALIZER_URL = "https://tetraly.github.io/z1r-visualizer/";
const VISUALIZER_PROTOCOL = 1;
// The visualizer says "ready" for up to 30 s; past that, stop listening.
const VISUALIZER_WAIT_MS = 35000;

function seedReport(result) {
  if (!result.report) {
    // With randomized music, the ROM before the music: the report reads a 128 KB ROM.
    result.report = ask("report", { bytes: result.reportBytes || result.bytes, seed: result.seed, flags: result.flags,
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

// The seed code as its item names, comma-separated: what "Copy seed code" copies (for a race room
// such as racetime.gg; owner, 2026-10-17) and the bug report's last line.
function seedCodeText(code) {
  return code.join(", ");
}

// The seed code as pictures (owner's backlog, 2026-10-18): each item as the player's own ROM draws it
// on the file-select screen, its tiles and palette (zora.rom.seed_code_icons: custom sprites, the
// Pegasus Boots and the tunic color show as in the game), beside its name, which stays the text that
// screen readers read and copying copies.
const SEED_CODE_ICON_SIZE = 16;

// An icon's 16 rows of NES palette values as a canvas's RGBA pixels.
function iconRgba(pixels) {
  const rgba = new Uint8ClampedArray(SEED_CODE_ICON_SIZE * SEED_CODE_ICON_SIZE * 4);
  pixels.flat().forEach((color, index) => {
    const rgb = NES_PALETTE[color];
    rgba.set([1, 3, 5].map((start) => parseInt(rgb.slice(start, start + 2), 16)).concat(255), index * 4);
  });
  return rgba;
}

// One seed-code item: its icon, when Python drew one, and its name.
function seedCodeItem(name, pixels) {
  const item = element("span", { className: "seed-code-item" });
  if (pixels) {
    const canvas = element("canvas", { className: "seed-code-icon", width: SEED_CODE_ICON_SIZE,
                                       height: SEED_CODE_ICON_SIZE, ariaHidden: "true" });
    canvas.getContext("2d").putImageData(new ImageData(iconRgba(pixels), SEED_CODE_ICON_SIZE), 0, 0);
    item.append(canvas);
  }
  item.append(element("span", { className: "seed-code-name", textContent: name }));
  return item;
}

// "Copy bug report info" (owner's triage, 2026-10-17): one block a player pastes into a bug report,
// enough to make the same game again: the page's version, the seed, both flag strings as asked for
// (the page never shows what Random resolved to), the ROM and the seed code as its item names.
function bugReportText(info) {
  const graphics = info.identity.modifiedGraphics ? ", modified graphics" : "";
  return [`ZORA ${info.version}`, `Seed: ${info.seed}`, `Z1R flags: ${info.flags}`,
          `ZORA flags: ${info.zoraFlags || "(none)"}`, `ROM: ${info.identity.revision}${graphics}`,
          `Seed code: ${info.code.length ? seedCodeText(info.code) : "(none)"}`].join("\n");
}

// "Copy race info" (owner, 2026-10-22): a short block for a race channel such as Discord: the
// version, the seed, the strings as asked for, the seed code (its item names, or the four
// characters the screen shows under Item Sprites), the race status and any notice (a postponed
// setting, B06). The race status is B82, one switch: the original's Race ROM, the spec's tournament
// mode, this page's "Encode level data". On, the level data is encoded and ZORA makes no spoiler log
// for the seed; off, anyone with the flags and seed can make one.
const RACE_ROM_ON = "Race ROM: on (level data encoded, no spoiler log)";
const RACE_ROM_OFF = "Race ROM: off (spoiler log available)";

function raceInfoText(info) {
  const spoiler = info.encoded ? RACE_ROM_ON : RACE_ROM_OFF;
  return [`ZORA ${info.version}`, `Seed: ${info.seed}`, `Flags: ${info.flags}`,
          ...(info.zoraFlags ? [`ZORA flags: ${info.zoraFlags}`] : []),
          ...(info.code.length ? [`Seed code: ${seedCodeText(info.code)}`] : []),
          spoiler, ...info.notices.map((text) => `Notice: ${text}.`)].join("\n");
}

// The clipboard API, or, where the browser refuses it, a selected text area and the copy command.
async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    const area = element("textarea", { value: text, readOnly: true });
    area.style.position = "fixed";
    area.style.opacity = "0";
    document.body.append(area);
    area.select();
    const copied = document.execCommand("copy");
    area.remove();
    return copied;
  }
}

// A button that copies `text` and says so, or shows the text where the browser will not copy.
function copyButton(id, label, text, copied) {
  const button = element("button", { type: "button", id, className: "btn btn-outline", textContent: label });
  button.addEventListener("click", async () => {
    if (await copyText(text)) showAfterSeed(copied, "ready");
    else showAfterSeed(`The browser would not copy. Select this and copy it yourself:\n${text}`, "error");
  });
  return button;
}

// "Copy bug report info", "Copy race info", then "Copy seed code" when the seed has one.
function addCopyButtons(info) {
  $("download").append(copyButton("copy-bug-report", "Copy bug report info", bugReportText(info),
                                  "Bug report info copied. Paste it into your report."),
                       copyButton("copy-race-info", "Copy race info", raceInfoText(info),
                                  "Race info copied. Paste it into your race channel."));
  if (info.code.length) {
    $("download").append(copyButton("copy-seed-code", "Copy seed code", seedCodeText(info.code), "Seed code copied."));
  }
}

// The result's Music entry: the library files, then the tracks and the warnings (which can name
// tracks). Under Hide track list (TheGobOne's request for beta 9) the tracks and warnings wait behind
// a button, so a player can be surprised and still look later; the copy buttons never carry them.
function musicResult(result, hidden) {
  const music = element("dd");
  if (result.musicLibraries.length) {
    music.append(element("p", { className: "panel-note", textContent: "Library: " +
      result.musicLibraries.map(([name, id]) => `${name} (${id})`).join(", ") }));
  }
  const tracks = element("div", { className: "music-track-list" },
                         element("ul", { className: "music-tracks" },
                                 ...result.tracks.map(([area, title]) => element("li", { textContent: `${area}: ${title}` }))),
                         ...result.musicWarnings.map((warning) => element("p", { className: "panel-note", textContent: warning })));
  if (!hidden) {
    music.prepend(tracks);
    return music;
  }
  const reveal = element("button", { type: "button", id: "show-music-tracks", className: "btn btn-outline",
                                     textContent: "Show track list" });
  const note = element("p", { className: "panel-note", textContent: "Track list hidden (Hide track list)." });
  reveal.addEventListener("click", () => {
    note.remove();
    reveal.replaceWith(tracks);
  });
  music.prepend(note, reveal);
  return music;
}

// One seed within GENERATION_LIMIT_MS: a page-chosen seed that runs out of time or fails is replaced
// by a new one while time is left (the seed box shows each); a typed seed is tried once.
async function generateWithinLimit() {
  const started = performance.now();
  for (;;) {
    const seed = $("seed").value.trim();
    const left = GENERATION_LIMIT_MS - (performance.now() - started);
    try {
      return await generateSeed(seed, form.flags, form.zora.flags, seedTyped ? left : Math.min(left, CHOSEN_SEED_MS));
    } catch (err) {
      const replaceable = !seedTyped && (STOPPED.test(err.message) || GENERATION_FAILED.test(err.message));
      if (!replaceable || GENERATION_LIMIT_MS - (performance.now() - started) < RETRY_MIN_MS) {
        if (!STOPPED.test(err.message)) throw err;
        throw new Error(seedTyped
          ? `Seed ${seed} took longer than ${GENERATION_LIMIT_MS / 1000} s to generate. Try another seed.`
          : `No seed was ready within ${GENERATION_LIMIT_MS / 1000} s with these settings. Press Generate to `
            + "try again, or change the settings.");
      }
      randomSeed();
      status(`Generating seed ${$("seed").value}…`);
    }
  }
}

async function onGenerate() {
  const seed = $("seed").value.trim();
  // What the player asked for. Owner ruling: the page never shows what a
  // Random field resolved to, so the result shows these and not the resolved
  // flags. Encode level data is on or off, never Random, so `encoded` is the switch.
  const requested = { flags: form.flags, zoraFlags: form.zora.flags, notices: form.notices || [],
                      encoded: form.fields[metadata.encodeLevelData].value === TOGGLE_ON,
                      hideTracks: playerSettings.musicHideTrackList === "on" };
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
    const result = await generateWithinLimit();
    const url = URL.createObjectURL(new Blob([result.bytes], { type: "application/octet-stream" }));
    const name = `zora-seed-${result.seed}${requested.encoded ? "-encoded" : ""}${result.tracks ? "-music" : ""}.nes`;
    $("download").append(element("a", { id: "download-link", className: "btn btn-teal", href: url,
                                        download: name, title: name, textContent: "Download ROM" }));
    // A seed made with "Encode level data" stays unreadable: no spoiler, no visualizer.
    if (!requested.encoded) addSeedReportButtons(result);
    $("result").append(element("dt", { textContent: "Seed" }), element("dd", { textContent: result.seed }),
                       element("dt", { textContent: "Z1R flags" }), element("dd", { textContent: requested.flags }));
    if (requested.zoraFlags) {
      $("result").append(element("dt", { textContent: "ZORA flags" }), element("dd", { textContent: requested.zoraFlags }));
    }
    // What the seed leaves out of what was asked for (a postponed setting: Mirrored Overworld, B06)
    for (const notice of requested.notices) {
      $("result").append(element("dt", { textContent: "Notice" }),
                         element("dd", { className: "result-notice", textContent: `${plainText(notice)}.` }));
    }
    // Under Item Sprites other than normal the screen shows the code as four characters (FP-SPRITE-01)
    const code = typeof result.codeText === "string" ? [result.codeText]
      : Array.isArray(result.code) && result.code.length === SEED_CODE_LENGTH ? result.code : [];
    if (result.tracks) $("result").append(element("dt", { textContent: "Music" }), musicResult(result, requested.hideTracks));
    // The ROM as identified when it was chosen: another chosen later does not change this seed's.
    addCopyButtons({ version: $("version").textContent, seed: result.seed, flags: requested.flags,
                     zoraFlags: requested.zoraFlags, identity: romIdentity, code,
                     encoded: requested.encoded, notices: requested.notices });
    // The seed code (four items, with their icons), once Python reports one.
    if (code.length) {
      const icons = Array.isArray(result.codeIcons) && result.codeIcons.length === code.length ? result.codeIcons : [];   // none for text
      $("seed-code").append(...code.map((name, index) => seedCodeItem(name, icons[index])));
      $("seed-code-row").hidden = false;
    }
    $("gen-time").textContent = `Generated in ${(result.ms / 1000).toFixed(1)} s`;
    $("generate-result").hidden = false;
    markStepDone("step-generate-num", 3, true);
    status(`Seed ${result.seed} generated.`, "ready");
    linkSeed = String(result.seed);
    updateLink();
  } catch (err) {
    const notProduced = err.message.indexOf(NOT_PRODUCED_REFUSAL);
    if (MUSIC_PROBLEM.test(err.message)) status(`The music could not be made: ${err.message.replace(MUSIC_PROBLEM, "")}`, "error");
    else status(notProduced < 0 ? `Generation failed: ${err.message}`
      : `${NOT_IMPLEMENTED}: ${err.message.slice(notProduced + NOT_PRODUCED_REFUSAL.length)}`, "error");
  }
  button.textContent = "Generate";
  updateButton();
}

initThemeToggle();
$("rom-btn").addEventListener("click", () => $("rom").click());
$("rom").addEventListener("change", onRomChosen);
$("rom-forget").addEventListener("click", onForgetRom);
$("presets-btn").addEventListener("click", openPresets);
$("presets-close").addEventListener("click", closePresets);
$("settings-save").addEventListener("click", saveSettingsFile);
$("settings-load").addEventListener("click", () => $("settings-file").click());
$("settings-file").addEventListener("change", loadSettingsFile);
// A click on the dimmed page around the window closes it.
$("presets").addEventListener("click", (event) => {
  const box = $("presets").getBoundingClientRect();
  const outside = event.clientX < box.left || event.clientX > box.right || event.clientY < box.top || event.clientY > box.bottom;
  if (event.target === $("presets") && outside) closePresets();
});
$("seed").addEventListener("input", () => { seedTyped = true; onSeedChanged(); });
$("new-seed").addEventListener("click", () => { randomSeed(); onSeedChanged(); });
$("flags").addEventListener("input", onFlagsTyped);
$("flags").addEventListener("change", onFlagsCommitted);
$("zora-flags").addEventListener("input", onFlagsTyped);
$("zora-flags").addEventListener("change", onFlagsCommitted);
$("generate").addEventListener("click", onGenerate);
$("mode-single").addEventListener("click", () => { if (mode !== SINGLE) setMode(SINGLE); });
$("mode-multiworld").addEventListener("click", () => { if (mode !== MULTIWORLD) setMode(MULTIWORLD); });
$("player-name").value = savedPlayerName();
$("player-name").addEventListener("input", checkPlayerName);
$("player-name").addEventListener("blur", () => { nameTouched = true; checkPlayerName(); });
$("export").addEventListener("click", onExport);
// The hero graphic comes up out of the water (owner, 2026-10-30): the masthead's waves stretch with the
// window and the hero is centred, so the water's height under the logo changes with the width. Read the front
// wave's surface under the logo from its own shape (isPointInFill, in the waves' viewBox) and move the logo
// so the wave's lowest point under it covers HERO_LOGO_DIP of its height; a transform, so the layout never moves.
const HERO_LOGO_DIP = 0.05;
const HERO_LOGO_SAMPLES = [0.3, 0.5, 0.7];          // across the logo's width, where its foot is

function tuckHeroLogo() {
  const logo = document.querySelector(".hero-logo");
  const waves = document.querySelector(".masthead .waves");
  const front = waves && waves.querySelector(".wave-1");
  if (!logo || !front || !logo.complete || !logo.naturalWidth) return;
  logo.style.transform = "";
  const box = waves.getBoundingClientRect(), logoBox = logo.getBoundingClientRect(), view = waves.viewBox.baseVal;
  const surfaceAt = (fraction) => {
    const x = (logoBox.left + logoBox.width * fraction - box.left) * view.width / box.width;
    let y = 0;
    while (y < view.height && !front.isPointInFill(new DOMPoint(x, y))) y += 0.5;
    return box.top + y * box.height / view.height;
  };
  const lowestSurface = Math.max(...HERO_LOGO_SAMPLES.map(surfaceAt));
  logo.style.transform = `translateY(${lowestSurface + logoBox.height * HERO_LOGO_DIP - logoBox.bottom}px)`;
}

showWorldLinks();
if (mode === MULTIWORLD) setMode(MULTIWORLD);
document.querySelector(".hero-logo")?.addEventListener("load", tuckHeroLogo);
window.addEventListener("resize", tuckHeroLogo);
document.fonts?.ready.then(tuckHeroLogo);
tuckHeroLogo();
randomSeed();
if (linkSeed) {                                      // a shared link's seed (single player)
  $("seed").value = linkSeed;
  seedTyped = true;
}
const bootStart = performance.now();
if (EMBEDDED_INFO) {
  worker.postMessage({ type: "init", version: PYODIDE_VERSION, wheelBytes: embeddedWheel(), classic: true });
} else {
  fetch(WHEEL_INFO_URL).then((response) => response.json()).then(({ wheel }) => worker.postMessage(
    { type: "init", version: PYODIDE_VERSION, wheelUrl: new URL(`dist/${wheel}`, location.href).href }))
    .catch((err) => status(`Could not load Python: no wheel listed in dist/wheel.json (${err.message})`, "error"));
}
