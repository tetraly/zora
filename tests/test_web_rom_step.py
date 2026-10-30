"""The web page's ROM step (web/zora-web.js, web/zora-worker.js) on zora_web.api.identify_rom
(zora/rom/revision.py; docs/design/prg1.md): an unmodified PRG0 or PRG1 ROM accepted quietly, a
ROM with modified graphics accepted with Python's message, any other refused with it, Generate
on or off to match; the accepted ROM remembered in the browser (IndexedDB) for the next visit until
Forget, and nothing remembered without storage; and the worker's glue generating from the
player's ROM as Python does."""
import json
import re
import shutil
import subprocess
from functools import cache
from pathlib import Path
from typing import Any

import pytest

from zora.generate.pipeline import generate_rom
from zora.rom.base_rom import BASE_ROM_PATH, PRG1_ROM_PATH
from zora.rom.revision import GRAPHICS_BLOCKS, NES_HEADER_SIZE, NOT_RECOGNIZED
from zora_web import api

REPO = Path(__file__).resolve().parent.parent
PAGE = (REPO / "web" / "index.html").read_text()
PAGE_SCRIPT = (REPO / "web" / "zora-web.js").read_text()
WORKER = (REPO / "web" / "zora-worker.js").read_text()
FLAGS = api.flag_form.metadata()["defaultFlags"]
SEED = 2535214729
REMEMBERED_NOW, REMEMBERED_BEFORE = (re.search(rf'^const {name} = "(.*)";$', PAGE_SCRIPT, re.MULTILINE).group(1)  # type: ignore[union-attr]
                                     for name in ("REMEMBERED_NOW", "REMEMBERED_BEFORE"))
LEVEL_DATA_BYTE = NES_HEADER_SIZE + 0x18710      # outside every graphics block

needs_prg0 = pytest.mark.skipif(not BASE_ROM_PATH.exists(), reason="needs the base ROM")
needs_prg1 = pytest.mark.skipif(not PRG1_ROM_PATH.exists(), reason="PRG1 ROM not found")


@cache
def prg0() -> bytes:
    return BASE_ROM_PATH.read_bytes()


@cache
def prg1() -> bytes:
    return PRG1_ROM_PATH.read_bytes()


def graphics_inverted(rom: bytes) -> bytes:
    """`rom` with every byte of every pattern block inverted: modified graphics."""
    image = bytearray(rom)
    for _name, offset, length in GRAPHICS_BLOCKS:
        start = NES_HEADER_SIZE + offset
        image[start:start + length] = bytes(value ^ 0xFF for value in image[start:start + length])
    return bytes(image)


def one_byte_changed(rom: bytes) -> bytes:
    """`rom` with one level-data byte changed: no release, so refused."""
    image = bytearray(rom)
    image[LEVEL_DATA_BYTE] ^= 0x01
    return bytes(image)


class JsBytes:
    """What the worker hands the glue: a Pyodide proxy of a Uint8Array."""

    def __init__(self, data: bytes) -> None:
        self.data = data

    def to_py(self) -> memoryview:
        return memoryview(self.data)


@cache
def glue() -> dict[str, Any]:
    """The worker's Python glue, run here."""
    match = re.search(r"const GLUE = `\n(.*?)`;", WORKER, re.DOTALL)
    assert match
    names: dict[str, Any] = {}
    exec(match.group(1), names)
    return names


# --- the page: each outcome's text and Generate ------------------------------------------------

def page_function(name: str) -> str:
    """A top-level function's source from web/zora-web.js, async or not."""
    match = re.search(rf"^(?:async )?function {name}\(.*?^}}\n", PAGE_SCRIPT, re.MULTILINE | re.DOTALL)
    assert match, name
    return match.group(0)


ROM_STEP_FUNCTIONS = ("romStepText", "useRom", "onRomChosen", "browserStore", "storeBaseRom", "forgetBaseRom",
                      "showRememberedRom", "restoreBaseRom", "onForgetRom", "resetRomStep", "canGenerate",
                      "updateButton")
# The page's constants those functions read, from the page itself
ROM_STEP_CONSTANTS = "\n".join(
    re.search(rf"^(?:let|const) {name} = .*$", PAGE_SCRIPT, re.MULTILINE).group(0)  # type: ignore[union-attr]
    for name in ("romChecks", "BASE_ROM_DB", "BASE_ROM_KEY", "REMEMBERED_NOW", "REMEMBERED_BEFORE"))


# The page around onRomChosen, stubbed: its elements, a worker answering with `identity`, a form
# that may generate and a seed, so Generate is on exactly when the ROM is accepted.
ROM_STEP_PAGE = """
const elements = {};
const $ = (id) => (elements[id] ||= { id, textContent: "", disabled: false, value: "",
                                       classList: { toggle() {} }, files: [] });
let ready = true, flagsPending = false, baseRom = null, romIdentity = null;
const form = { zora: { ok: true }, generateRefusals: [] };
const statuses = [];
const status = (text, kind) => statuses.push([text, kind || ""]);
const canExport = () => false;
const musicReady = () => true;
const markStepDone = (id, number, done) => { elements[id + ":done"] = done; };
// The Link sprite preview redraws from the ROM; it has its own tests (test_link_sprite*.py, test_link_art.py)
const refreshLinkSpritePreview = () => {};
$("seed").value = "123";
const ROM_LABEL = "Legend of Zelda, The (USA), PRG0 or PRG1 release, as a .nes file.";
$("rom-label").textContent = ROM_LABEL;
$("rom-remembered").hidden = true;
"""
ROM_STEP_HARNESS = """
const answers = IDENTITIES;
const shown = {};
(async () => {
  for (const [name, identity] of Object.entries(answers)) {
    ask = async () => ({ identity });
    $("rom").files = [{ name: name + ".nes", arrayBuffer: async () => new ArrayBuffer(4) }];
    await onRomChosen();
    shown[name] = { label: $("rom-label").textContent, note: $("rom-identity").textContent,
                    error: $("rom-error").textContent, generateDisabled: $("generate").disabled,
                    done: elements["step-rom-num:done"], accepted: baseRom !== null, status: statuses.at(-1),
                    remembered: !$("rom-remembered").hidden };
  }
  console.log(JSON.stringify(shown));
})();
"""


def run_on_stubbed_page(harness: str) -> dict[str, dict[str, Any]]:
    """`harness` run under Node with the ROM step's functions and constants; what it prints."""
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is not installed")
    functions = [page_function(name) for name in ROM_STEP_FUNCTIONS]
    source = "\n".join(["let ask;", ROM_STEP_CONSTANTS, *functions, ROM_STEP_PAGE, harness])
    result: dict[str, dict[str, Any]] = json.loads(
        subprocess.run([node, "-e", source], capture_output=True, text=True, check=True).stdout)
    return result


def run_rom_step(identities: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Choose each named ROM in turn on the stubbed page; what the ROM step then shows."""
    return run_on_stubbed_page(ROM_STEP_HARNESS.replace("IDENTITIES", json.dumps(identities)))


@needs_prg0
@needs_prg1
def test_each_outcome_shows_its_text_and_sets_generate() -> None:
    """PRG0 and PRG1 quietly recognized, modified graphics in Python's words (Generate on for all
    three), any other ROM refused with exactly the Discord message and Generate off. A refusal
    after an accepted ROM turns Generate off again; an accepted one after it turns it back on."""
    roms = {"prg0": prg0(), "prg1": prg1(), "prg0-graphics": graphics_inverted(prg0()),
            "prg1-graphics": graphics_inverted(prg1()), "refused": one_byte_changed(prg0()),
            "prg1-again": prg1()}
    shown = run_rom_step({name: json.loads(glue()["identify"](JsBytes(rom))) for name, rom in roms.items()})
    expected_notes = {"prg0": "PRG0 ROM recognized", "prg1": "PRG1 ROM recognized",
                      "prg0-graphics": "This is a PRG0 ROM with modified graphics",
                      "prg1-graphics": "This is a PRG1 ROM with modified graphics", "refused": "",
                      "prg1-again": "PRG1 ROM recognized"}
    for name, note in expected_notes.items():
        accepted = name != "refused"
        assert shown[name]["label"] == f"{name}.nes"
        assert shown[name]["note"] == note
        assert shown[name]["error"] == ("" if accepted else NOT_RECOGNIZED)
        assert shown[name]["accepted"] is accepted and shown[name]["done"] is accepted
        assert shown[name]["generateDisabled"] is not accepted, name
        assert not shown[name]["remembered"]           # Node has no IndexedDB: nothing is remembered
    assert NOT_RECOGNIZED == ("ROM not recognized. If you believe this is in error, "
                              "please file a bug in the ZORA Discord")
    assert shown["prg1"]["status"] == ["Base ROM verified (PRG1).", ""]
    assert shown["prg0-graphics"]["status"] == ["Base ROM verified (PRG0, modified graphics).", ""]
    assert shown["refused"]["status"] == ["Choose the base ROM.", "error"]


# The remembered ROM (player request, 2026-10-24) on an in-memory IndexedDB ("works"), one whose
# open fails ("fails", as some private windows do) or none at all ("missing"): a ROM chosen, the next
# visit (the page's state cleared, the stored ROM restored), Forget, and a visit after it.
MEMORY_HARNESS = """
const databases = new Map();
const answer = (result) => { const request = { result }; setTimeout(() => request.onsuccess?.()); return request; };
const objectStore = (data) => ({ put: (value, key) => (data.set(key, value), answer()),
                                 get: (key) => answer(data.get(key)), delete: (key) => (data.delete(key), answer()) });
globalThis.indexedDB = MODE === "missing" ? undefined : { open(name) {
  const request = {};
  setTimeout(() => {
    if (MODE === "fails") { request.onerror?.(); return; }
    const created = !databases.has(name);
    if (created) databases.set(name, new Map());
    request.result = { createObjectStore() {}, transaction: () => ({ objectStore: () => objectStore(databases.get(name)) }) };
    if (created) request.onupgradeneeded?.();
    request.onsuccess();
  });
  return request;
} };
const snapshot = () => ({ label: $("rom-label").textContent, note: $("rom-identity").textContent,
                          remembered: $("rom-remembered").hidden ? null : $("rom-remembered-text").textContent,
                          accepted: baseRom !== null, generateDisabled: $("generate").disabled,
                          button: $("rom-btn").textContent, stored: Boolean(databases.get(BASE_ROM_DB)?.has(BASE_ROM_KEY)) });
const nextVisit = () => { resetRomStep(); romChecks = 0; $("rom").files = []; };
(async () => {
  const shown = {};
  ask = async () => ({ identity: IDENTITY });
  $("rom").files = [{ name: "zelda.nes", arrayBuffer: async () => new ArrayBuffer(4) }];
  await onRomChosen();
  shown.chosen = snapshot();
  nextVisit();
  await restoreBaseRom();
  shown.restored = snapshot();
  await onForgetRom();
  shown.forgotten = snapshot();
  nextVisit();
  await restoreBaseRom();
  shown.afterForget = snapshot();
  console.log(JSON.stringify(shown));
})();
"""
CHOOSE_FILE = {"label": "Legend of Zelda, The (USA), PRG0 or PRG1 release, as a .nes file.", "note": "",
               "remembered": None, "accepted": False, "generateDisabled": True, "button": "Choose file",
               "stored": False}


def remembered_rom(mode: str) -> dict[str, dict[str, Any]]:
    identity = {"recognized": True, "revision": "PRG0", "modifiedGraphics": False, "message": ""}
    return run_on_stubbed_page(MEMORY_HARNESS.replace("MODE", json.dumps(mode))
                               .replace("IDENTITY", json.dumps(identity)))


def test_the_rom_is_remembered_used_next_visit_and_forgotten() -> None:
    shown = remembered_rom("works")
    in_use = {"label": "zelda.nes", "note": "PRG0 ROM recognized", "accepted": True, "generateDisabled": False,
              "button": "Change", "stored": True}
    assert shown["chosen"] == {**in_use, "remembered": REMEMBERED_NOW}
    assert shown["restored"] == {**in_use, "remembered": REMEMBERED_BEFORE}
    assert shown["forgotten"] == shown["afterForget"] == CHOOSE_FILE


@pytest.mark.parametrize("mode", ["fails", "missing"])
def test_without_storage_the_rom_works_and_is_not_remembered(mode: str) -> None:
    """A private window: the chosen ROM is used, no remembered line, and the next visit asks again."""
    shown = remembered_rom(mode)
    assert shown["chosen"] == {"label": "zelda.nes", "note": "PRG0 ROM recognized", "remembered": None,
                               "accepted": True, "generateDisabled": False, "button": "Change", "stored": False}
    assert shown["restored"] == shown["forgotten"] == shown["afterForget"] == CHOOSE_FILE


def test_the_remembered_rom_stays_in_the_browser() -> None:
    """Kept in the page's own IndexedDB and never sent anywhere: the only request carrying the ROM's
    bytes is the worker's check and generation."""
    assert page_function("storeBaseRom").count("store.put({ name, bytes }, BASE_ROM_KEY)") == 1
    assert "fetch(" not in "".join(page_function(name) for name in ROM_STEP_FUNCTIONS)


def test_the_rom_step_has_its_lines_and_no_prg0_only_wording() -> None:
    """The step names both releases and has a line for the identification beside its error."""
    assert "PRG0 or PRG1 release, as a .nes file." in PAGE
    assert re.search(r'<p class="step-note" id="rom-identity" role="status"></p>\s*'
                     r'<p class="step-error" id="rom-error" role="alert"></p>', PAGE)
    assert "not the PRG0 release" not in PAGE_SCRIPT
    assert "check_rom" not in WORKER and "EXPECTED_SHA1" not in WORKER


def test_the_rom_step_is_single_player_only() -> None:
    """Multiworld mode hides the ROM step (it exports a YAML; no ROM is read)."""
    assert '$("step-rom").hidden = multiworld;' in PAGE_SCRIPT


# --- the worker: identify_rom's answer and generation from the player's ROM ---------------------

@needs_prg0
@needs_prg1
def test_the_worker_answers_as_identify_rom() -> None:
    for rom in (prg0(), prg1(), graphics_inverted(prg1()), one_byte_changed(prg1()), bytes(16)):
        assert json.loads(glue()["identify"](JsBytes(rom))) == api.identify_rom(rom)


@needs_prg0
@needs_prg1
@pytest.mark.parametrize("release", ["prg0", "prg1", "prg1-graphics"])
def test_the_worker_generates_from_the_players_rom_as_python_does(release: str) -> None:
    """The glue's generate on PRG0, PRG1 and a PRG1 ROM with modified graphics: the bytes
    generate_rom makes from that ROM. PRG1's game is PRG0's in PRG1's layout, so it differs."""
    rom = {"prg0": prg0(), "prg1": prg1(), "prg1-graphics": graphics_inverted(prg1())}[release]
    made = bytes(glue()["generate"](JsBytes(rom), str(SEED), FLAGS, "{}", ""))
    assert made == generate_rom(FLAGS, SEED, rom).rom
    if release != "prg0":
        assert made != generate_rom(FLAGS, SEED, prg0()).rom
