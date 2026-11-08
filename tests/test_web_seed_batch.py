"""Several seeds at once (issue #16; web/zora-web.js): Number of seeds counts up from the seed box, each
seed made as Generate makes that seed alone (generateSeed with the same flags and time limit), a seed
that fails reported while the batch carries on, Stop keeping the seeds already made, and the page's
store-only .zip writer read back by Python's zipfile. Run in Node on the page's own functions; the
byte-for-byte check runs the worker's glue in this process and each seed alone in a fresh one."""
import base64
import io
import json
import re
import shutil
import subprocess
import sys
import zipfile
import zlib
from pathlib import Path
from typing import Any

import pytest

from zora.rom.base_rom import BASE_ROM_PATH
from zora_web import api

REPO = Path(__file__).resolve().parent.parent
PAGE = (REPO / "web" / "index.html").read_text()
PAGE_SCRIPT = (REPO / "web" / "zora-web.js").read_text()
WORKER = (REPO / "web" / "zora-worker.js").read_text()
FLAGS = api.flag_form.metadata()["defaultFlags"]
CONSTANTS = ("SEED_LIMIT", "GENERATION_LIMIT_MS", "ZIP_SEED_LIMIT", "FOLDER_SEED_LIMIT", "BATCH_ZIP", "BATCH_FOLDER",
             "ZIP_TYPE", "ZIP_LOCAL_HEADER", "ZIP_CENTRAL_HEADER", "ZIP_END", "ZIP_VERSION", "ZIP_UTF8_NAMES",
             "ZIP_STORED", "ZIP_MAX_FILES", "ZIP_MAX_BYTES", "NOT_PRODUCED_REFUSAL", "NOT_IMPLEMENTED", "MUSIC_PROBLEM")
ZIP_FUNCTIONS = ["crc32", "dosDateTime", "zipStore"]


def page_function(name: str) -> str:
    match = re.search(rf"^(?:async )?function {name}\(.*?^}}\n", PAGE_SCRIPT, re.MULTILINE | re.DOTALL)
    assert match, name
    return match.group(0)


def page_constant(name: str) -> str:
    """A constant's definition: its line, or CRC32_TABLE's lines."""
    whole = r".*?^\}\);$" if name == "CRC32_TABLE" else "[^\n]*"
    match = re.search(rf"^const {name} = {whole}", PAGE_SCRIPT, re.MULTILINE | re.DOTALL)
    assert match, name
    return match.group(0)


def run(functions: list[str], script: str) -> Any:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is not installed")
    source = "\n".join([*map(page_constant, [*CONSTANTS, "CRC32_TABLE"]), *map(page_function, functions), script])
    return json.loads(subprocess.run([node], input=source, capture_output=True, text=True, check=True).stdout)


# --- the .zip writer ------------------------------------------------------------------------------

SAMPLES = {"zora-seed-123.nes": bytes(range(256)) * 520, "empty.txt": b"",
           "zora-spoiler-123.txt": "Level 9: Triforce of Power — ÄÖ\n".encode() * 40,
           "naïve name.json": b'{"a": 1}'}


def test_crc32_matches_zlib() -> None:
    samples = [b"", b"a", b"123456789", bytes(range(256)) * 3]
    answers = run(["crc32"], f"const samples = {json.dumps([list(s) for s in samples])};\n"
                             "console.log(JSON.stringify(samples.map((s) => crc32(Uint8Array.from(s)))));")
    assert answers == [zlib.crc32(sample) for sample in samples]


def test_pythons_zipfile_reads_the_pages_zip() -> None:
    files = [{"name": name, "bytes": base64.b64encode(data).decode()} for name, data in SAMPLES.items()]
    answer = run(ZIP_FUNCTIONS,
                 f"const files = {json.dumps(files)}"
                 ".map(({name, bytes}) => ({name, bytes: Buffer.from(bytes, 'base64')}));\n"
                 "const parts = zipStore(files, new Date(2026, 10, 7, 13, 45, 30));\n"
                 "console.log(JSON.stringify(Buffer.concat(parts.map((p) => Buffer.from(p))).toString('base64')));")
    with zipfile.ZipFile(io.BytesIO(base64.b64decode(answer))) as archive:
        assert archive.testzip() is None                     # every CRC checks
        assert archive.namelist() == list(SAMPLES)
        for info in archive.infolist():
            assert info.compress_type == zipfile.ZIP_STORED
            assert info.date_time == (2026, 11, 7, 13, 45, 30)
            assert archive.read(info) == SAMPLES[info.filename]


# --- the seeds a batch makes ----------------------------------------------------------------------

def test_a_batch_counts_up_from_the_seed_box() -> None:
    answers = run(["batchSeeds", "seedCount"],
                  "console.log(JSON.stringify({\n"
                  "  five: batchSeeds('123', 5), one: batchSeeds('7', 1),\n"
                  "  top: batchSeeds(String(SEED_LIMIT - 3n), 3), over: batchSeeds(String(SEED_LIMIT - 3n), 4),\n"
                  "  counts: ['1', '100', '101', '0', '', 'x', '1000', '1001', ' 5', '2.5']"
                  ".map((t) => [seedCount(t, ZIP_SEED_LIMIT), seedCount(t, FOLDER_SEED_LIMIT)]),\n"
                  "}));")
    assert answers["five"] == ["123", "124", "125", "126", "127"]
    assert answers["one"] == ["7"]
    assert answers["top"] == [str(2 ** 64 - 3), str(2 ** 64 - 2), str(2 ** 64 - 1)]
    assert answers["over"] is None
    assert answers["counts"] == [[1, 1], [100, 100], [None, 101], [None, None], [None, None], [None, None],
                                 [None, 1000], [None, None], [None, None], [None, None]]


# onGenerateBatch on a stubbed page: a worker that makes each seed (seed 125 fails), the zip chosen, and
# Stop pressed while STOP_AT is being made. What it asked generateSeed for, the zip's files and the card.
BATCH_HARNESS = """
const element = (tag, props = {}) => ({ tag, ...props });
const stub = () => new Proxy({ classList: { toggle() {} }, querySelectorAll: () => [] }, { get: (target, key) =>
  key in target ? target[key] : (key === "hasChildNodes" ? () => false
    : ["replaceChildren", "append"].includes(key) ? (...children) => { target.children = children; } : () => {}),
  set: (target, key, value) => { target[key] = value; return true; } });
const nodes = {};
const $ = (id) => (nodes[id] ||= stub());
let clock = 0;
const performance = { now: () => clock };
const blobs = [];
const URL = { createObjectURL: (blob) => { blobs.push(blob); return "blob:zip"; } };
const statuses = [];
const status = (text, kind) => statuses.push(text);
const markStepDone = () => {}, updateButton = () => {}, getSetting = () => null;
const window = {};
let batch = null, mode = "single";
const metadata = { encodeLevelData: "B82" };
const form = { flags: "FLAGS", zora: { ok: true, flags: "ZORA" }, fields: { B82: { value: 0 } } };
const TOGGLE_ON = 1;
const asked = [];
async function generateSeed(seed, flags, zoraFlags, limitMs) {
  asked.push([seed, flags, zoraFlags, limitMs]);
  clock += 1500;
  if (seed === STOP_AT) onStopBatch();
  if (seed === "125") throw new Error("generation failed after 3 attempts");
  return { seed, bytes: new TextEncoder().encode("ROM " + seed), spoilerLevel: seed === "124" ? 2 : 0, tracks: null };
}
const seedReport = async (result) => ({ spoiler: "log " + result.seed,
                                        spoilerName: `zora-seed-${result.seed}-spoiler.txt`,
                                        tracker: "{}", trackerName: `zora-seed-${result.seed}-tracker.json` });
(async () => {
  await onGenerateBatch({ seeds: batchSeeds("123", 5) });
  const zip = blobs.length ? Buffer.from(await blobs[0].arrayBuffer()).toString("base64") : null;
  console.log(JSON.stringify({ asked, zip, failures: nodes["batch-failures"].children.map((li) => li.textContent),
                               summary: nodes["batch-summary"].children.map((node) => node.textContent),
                               link: nodes["batch-download"].children?.[0]?.download ?? null,
                               statuses, stopHidden: nodes["batch-stop"].hidden }));
})();
"""
BATCH_FUNCTIONS = [*ZIP_FUNCTIONS, "batchSeeds", "batchOutput", "canSaveToFolder", "runBatch", "seedFiles",
                   "romFileName", "generationErrorText", "showBatchProgress", "timeLeftText", "onGenerateBatch",
                   "showBatchResult",
                   "onStopBatch"]


def run_batch(stop_at: str) -> dict[str, Any]:
    result: dict[str, Any] = run(BATCH_FUNCTIONS, BATCH_HARNESS.replace("STOP_AT", json.dumps(stop_at)))
    return result


def zipped(answer: dict[str, Any]) -> dict[str, bytes]:
    with zipfile.ZipFile(io.BytesIO(base64.b64decode(answer["zip"]))) as archive:
        assert archive.testzip() is None
        return {name: archive.read(name) for name in archive.namelist()}


def test_each_seed_is_asked_for_as_generate_asks_for_a_typed_seed() -> None:
    """Every seed in order, with the batch's flags and Generate's time limit; one that fails is listed and
    the rest are made; the zip holds each made seed's files by their single-download names."""
    answer = run_batch(stop_at="none")
    assert answer["asked"] == [[str(seed), "FLAGS", "ZORA", 30000] for seed in range(123, 128)]
    assert answer["failures"] == ["Seed 125: Generation failed: generation failed after 3 attempts"]
    assert zipped(answer) == {"zora-seed-123.nes": b"ROM 123", "zora-seed-124.nes": b"ROM 124",
                              "zora-seed-124-spoiler.txt": b"log 124", "zora-seed-124-tracker.json": b"{}",
                              "zora-seed-126.nes": b"ROM 126", "zora-seed-127.nes": b"ROM 127"}
    assert answer["link"] == "zora-seeds-123-127.zip"
    assert answer["summary"][:4] == ["Seeds", "123 to 127", "Made", "4 of 5"]
    assert answer["statuses"][1] == "Generating seed 2 of 5 (seed 124)… about 6 s left."
    assert answer["statuses"][-1] == "4 of 5 seeds made, 1 failed."
    assert answer["stopHidden"] is True


def test_stop_keeps_the_seeds_already_made() -> None:
    answer = run_batch(stop_at="124")
    assert [seed for seed, *_ in answer["asked"]] == ["123", "124"]
    assert set(zipped(answer)) == {"zora-seed-123.nes", "zora-seed-124.nes", "zora-seed-124-spoiler.txt",
                                   "zora-seed-124-tracker.json"}
    assert answer["link"] == "zora-seeds-123-124.zip"
    assert answer["summary"][:4] == ["Seeds", "123 to 124", "Made", "2 of 5 (stopped)"]


def test_the_count_is_a_page_preference_never_in_a_flag_string_or_link() -> None:
    assert 'const SEED_COUNT_KEY = "zora-seed-count";' in PAGE_SCRIPT
    assert "SEED_COUNT_KEY" not in page_function("linkSearch") + page_function("pageSettings")
    assert 'id="seed-count"' in PAGE


# --- byte for byte --------------------------------------------------------------------------------

class JsBytes:
    """What the worker hands the glue: a Pyodide proxy of a Uint8Array."""

    def __init__(self, data: bytes) -> None:
        self.data = data

    def to_py(self) -> memoryview:
        return memoryview(self.data)


ALONE = """
import sys
from zora.rom.base_rom import BASE_ROM_PATH
from zora_web.api import generate_rom, player_settings_from_page
seed, flags = int(sys.argv[1]), sys.argv[2]
sys.stdout.buffer.write(generate_rom(flags, seed, BASE_ROM_PATH.read_bytes(), player_settings_from_page({}), "").rom)
"""


@pytest.mark.skipif(not BASE_ROM_PATH.exists(), reason="needs the base ROM")
def test_a_batchs_roms_are_each_seed_made_alone() -> None:
    """Seeds 4100-4102 made one after another by the worker's glue, as a batch makes them, are byte for
    byte each seed generated alone in a fresh Python."""
    match = re.search(r"const GLUE = `\n(.*?)`;", WORKER, re.DOTALL)
    assert match
    glue: dict[str, Any] = {}
    exec(match.group(1), glue)
    base = BASE_ROM_PATH.read_bytes()
    for seed in (4100, 4101, 4102):
        in_batch = bytes(glue["generate"](JsBytes(base), str(seed), FLAGS, "{}", "", limit=30.0))
        alone = subprocess.run([sys.executable, "-c", ALONE, str(seed), FLAGS], capture_output=True, check=True,
                               cwd=REPO).stdout
        assert in_batch == alone, seed
