"""The Multiworld tab's "Build your ROM from a .apzora" step (zora_web/apzora.py, web/zora-web.js; 2.0.2, owner
decisions 2026-11-21).

- With the recipe's own playerSettings, the step's ROM is the one Archipelago's patch makes from the same .apzora:
  its one procedure step (archipelago/rom.py ZoraPatchExtension.zora_rom_from_recipe) is
  archipelago.rom_from_recipe on the container's recipe.json, so the two are compared byte for byte here, on a
  container built as ZoraProcedurePatch writes one. (scripts/check_apworld.py compares the step with
  Archipelago's real patcher too, on every patch it generates, from PRG0, PRG1 and modified graphics.)
- With other cosmetics, the ROM differs only where the cosmetic writer writes: it is exactly the first ROM with
  write_player_settings run over it with the new settings (every byte that differs is one that writer writes),
  the slot identity and every place's item read the same, and FINISH's sanity check passes (rom_from_recipe
  runs it, and raises RecipeNotReproduced otherwise). The recipe copy differs only in playerSettings.
- A recipe from another ZORA version names that version and links its archived page, and nothing is built; a
  broken or non-ZORA .apzora gets a clear reason."""
import io
import json
import re
import zipfile
from pathlib import Path
from typing import Any

import pytest

from tests.test_assignment import identity
from zora import archipelago
from zora.generate.places import read_item
from zora.model.item_names import ITEM_NAMES
from zora.rom import final_steps
from zora.rom.base_rom import BASE_ROM_PATH, PRG1_ROM_PATH, remember_repo_base_rom
from zora.rom.parse.rom_file import parse_rom
from zora.rom.player_settings import PlayerSettingError, player_settings_from_page, write_player_settings
from zora.rom.slot_identity import SLOT_IDENTITY_ADDRESS, SLOT_IDENTITY_SIZE
from zora.version import ZORA_VERSION
from zora_web import apzora

REPO = Path(__file__).resolve().parent.parent
PAGE = (REPO / "web" / "index.html").read_text()
PAGE_SCRIPT = (REPO / "web" / "zora-web.js").read_text()
WORKER = (REPO / "web" / "zora-worker.js").read_text()
SEED = 5
AP_NAME = b"ZORA2_12345678901234567"
FILE_NAME = "AP_12345678901234567_P2_Tetra.apzora"
# The recipe's own look and feel (as a YAML would give it) and the player's new choices at the step
OWN = {"selectButton": "swap", "greenTunic": 0x1A, "levelWord": "LAIR", "linkSprite": "agumon",
       "itemArrivalSound": "none"}
NEW = {"selectButton": "off", "lowHealthBeep": "kept", "deathWarp": "p1-up-select", "reduceFlashing": "on",
       "cropGuide": "off", "music": "off", "greenTunic": 0x3E, "blueRingTunic": 0x00, "redRingTunic": 0x3F,
       "heart": 0x30, "levelWord": "RANDOM", "bossSoundWord": "MEOW", "linkSprite": "link", "linkColor2": 0x30}
# archipelago.json as ZoraProcedurePatch writes it (archipelago/rom.py; Archipelago's APContainer)
MANIFEST = {"compatible_version": 6, "version": 7, "server": "", "player": 2, "player_name": "Tetra", "game": "ZORA",
            "patch_file_ending": ".apzora", "procedure": [["zora_rom_from_recipe", ["recipe.json"]]],
            "base_checksum": None, "result_file_ending": ".nes"}


@pytest.fixture(scope="module")
def base() -> bytes:
    if not BASE_ROM_PATH.exists():
        pytest.skip("needs the base ROM")
    return remember_repo_base_rom()


def container(recipe: dict[str, Any], manifest: dict[str, Any] | None = None) -> bytes:
    """A .apzora as ZoraProcedurePatch writes it: archipelago.json and recipe.json in a zip."""
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("archipelago.json", json.dumps(manifest or MANIFEST))
        archive.writestr("recipe.json", json.dumps(recipe, sort_keys=True))
    return data.getvalue()


@pytest.fixture(scope="module")
def made(base: bytes) -> tuple[archipelago.BuildResult, dict[str, Any]]:
    """A multiworld player's recipe: an item of another player's at the Coast, one received item."""
    result = archipelago.build_from_strings(*archipelago.flag_strings({}), SEED, base, OWN)
    names = {**ITEM_NAMES, **archipelago.seed_item_names(result.state.world)}     # the per-level names too
    assignment: dict[str, Any] = {place: names[item] for place, item in identity(result.state).items()
                                  if not isinstance(item, archipelago.Foreign)}
    assignment["Coast"] = archipelago.FOREIGN
    return result, archipelago.recipe(result, assignment, ["Heart Container"], OWN, AP_NAME)


def items(rom: bytes, result: archipelago.BuildResult) -> dict[str, Any]:
    world = parse_rom(rom)
    return {place.name: read_item(world, place) for place in result.state.places}


def test_the_recipes_own_look_and_feel_makes_archipelagos_rom(base: bytes, made: tuple[Any, dict[str, Any]]) -> None:
    _result, recipe = made
    data = container(recipe)
    info = apzora.read_apzora(data, FILE_NAME)
    assert info["ok"] and (info["playerName"], info["player"]) == ("Tetra", 2)
    assert info["romFileName"] == "AP_12345678901234567_P2_Tetra.nes"
    shown = {entry["key"]: entry["value"] for entry in info["settings"]}
    assert {key: shown[key] for key in OWN if key != "itemArrivalSound"} == {
        key: value for key, value in OWN.items() if key != "itemArrivalSound"}
    assert "itemArrivalSound" not in shown          # read by the client from the game, not the ROM
    with zipfile.ZipFile(io.BytesIO(data)) as archive:      # what Archipelago's patch step runs
        patched = archipelago.rom_from_recipe(json.loads(archive.read("recipe.json")), base)
    assert apzora.build_rom(data, base) == patched
    assert apzora.build_rom(data, base, shown) == patched   # the prefilled choices, unchanged


def test_on_prg1_too(made: tuple[Any, dict[str, Any]]) -> None:
    if not PRG1_ROM_PATH.exists():
        pytest.skip("needs the PRG1 ROM")
    _result, recipe = made
    prg1 = PRG1_ROM_PATH.read_bytes()
    assert apzora.build_rom(container(recipe), prg1) == archipelago.rom_from_recipe(recipe, prg1)


def built_with_writer_seen(data: bytes, base: bytes, chosen: dict[str, Any] | None,
                           monkeypatch: pytest.MonkeyPatch) -> tuple[bytes, bytes, bytes]:
    """The step's ROM, and the image the cosmetic writer (write_player_settings, run by FINISH's player-settings
    step, the last but B55's) was given and what it made of it."""
    seen: list[tuple[bytes, bytes]] = []

    def watched(rom: bytes, settings: Any, coop: bool = False) -> bytes:
        written = write_player_settings(rom, settings, coop)
        seen.append((rom, written))
        return written

    monkeypatch.setattr(final_steps, "write_player_settings", watched)
    built = apzora.build_rom(data, base, chosen)
    monkeypatch.undo()
    [(before, after)] = seen
    return built, before, after


def test_other_cosmetics_change_only_what_the_cosmetic_writer_writes(base: bytes, made: tuple[Any, dict[str, Any]],
                                                                    monkeypatch: pytest.MonkeyPatch) -> None:
    """How "only where cosmetics write" is shown: both builds hand the cosmetic writer the same image, byte for
    byte (so everything before it, the items, the slot identity, the seed's code, is the same), and each ROM is
    exactly what the writer made of that image (no step after it changes a byte: B55 is off). So every byte that
    differs is one the writer wrote."""
    result, recipe = made
    data = container(recipe)
    own, own_before, own_after = built_with_writer_seen(data, base, None, monkeypatch)
    new, new_before, new_after = built_with_writer_seen(data, base, NEW, monkeypatch)   # FINISH's check passed
    assert own_before == new_before
    assert (own, new) == (own_after, new_after)
    changed = recipe_with = apzora.recipe_with_settings(recipe, NEW)
    assert {key: value for key, value in changed.items() if key != "playerSettings"} == {
        key: value for key, value in recipe.items() if key != "playerSettings"}
    assert recipe_with["playerSettings"]["itemArrivalSound"] == "none"       # kept, not shown
    assert own != new
    assert write_player_settings(own_before, player_settings_from_page(recipe_with["playerSettings"])) == new
    # The slot identity, and every place's item, are the same
    identity_bytes = slice(SLOT_IDENTITY_ADDRESS, SLOT_IDENTITY_ADDRESS + SLOT_IDENTITY_SIZE)
    assert own[identity_bytes] == new[identity_bytes]
    assert archipelago.rom_identity(own) == archipelago.rom_identity(new) is not None
    assert items(own, result) == items(new, result)


def test_a_recipe_from_another_version_is_not_built(base: bytes, made: tuple[Any, dict[str, Any]],
                                                    monkeypatch: pytest.MonkeyPatch) -> None:
    _result, recipe = made
    older = {**recipe, "producer": {**recipe["producer"], "version": "2.0.0"}}
    info = apzora.read_apzora(container(older), FILE_NAME)
    assert info["ok"] is False
    assert info["reason"].startswith(f"This patch was made by ZORA 2.0.0, and this page is ZORA {ZORA_VERSION}")
    assert (info["version"], info["archiveUrl"]) == ("2.0.0", "https://zora.gg/2.0.0/")
    built: list[object] = []
    monkeypatch.setattr(archipelago, "rom_from_recipe", lambda *args: built.append(args))
    with pytest.raises(apzora.ApzoraRefused, match=r"made by ZORA 2\.0\.0"):
        apzora.build_rom(container(older), base)
    assert built == []
    # The same version from another build (source hash): named, no archive to send the player to
    other = {**recipe, "producer": {**recipe["producer"], "sourceHash": "sha256:" + "0" * 64}}
    info = apzora.read_apzora(container(other), FILE_NAME)
    assert info["ok"] is False and "another build of ZORA" in info["reason"] and "archiveUrl" not in info


@pytest.mark.parametrize(("data", "reason"), [
    (b"not a zip at all", "This isn't a ZORA patch (.apzora): it isn't a patch file (not a zip archive)."),
    (b"", "This isn't a ZORA patch (.apzora): it isn't a patch file (not a zip archive)."),
    ("no recipe", "This isn't a ZORA patch (.apzora): it has no recipe.json."),
    ("another game", "This isn't a ZORA patch (.apzora): it is a patch for 'A Link to the Past', not ZORA."),
    ("unreadable", "This isn't a ZORA patch (.apzora): its contents can't be read."),
    ("no version", "This isn't a ZORA patch (.apzora): its recipe names no ZORA version."),
    ("another recipe", "This isn't a ZORA patch (.apzora): its recipe is not ZORA's."),
])
def test_a_broken_or_foreign_patch_gets_a_clear_reason(data: bytes | str, reason: str,
                                                       made: tuple[Any, dict[str, Any]]) -> None:
    _result, recipe = made
    if data == "no recipe":
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("archipelago.json", json.dumps(MANIFEST))
        data = buffer.getvalue()
    elif data == "another game":
        data = container(recipe, {**MANIFEST, "game": "A Link to the Past"})
    elif data == "unreadable":
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("archipelago.json", json.dumps(MANIFEST))
            archive.writestr("recipe.json", b"\xff\xfe not json")
        data = buffer.getvalue()
    elif data == "no version":
        data = container({key: value for key, value in recipe.items() if key != "producer"})
    elif data == "another recipe":
        data = container({**recipe, "format": "something-else"})
    assert isinstance(data, bytes)
    assert apzora.read_apzora(data, FILE_NAME) == {"ok": False, "reason": reason}
    with pytest.raises(apzora.ApzoraRefused):
        apzora.build_rom(data, b"")


def test_a_refused_choice_is_named(base: bytes, made: tuple[Any, dict[str, Any]]) -> None:
    _result, recipe = made
    with pytest.raises(PlayerSettingError, match=r"0x0D|13|0D"):
        apzora.build_rom(container(recipe), base, {"greenTunic": 0x0D})
    with pytest.raises(PlayerSettingError, match="itemArrivalSound"):
        apzora.recipe_with_settings(recipe, {"itemArrivalSound": "none"})


@pytest.mark.parametrize(("name", "rom"), [("AP_1_P2_Tetra.apzora", "AP_1_P2_Tetra.nes"),
                                           ("C:\\Archipelago\\output\\AP_1_P2_Tetra.APZORA", "AP_1_P2_Tetra.nes"),
                                           ("", "ZORA.nes")])
def test_the_rom_is_named_as_archipelago_names_it(name: str, rom: str) -> None:
    assert apzora.rom_file_name(name) == rom


def test_the_page_and_worker_wire_the_step() -> None:
    """Step 4 on the Multiworld tab, the page's own ROM input for the base ROM, the worker's two messages, and
    the archived page's link for another version."""
    assert re.search(r'<section class="step multiworld-only" id="step-apzora"', PAGE)
    assert '<input id="apzora-file" type="file" accept=".apzora" hidden>' in PAGE
    assert '$("apzora-rom-btn").addEventListener("click", () => $("rom").click());' in PAGE_SCRIPT
    builder = re.search(r"^async function onApzoraBuild\(.*?^}\n", PAGE_SCRIPT, re.MULTILINE | re.DOTALL)
    assert builder and "rom: baseRom" in builder.group(0) and "apzora.info.romFileName" in builder.group(0)
    shown = re.search(r"^function showApzoraStep\(.*?^}\n", PAGE_SCRIPT, re.MULTILINE | re.DOTALL)
    assert shown and "info.archiveUrl" in shown.group(0)
    for message in ('"readApzora"', '"buildApzora"'):
        assert f"message.type === {message}" in WORKER
    assert "def read_apzora(data, name):" in WORKER and "def build_apzora(data, rom, chosen):" in WORKER
