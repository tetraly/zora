"""Archipelago's recipe (zora/archipelago.py recipe, rom_from_recipe and source_hash;
docs/archipelago.md "Interface"), Archipelago Phase 4a tests 4 and 5:
  4. for seeds across tests/archipelago_cases.py, with shuffled assignments that FINISH accepts
     (some places holding another player's item, their own items received) and player settings,
     the ROM rebuilt from the recipe after a JSON round trip equals finish()'s byte for byte: in
     this process, in a fresh one, and under Python 3.11 and 3.13;
  5. the pin: one changed byte in a copied zora/ changes the source hash, and that copy refuses
     the recipe naming both; the hash is the same from the repo, a copied folder and a zip."""
import hashlib
import json
import random
import shutil
import subprocess
import sys
import zipfile
from functools import cache
from pathlib import Path
from typing import Any

import pytest

from tests.archipelago_cases import FLAG_CASES
from tests.shared_builds import prebuild
from tests.test_assignment import identity, permuted
from zora import archipelago
from zora.generate.finish import AssignmentUnbeatable, Foreign
from zora.model.item_names import ITEM_NAMES
from zora.rom.base_rom import BASE_ROM_PATH, remember_repo_base_rom
from zora.version import ZORA_VERSION

REPO = Path(__file__).resolve().parent.parent
SEEDS = (1, 2, 3)
MANY_SEEDS = range(4, 16)
SHUFFLE_TRIES = 20
FOREIGN_SHARE = 0.25
PYTHONS = {"3.11": Path.home() / ".pyenv/versions/3.11.16/bin/python",
           "3.13": Path.home() / ".pyenv/versions/3.13.3/bin/python"}
SETTINGS: tuple[dict[str, Any], ...] = ({}, {"selectButton": "swap", "music": "off", "greenTunic": 0x2A, "heart": 0x27})
REBUILD = """
import hashlib, json, sys
sys.path.insert(0, sys.argv[1])
from zora import archipelago
with open(sys.argv[2], "rb") as rom, open(sys.argv[3]) as recipe:
    print(hashlib.sha1(archipelago.rom_from_recipe(json.load(recipe), rom.read())).hexdigest())
"""


@pytest.fixture(scope="module")
def base() -> bytes:
    if not BASE_ROM_PATH.exists():
        pytest.skip("vanilla ROM missing")
    return remember_repo_base_rom()


@cache
def built(case: str, seed: int) -> archipelago.BuildResult:
    return archipelago.build_from_strings(*FLAG_CASES[case], seed, remember_repo_base_rom())


def named(assignment: dict[str, object]) -> dict[str, str | Foreign]:
    return {place: item if isinstance(item, Foreign) else ITEM_NAMES[item]  # type: ignore[index]
            for place, item in assignment.items()}


def accepted_assignment(result: archipelago.BuildResult, seed: int) -> tuple[dict[str, str | Foreign], list[str]]:
    """A shuffled assignment FINISH accepts, a share of its places holding another player's item
    and their own items received; ZORA's own placement (with the same foreign places) if no
    shuffle passes."""
    rng = random.Random(f"recipe {seed}")
    candidates = [permuted(result.state, seed * 100 + attempt) for attempt in range(SHUFFLE_TRIES)]
    for items in (*candidates, identity(result.state)):
        assignment = named(items)  # type: ignore[arg-type]
        received: list[str] = []
        for place in rng.sample(sorted(assignment), int(len(assignment) * FOREIGN_SHARE)):
            item = assignment[place]
            assert isinstance(item, str)
            received.append(item)
            assignment[place] = archipelago.FOREIGN
        try:
            archipelago.finish(result, assignment, received)
        except AssignmentUnbeatable:
            continue
        return assignment, received
    raise AssertionError("no assignment passes")


def round_tripped(case: str, seed: int) -> tuple[dict[str, Any], bytes]:
    result = built(case, seed)
    assignment, received = accepted_assignment(result, seed)
    settings = SETTINGS[seed % len(SETTINGS)]
    rom = archipelago.finish(result, assignment, received, settings)
    data = json.loads(json.dumps(archipelago.recipe(result, assignment, received, settings)))
    return data, rom


@pytest.mark.parametrize("seed", SEEDS)
@pytest.mark.parametrize("case", list(FLAG_CASES))
def test_the_recipe_rebuilds_the_rom(base: bytes, case: str, seed: int) -> None:
    data, rom = round_tripped(case, seed)
    assert data["producer"] == {"name": "ZORA", "version": ZORA_VERSION,
                                "sourceHash": archipelago.source_hash()}
    assert data["seed"]["number"] == str(seed)
    assert any(value == {"foreign": True} for value in data["assignment"].values())
    assert archipelago.rom_from_recipe(data, base) == rom


@pytest.mark.slow
@pytest.mark.parametrize("case", list(FLAG_CASES))
def test_the_recipe_rebuilds_the_rom_many_seeds(base: bytes, case: str) -> None:
    prebuild([FLAG_CASES[case]], MANY_SEEDS)
    for seed in MANY_SEEDS:
        data, rom = round_tripped(case, seed)
        assert archipelago.rom_from_recipe(data, base) == rom, seed


@pytest.mark.parametrize("python", list(PYTHONS))
@pytest.mark.parametrize("case", list(FLAG_CASES))
def test_a_fresh_process_rebuilds_the_rom(base: bytes, case: str, python: str, tmp_path: Path) -> None:
    if not PYTHONS[python].exists():
        pytest.skip(f"Python {python} missing")
    data, rom = round_tripped(case, 2)
    (tmp_path / "recipe.json").write_text(json.dumps(data))
    run = subprocess.run([str(PYTHONS[python]), "-c", REBUILD, str(REPO), str(BASE_ROM_PATH),
                          str(tmp_path / "recipe.json")], capture_output=True, text=True, cwd=tmp_path, check=False)
    assert run.returncode == 0, run.stderr
    assert run.stdout.strip() == hashlib.sha1(rom).hexdigest()


def test_a_recipe_from_another_version_is_refused(base: bytes) -> None:
    data, _rom = round_tripped("baseline", 1)
    data["producer"]["version"] = "0.0.0"
    with pytest.raises(archipelago.RecipeRefused, match=r"ZORA 0\.0\.0.*this is ZORA"):
        archipelago.rom_from_recipe(data, base)


# --- test 5: the pin -------------------------------------------------------------------------------

HASH_AND_REBUILD = """
import importlib, json, sys
sys.path.insert(0, sys.argv[1])
archipelago = importlib.import_module("worlds.zora.zora.archipelago")
print(archipelago.source_hash())
if len(sys.argv) > 2:
    try:
        archipelago.rom_from_recipe(json.load(open(sys.argv[3])), open(sys.argv[2], "rb").read())
    except archipelago.RecipeRefused as refused:
        print("REFUSED", refused)
"""


def copy_package(root: Path) -> Path:
    """zora/ alone as worlds/zora/zora/, as Archipelago ships it (tests/test_package_copy.py)."""
    world = root / "worlds" / "zora"
    world.mkdir(parents=True)
    (root / "worlds" / "__init__.py").write_text("")
    (world / "__init__.py").write_text("")
    shutil.copytree(REPO / "zora", world / "zora", ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".*"))
    return world / "zora"


def run_copy(path_entry: Path, *args: str) -> list[str]:
    run = subprocess.run([sys.executable, "-I", "-S", "-c", HASH_AND_REBUILD, str(path_entry), *args],
                         capture_output=True, text=True, cwd=path_entry.parent, check=False)
    assert run.returncode == 0, run.stderr
    return run.stdout.splitlines()


def test_the_hash_is_the_same_from_a_folder_and_a_zip(tmp_path: Path) -> None:
    folder = tmp_path / "folder"
    copy_package(folder)
    archive = tmp_path / "zora.apworld"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
        for path in sorted((folder / "worlds").rglob("*")):
            if path.is_file():
                bundle.write(path, path.relative_to(folder).as_posix())
    assert run_copy(folder) == run_copy(archive) == [archipelago.source_hash()]


def test_one_changed_byte_changes_the_hash_and_refuses_the_recipe(base: bytes, tmp_path: Path) -> None:
    package = copy_package(tmp_path / "copy")
    changed = package / "generate" / "logic.py"
    source = bytearray(changed.read_bytes())
    source[-1] ^= ord("\n") ^ ord(" ")             # the last newline becomes a space: same behaviour
    changed.write_bytes(bytes(source))
    data, _rom = round_tripped("baseline", 1)
    (tmp_path / "recipe.json").write_text(json.dumps(data))
    copy_hash, refusal = run_copy(tmp_path / "copy", str(BASE_ROM_PATH), str(tmp_path / "recipe.json"))
    assert copy_hash != archipelago.source_hash()
    assert refusal.startswith("REFUSED") and archipelago.source_hash() in refusal and copy_hash in refusal
