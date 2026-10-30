"""How long a seed may take (2026-10-28): the web page's 15 s limit, which stops generation between
attempts without changing what a finished seed is (zora/generate/deadline.py; the page's
generateWithinLimit in web/zora-web.js, run here in Node). (Gatekeeper Bosses' restart cap and
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
PAGE_CONSTANTS = ("GENERATION_LIMIT_MS", "CHOSEN_SEED_MS", "RETRY_MIN_MS", "STOPPED", "GENERATION_FAILED")


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


# A clock that moves only when a seed runs: each seed takes OUTCOMES[seed][1] ms, or stops at its limit.
PAGE_STUBS = """
let clock = 0;
const performance = { now: () => clock };
const nodes = { seed: { value: SEED } };
const $ = (id) => nodes[id];
let seedTyped = TYPED;
let nextSeed = 100;
const tried = [];
const form = { flags: "F", zora: { flags: "" } };
function status() {}
function randomSeed() { nodes.seed.value = String(nextSeed++); seedTyped = false; }
async function generateSeed(seed, flags, zoraFlags, limitMs) {
  tried.push([seed, limitMs]);
  const [kind, ms] = OUTCOMES[seed] || ["slow", Infinity];
  if (kind === "slow" && ms > limitMs) {
    clock += limitMs;
    throw new Error("zora.generate.deadline.GenerationStopped: stopped");
  }
  clock += ms;
  if (kind === "fail") throw new Error("RuntimeError: generation failed after 2000 attempts, none accepted");
  return { seed };
}
"""


def run_page(seed: str, typed: bool, outcomes: dict[str, list[Any]]) -> Any:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is not installed")
    constants = [line for line in PAGE_SCRIPT.splitlines() if re.match(rf"const ({'|'.join(PAGE_CONSTANTS)}) = ", line)]
    assert len(constants) == len(PAGE_CONSTANTS)
    stubs = (PAGE_STUBS.replace("SEED", json.dumps(seed)).replace("TYPED", json.dumps(typed))
             .replace("OUTCOMES", json.dumps(outcomes)))
    script = """
generateWithinLimit().then((result) => console.log(JSON.stringify({ result, tried, clock })),
                           (err) => console.log(JSON.stringify({ error: err.message, tried, clock })));
"""
    source = "\n".join([*constants, stubs, page_function("generateWithinLimit"), script])
    return json.loads(subprocess.run([node, "-e", source], capture_output=True, text=True, check=True).stdout)


def test_a_typed_seed_gets_the_whole_limit_then_a_message() -> None:
    outcome = run_page("7", typed=True, outcomes={})
    assert outcome["tried"] == [["7", 15000]]
    assert outcome["error"] == "Seed 7 took longer than 15 s to generate. Try another seed."


def test_a_typed_seed_that_fails_reports_its_own_error() -> None:
    outcome = run_page("7", typed=True, outcomes={"7": ["fail", 300]})
    assert outcome["tried"] == [["7", 15000]] and "generation failed" in outcome["error"]


def test_a_chosen_seed_is_replaced_quietly_until_one_finishes() -> None:
    outcome = run_page("1", typed=False, outcomes={"100": ["fail", 2000], "101": ["ok", 1500]})
    assert outcome["tried"] == [["1", 5000], ["100", 5000], ["101", 5000]]
    assert outcome["result"] == {"seed": "101"} and outcome["clock"] == 8500


def test_chosen_seeds_stop_within_the_limit() -> None:
    outcome = run_page("1", typed=False, outcomes={})
    assert [limit for _seed, limit in outcome["tried"]] == [5000, 5000, 5000]
    assert outcome["clock"] == 15000
    assert outcome["error"].startswith("No seed was ready within 15 s with these settings.")
