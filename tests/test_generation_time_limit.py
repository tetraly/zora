"""How long a seed may take (2026-10-28): the web page's 30 s limit (15 s until 2026-11-02), which stops
generation between attempts without changing what a finished seed is (zora/generate/deadline.py; the page's
onGenerate in web/zora-web.js, run here in Node). (Gatekeeper Bosses' restart cap and
fallback were tested here until its retirement, 2026-10-29.)"""
import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from tests.needs import needs_base_rom
from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
from zora.generate.deadline import GenerationStopped, stop_after
from zora.generate.pipeline import generate_rom
from zora.rom.base_rom import remember_repo_base_rom

REPO = Path(__file__).resolve().parent.parent
PAGE_SCRIPT = (REPO / "web" / "zora-web.js").read_text()
PAGE_CONSTANTS = ("GENERATION_LIMIT_MS", "STOPPED", "GENERATION_FAILED", "MUSIC_PROBLEM",
                  "NOT_PRODUCED_REFUSAL", "NOT_IMPLEMENTED", "BACKGROUND_TAB_NOTE")


# --- generation's side --------------------------------------------------------------------------

# Both tests take the monkeypatch fixture only to keep their builds out of the session's shared builds
# (tests/shared_builds.py): a world another test stored would be loaded without generating, so no
# deadline would ever be checked (the stop test failed whenever an earlier test in its process had
# built the same seed).

@needs_base_rom
def test_a_passed_limit_stops_generation(monkeypatch: pytest.MonkeyPatch) -> None:
    with stop_after(-1), pytest.raises(GenerationStopped):          # already passed: no clock race
        generate_rom(MVP_BASELINE_LEVEL_ENCODING_OFF, 1, remember_repo_base_rom())


@needs_base_rom
def test_a_seed_finished_in_time_is_the_same_rom(monkeypatch: pytest.MonkeyPatch) -> None:
    base = remember_repo_base_rom()
    with stop_after(600):
        limited = generate_rom(MVP_BASELINE_LEVEL_ENCODING_OFF, 1, base).rom
    assert limited == generate_rom(MVP_BASELINE_LEVEL_ENCODING_OFF, 1, base).rom


# --- the page's side ------------------------------------------------------------------------------

def page_function(name: str) -> str:
    match = re.search(rf"^(?:async )?function {name}\(.*?^}}\n", PAGE_SCRIPT, re.MULTILINE | re.DOTALL)
    assert match, name
    return match.group(0)


# onGenerate on a stubbed page. A seed in OUTCOMES fails as it says; any other runs out its limit.
PAGE_STUBS = """
const element = (tag, props = {}) => ({ tag, ...props });
const stub = () => new Proxy({}, { get: (target, key) => key in target ? target[key] : () => {},
                                   set: (target, key, value) => { target[key] = value; return true; } });
const nodes = {};
const $ = (id) => (nodes[id] ||= stub());
const tried = [], statuses = [];
const status = (text) => statuses.push(text);
const showAfterSeed = () => {}, markStepDone = () => {}, updateButton = () => {}, labelIn = () => "None";
const crypto = { getRandomValues: () => [CHOSEN] };
const metadata = { encodeLevelData: "B82", spoilerLevelField: "B51" };
const form = { flags: "F", zora: { flags: "" }, fields: { B82: { value: 0 }, B51: { value: 0 } } };
const controls = new Map([["B51", { field: { values: [] } }]]);
const playerSettings = {}, TOGGLE_ON = 1;
let linkSeed = null;
let tabWentBehind = true;           // left over from an earlier run: onGenerate starts afresh
const document = { hidden: HIDDEN_AT_START };
async function generateSeed(seed, flags, zoraFlags, limitMs) {
  tried.push([seed, limitMs]);
  if (GOES_BEHIND) { document.hidden = true; noteTabHidden(); document.hidden = false; }
  if ((OUTCOMES)[seed] === "fail") throw new Error("RuntimeError: generation failed after 2000 attempts");
  throw new Error("zora.generate.deadline.GenerationStopped: stopped");
}
"""


def run_page(chosen_by_page: bool, outcomes: dict[str, str], *, hidden_at_start: bool = False,
             goes_behind: bool = False) -> Any:
    """Generate on seed 7, chosen by the page (the real randomSeed) or typed: what was tried, the box after it,
    and the last status."""
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is not installed")
    constants = [line for line in PAGE_SCRIPT.splitlines() if re.match(rf"const ({'|'.join(PAGE_CONSTANTS)}) = ", line)]
    assert len(constants) == len(PAGE_CONSTANTS)
    stubs = (PAGE_STUBS.replace("CHOSEN", "7").replace("OUTCOMES", json.dumps(outcomes))
             .replace("HIDDEN_AT_START", json.dumps(hidden_at_start)).replace("GOES_BEHIND", json.dumps(goes_behind)))
    script = f"""
{'randomSeed();' if chosen_by_page else '$("seed").value = "7";'}
onGenerate().then(() => console.log(JSON.stringify({{ tried, box: $("seed").value, last: statuses.at(-1) }})));
"""
    functions = [page_function(name) for name in ("randomSeed", "onGenerate", "seedProblem", "noteTabHidden",
                                                       "generationErrorText")]
    source = "\n".join([*constants, stubs, *functions, script])
    return json.loads(subprocess.run([node, "-e", source], capture_output=True, text=True, check=True).stdout)


STOPPED_TEXT = ("Seed 7 took longer than 30 seconds to generate, so it was stopped. "
                "Press Generate to try it again, or New seed for a different seed.")
STOPPED_BEHIND_TEXT = ("Seed 7 took longer than 30 seconds to generate, so it was stopped. "
                       "This tab was in the background, which can slow generation down, so keep it in front. "
                       "Press Generate to try it again, or New seed for a different seed.")
CANNOT_BE_MADE_TEXT = ("Seed 7 could not be made with these settings. "
                       "Press New seed for a different seed, or change the settings.")


def test_a_slow_seed_chosen_by_the_page_keeps_its_number() -> None:
    """The page's own number gets the whole limit, once, and is still in the box afterwards."""
    outcome = run_page(chosen_by_page=True, outcomes={})
    assert outcome["tried"] == [["7", 30000]]
    assert outcome["box"] == "7" and outcome["last"] == STOPPED_TEXT


def test_a_typed_seed_gets_the_whole_limit_then_a_message() -> None:
    outcome = run_page(chosen_by_page=False, outcomes={})
    assert outcome["tried"] == [["7", 30000]]
    assert outcome["box"] == "7" and outcome["last"] == STOPPED_TEXT


@pytest.mark.parametrize("chosen_by_page", [True, False])
def test_a_seed_that_cannot_be_made_says_so_plainly(chosen_by_page: bool) -> None:
    outcome = run_page(chosen_by_page, outcomes={"7": "fail"})
    assert outcome["tried"] == [["7", 30000]] and outcome["box"] == "7"
    assert outcome["last"] == CANNOT_BE_MADE_TEXT


@pytest.mark.parametrize("behind", [{"goes_behind": True}, {"hidden_at_start": True}])
def test_a_timeout_after_the_tab_went_behind_says_so(behind: dict[str, bool]) -> None:
    assert run_page(chosen_by_page=True, outcomes={}, **behind)["last"] == STOPPED_BEHIND_TEXT


def test_a_timeout_with_the_tab_in_front_says_nothing_of_it() -> None:
    """Also when the tab was behind in an earlier run (the harness starts with the note set)."""
    assert run_page(chosen_by_page=True, outcomes={})["last"] == STOPPED_TEXT


def test_the_background_note_is_only_for_a_timeout() -> None:
    assert run_page(chosen_by_page=True, outcomes={"7": "fail"}, goes_behind=True)["last"] == CANNOT_BE_MADE_TEXT


def test_the_page_listens_for_the_tab_going_behind() -> None:
    assert 'document.addEventListener("visibilitychange", noteTabHidden);' in PAGE_SCRIPT


def test_only_new_seed_page_load_and_a_link_write_the_seed_box() -> None:
    """Nothing in Generate can change the number: the box is written by randomSeed and a shared link alone,
    and randomSeed runs only from New seed and at page load."""
    assert len(re.findall(r'\$\("seed"\)\.value = ', PAGE_SCRIPT)) == 2
    callers = [line for line in PAGE_SCRIPT.splitlines()
               if "randomSeed()" in line and "function randomSeed" not in line]
    assert callers == ['$("new-seed").addEventListener("click", () => { randomSeed(); onSeedChanged(); });',
                       "randomSeed();"]
