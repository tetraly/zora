"""The page's seed link (web/zora-web.js; owner request, beta 5): a valid seed= in a single-player
link fills the seed field at load (an invalid one is ignored quietly and the seed stays random);
after Generate the address names the seed that was used, beside both flag strings, so copying it
shares that exact game; before any generation (and once the seed is changed) it names none;
multiworld mode ignores the seed. Run in Node on the page's own functions."""
import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from zora.generate.pipeline import SEED_LIMIT

REPO = Path(__file__).resolve().parent.parent
PAGE_SCRIPT = (REPO / "web" / "zora-web.js").read_text()
CONSTANTS = ("SINGLE", "MULTIWORLD", "LINK_FLAGS", "LINK_ZORA_FLAGS", "LINK_MODE", "LINK_SEED", "SEED_LIMIT")


def page_function(name: str) -> str:
    match = re.search(rf"^(?:async )?function {name}\(.*?^}}\n", PAGE_SCRIPT, re.MULTILINE | re.DOTALL)
    assert match, name
    return match.group(0)


def run(functions: list[str], script: str) -> Any:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is not installed")
    constants = [line for line in PAGE_SCRIPT.splitlines()
                 if re.match(rf"const ({'|'.join(CONSTANTS)}) = ", line)]
    assert len(constants) == len(CONSTANTS)
    source = "\n".join([*constants, *map(page_function, functions), script])
    return json.loads(subprocess.run([node, "-e", source], capture_output=True, text=True, check=True).stdout)


def test_the_pages_seed_limit_is_zoras() -> None:
    assert "const SEED_LIMIT = 2n ** 64n;" in PAGE_SCRIPT
    assert SEED_LIMIT == 2 ** 64


SEEDS = {"12345": "12345", "0": "0", "007": "7", str(SEED_LIMIT - 1): str(SEED_LIMIT - 1),
         str(SEED_LIMIT): None, "abc": None, "-1": None, "1e5": None, " 12": None, "12 ": None, "": None,
         "1" * 21: None, "4.5": None}


def test_a_link_names_a_valid_seed_or_none() -> None:
    """Only a whole number ZORA takes, leading zeros dropped; multiworld ignores any seed."""
    answers = run(["validSeed", "linkSettings"],
                  f"const seeds = {json.dumps(list(SEEDS))};\n"
                  "console.log(JSON.stringify({\n"
                  "  single: seeds.map((s) => linkSettings('?' + new URLSearchParams({seed: s})).seed),\n"
                  "  multiworld: linkSettings('?mode=multiworld&seed=12345'),\n"
                  "  absent: linkSettings('?flags=X').seed,\n"
                  "}));")
    assert dict(zip(SEEDS, answers["single"], strict=True)) == SEEDS
    assert answers["multiworld"] == {"flags": None, "zoraFlags": None, "mode": "multiworld", "seed": None}
    assert answers["absent"] is None


def test_the_address_names_the_seed_in_single_player_only() -> None:
    answers = run(["validSeed", "linkSettings", "linkSearch"],
                  "const d = 'DEFAULT';\n"
                  "console.log(JSON.stringify({\n"
                  "  seeded: linkSearch('?pyodide=0.28.3', {flags: 'F', zoraFlags: 'Z', mode: SINGLE, seed: '12345'}, d),\n"
                  "  none: linkSearch('?seed=99', {flags: 'F', zoraFlags: '', mode: SINGLE, seed: null}, d),\n"
                  "  multiworld: linkSearch('?seed=99', {flags: 'F', zoraFlags: '', mode: MULTIWORLD, seed: '12345'}, d),\n"
                  "  trip: linkSettings(linkSearch('', {flags: 'F', zoraFlags: 'Z', mode: SINGLE, seed: '42'}, d)),\n"
                  "}));")
    assert answers["seeded"] == "?pyodide=0.28.3&flags=F&zora=Z&seed=12345"
    assert answers["none"] == "?flags=F&mode=single"
    assert answers["multiworld"] == "?flags=F&mode=multiworld"
    assert answers["trip"] == {"flags": "F", "zoraFlags": "Z", "mode": "single", "seed": "42"}


def test_the_page_starts_from_the_links_seed() -> None:
    """The address's seed starts as the link's (null in multiworld or when invalid), and the seed
    field takes it after the random one is drawn, so an invalid link keeps the random seed."""
    assert "let linkSeed = sharedLink.seed;" in PAGE_SCRIPT
    assert "randomSeed();\nif (linkSeed) $(\"seed\").value = linkSeed;" in PAGE_SCRIPT


# onGenerate and the seed field's handler on a stubbed page: elements that take anything, a worker
# that generates seed 12345, and history.replaceState recording each address.
GENERATE_HARNESS = """
const element = (tag, props = {}) => ({ tag, ...props });
const stub = () => new Proxy({ classList: { toggle() {} } }, { get: (target, key) =>
  key in target ? target[key] : (key === "hasChildNodes" ? () => false : () => {}), set: (target, key, value) => {
    target[key] = value; return true; } });
const nodes = {};
const $ = (id) => (nodes[id] ||= stub());
const addresses = [];
const location = { pathname: "/", search: "", hash: "" };
const history = { state: null, replaceState(state, title, url) { addresses.push(url); location.search = url.includes("?") ? url.slice(url.indexOf("?")) : ""; } };
const URL = { createObjectURL: () => "blob:rom" };
const status = () => {}, showAfterSeed = () => {}, markStepDone = () => {}, addSeedReportButtons = () => {};
const updateButton = () => {};
const NOT_PRODUCED_REFUSAL = "not produced", NOT_IMPLEMENTED = "Not implemented";
const generateSeed = async (seed) => ({ bytes: new Uint8Array(1), seed, code: [], ms: 1 });
const metadata = { defaultFlags: "DEFAULT", encodeLevelData: "B82" };
const form = { flags: "8hq4BeR1JXo7yjOOHjbxryVQW!UJ3A", zora: { ok: true, flags: "4.T9Jvg" },
               fields: { B82: { value: 0 } } };
let mode = SINGLE, linkSeed = null;
const TOGGLE_ON = 1, SEED_CODE_LENGTH = 4;
(async () => {
  updateLink();
  const before = location.search;
  $("seed").value = "12345";
  await onGenerate();
  const after = location.search;
  $("seed").value = "777";
  onSeedChanged();
  console.log(JSON.stringify({ before, after, changed: location.search }));
})();
"""


def test_after_generate_the_address_names_the_seed_used() -> None:
    answers = run(["validSeed", "linkSettings", "linkSearch", "updateLink", "onSeedChanged", "onGenerate"],
                  GENERATE_HARNESS)
    flags = "flags=8hq4BeR1JXo7yjOOHjbxryVQW%21UJ3A&zora=4.T9Jvg"
    assert answers["before"] == f"?{flags}&mode=single"           # no seed before any generation
    assert answers["after"] == f"?{flags}&seed=12345"
    assert answers["changed"] == f"?{flags}&mode=single"          # a changed seed: none until generated


# Flag strings ending in "!" (the flag alphabet has it), with and without a ZORA string, a seed,
# another parameter first, in both modes.
ENDINGS = [{"flags": flags, "zoraFlags": zora, "mode": mode, "seed": seed}
           for flags in ("DEFAULT", "8hq4BeR1JXo7yjOOHjbxryVQW!UJ3!", "!")
           for zora in ("", "4.T9Jv!")
           for mode in ("single", "multiworld")
           for seed in (None, "12345")]


def test_the_written_address_never_ends_in_an_exclamation_mark() -> None:
    """Owner (beta 5): chat apps drop a trailing "!", so the address the page writes never ends in
    one, encoded ("%21") or as a browser shows it decoded: it ends with the seed or the mode once it
    names any setting. Each address reads back the same in any parameter order."""
    answers = run(["validSeed", "linkSettings", "linkSearch"],
                  f"const cases = {json.dumps(ENDINGS)};\n"
                  "const out = [];\n"
                  "for (const c of cases) for (const before of ['', '?pyodide=0.28.3']) {\n"
                  "  const search = linkSearch(before, c, 'DEFAULT');\n"
                  "  const pairs = [...new URLSearchParams(search)];\n"
                  "  const reversed = '?' + new URLSearchParams(pairs.reverse()).toString();\n"
                  "  out.push({ search, shown: decodeURIComponent(search), last: pairs.length ? pairs[0][0] : null,\n"
                  "             read: linkSettings(search), readReversed: linkSettings(reversed) });\n"
                  "}\n"
                  "console.log(JSON.stringify(out));")
    assert len(answers) == 2 * len(ENDINGS)
    for case, answer in zip([case for case in ENDINGS for _ in range(2)], answers, strict=True):
        search, shown = answer["search"], answer["shown"]
        assert not search.endswith(("!", "%21")) and not shown.endswith("!"), search
        names_a_setting = case["flags"] != "DEFAULT" or case["zoraFlags"] or case["mode"] == "multiworld" \
            or (case["seed"] and case["mode"] == "single")
        if names_a_setting:
            assert answer["last"] == ("seed" if case["seed"] and case["mode"] == "single" else "mode"), search
        else:
            assert answer["last"] in (None, "pyodide"), search
        assert answer["read"] == answer["readReversed"]
        assert answer["read"]["mode"] == case["mode"]
        assert answer["read"]["flags"] == (None if case["flags"] == "DEFAULT" else case["flags"])
