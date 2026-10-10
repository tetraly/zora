"""zora/ works copied in alone under another name, the way Archipelago ships it (as
worlds.zora.zora, possibly imported from a zip): no sibling package, no top-level `zora`, no
repo-root ROM. One seed, level encoding off, with the ROM passed in, must give the same sha1
as a normal run, from the copied folder and again from a zip of it. From the zip, Archipelago's
interface (zora/archipelago.py) also rebuilds a recipe it made (Archipelago Phase 4a test 7).

The copy runs in a fresh interpreter started with -I -S: no site-packages (so no installed or
editable zora), no current directory or script folder on the path, and its working directory
outside the repo.
"""
import hashlib
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from zora.generate.pipeline import generate_rom
from zora.rom.base_rom import BASE_ROM_PATH, remember_repo_base_rom

REPO = Path(__file__).resolve().parent.parent
FLAGS = "8hq4BeR1JXo89BJ2!TFpTP02u8UJ3A"     # level encoding off
SEED = 12345
# Archipelago's layout: worlds/zora/ is the world, zora/ inside it the copied package.
COPY_PACKAGE = "worlds.zora.zora"
GENERATE = f"""
import hashlib, importlib, importlib.util, sys
sys.path.insert(0, sys.argv[1])
assert importlib.util.find_spec("zora") is None, "a top-level zora is importable"
for sibling in ("zora_export", "zora_measure", "zora_web"):
    assert importlib.util.find_spec(sibling) is None, sibling
pipeline = importlib.import_module("{COPY_PACKAGE}.generate.pipeline")
base_rom = importlib.import_module("{COPY_PACKAGE}.rom.base_rom")
assert not base_rom.BASE_ROM_PATH.exists(), base_rom.BASE_ROM_PATH
result = pipeline.generate_rom({FLAGS!r}, {SEED}, sys.stdin.buffer.read())
assert not result.encode_level_data
print(pipeline.__file__)
print(hashlib.sha1(result.rom).hexdigest())
"""


@pytest.fixture(scope="module")
def base() -> bytes:
    if not BASE_ROM_PATH.exists():
        pytest.skip("vanilla ROM missing")
    return remember_repo_base_rom()


@pytest.fixture(scope="module")
def copied(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """zora/ alone, copied in as worlds/zora/zora/ under a fresh folder outside the repo."""
    root = tmp_path_factory.mktemp("apworld")
    world = root / "worlds" / "zora"
    world.mkdir(parents=True)
    (root / "worlds" / "__init__.py").write_text("")
    (world / "__init__.py").write_text("")
    shutil.copytree(REPO / "zora", world / "zora", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    return root


def _generate(path_entry: Path, base: bytes, cwd: Path) -> list[str]:
    result = subprocess.run([sys.executable, "-I", "-S", "-c", GENERATE, str(path_entry)], input=base,
                            capture_output=True, cwd=cwd, check=False)
    assert result.returncode == 0, result.stderr.decode()
    return result.stdout.decode().split()


def test_the_copied_package_makes_the_same_rom(base: bytes, copied: Path) -> None:
    expected = hashlib.sha1(generate_rom(FLAGS, SEED, base).rom).hexdigest()
    module, sha1 = _generate(copied, base, copied)
    assert Path(module).is_relative_to(copied)
    assert sha1 == expected


def test_the_zipped_copy_makes_the_same_rom(base: bytes, copied: Path, tmp_path: Path) -> None:
    expected = hashlib.sha1(generate_rom(FLAGS, SEED, base).rom).hexdigest()
    archive = tmp_path / "zora.apworld"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
        for path in sorted((copied / "worlds").rglob("*")):
            if path.is_file():
                bundle.write(path, path.relative_to(copied).as_posix())
    module, sha1 = _generate(archive, base, tmp_path)
    assert module.startswith(str(archive))
    assert sha1 == expected


# Archipelago Phase 4a test 7: the interface module works from the renamed, zipped copy, and a
# recipe made there rebuilds there the ROM made at generation (the repo's own finish() too).
RECIPE_ROUND_TRIP = f"""
import hashlib, importlib, json, sys
sys.path.insert(0, sys.argv[1])
archipelago = importlib.import_module("{COPY_PACKAGE}.archipelago")
base = sys.stdin.buffer.read()
result = archipelago.build_from_strings({FLAGS!r}, "", {SEED}, base)
assignment = dict(zip((place.name for place in result.places), result.pool))
received = [assignment.pop(result.places[0].name)]
assignment[result.places[0].name] = archipelago.FOREIGN
rom = archipelago.finish(result, assignment, received)
recipe = json.loads(json.dumps(archipelago.recipe(result, assignment, received)))
assert archipelago.rom_from_recipe(recipe, base) == rom
print(archipelago.__file__)
print(hashlib.sha1(rom).hexdigest())
"""


def test_the_zipped_copy_rebuilds_a_recipe(base: bytes, copied: Path, tmp_path: Path) -> None:
    from zora import archipelago
    result = archipelago.build_from_strings(FLAGS, "", SEED, base)
    assignment: dict[str, str | archipelago.Foreign] = dict(zip((place.name for place in result.places),
                                                                result.pool, strict=True))
    received = [str(assignment.pop(result.places[0].name))]
    assignment[result.places[0].name] = archipelago.FOREIGN
    expected = hashlib.sha1(archipelago.finish(result, assignment, received)).hexdigest()
    archive = tmp_path / "zora.apworld"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
        for path in sorted((copied / "worlds").rglob("*")):
            if path.is_file():
                bundle.write(path, path.relative_to(copied).as_posix())
    run = subprocess.run([sys.executable, "-I", "-S", "-c", RECIPE_ROUND_TRIP, str(archive)], input=base,
                         capture_output=True, cwd=tmp_path, check=False)
    assert run.returncode == 0, run.stderr.decode()
    module, sha1 = run.stdout.decode().split()
    assert module.startswith(str(archive))
    assert sha1 == expected
