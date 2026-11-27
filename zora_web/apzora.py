"""The web page's "Build your ROM from a .apzora" step (2.0.2; owner decisions, 2026-11-21).

A host collects the players' YAMLs and generates the multiworld; each player then gets a .apzora, Archipelago's
patch container (archipelago/rom.py ZoraProcedurePatch: a zip holding archipelago.json and ZORA's recipe,
recipe.json). Archipelago's own patcher rebuilds the ROM from the recipe and the player's ROM
(zora.archipelago.rom_from_recipe). This step does the same in the page, with the look-and-feel settings the
player picks now: the recipe's playerSettings are replaced by the player's choices, and nothing else in the
recipe changes, so the seed, the slot identity and the items are the ones every other player's game expects.

The recipe pins the copy of ZORA that made it (its version and source hash, check_recipe), so the page builds
only recipes its own version made; for another version it names that version and links its archived page.
"""
from __future__ import annotations

import io
import json
import zipfile
from collections.abc import Mapping
from pathlib import PurePosixPath
from typing import Any

from zora import archipelago
from zora.rom.link_art import link_sprite_set_object, offered_sprite_sets
from zora.rom.player_settings import PAGE_LINK_SPRITE, PAGE_LINK_SPRITE_SET, PlayerSettingError
from zora.version import ZORA_VERSION

# The patch container's files (archipelago/rom.py) and its game
MANIFEST_FILE = "archipelago.json"
RECIPE_FILE = "recipe.json"
GAME = "ZORA"
PATCH_FILE_ENDING = ".apzora"
ROM_FILE_ENDING = ".nes"
# Where a released version's page is kept once a newer one replaces it (scripts/publish_site.sh --archive VERSION,
# scripts/gh_pages_commit.sh: VERSION/index.html on the site)
ARCHIVE_URL = "https://zora.gg/{version}/"
NOT_A_PATCH = "This isn't a ZORA patch (.apzora): {why}."
# A recipe value the player keeps as the recipe has it: a sprite set of its own, not one of ZORA's built-in sets
OWN_SET = "recipe-set"


class ApzoraRefused(ValueError):
    """A .apzora this page can't build from, with the reason for the player."""


def archive_url(version: str) -> str:
    return ARCHIVE_URL.format(version=version)


def _read(data: bytes) -> tuple[dict[str, Any], dict[str, Any]]:
    """The container's manifest and recipe; ApzoraRefused for anything that isn't a ZORA patch."""
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as container:
            names = set(container.namelist())
            missing = [name for name in (MANIFEST_FILE, RECIPE_FILE) if name not in names]
            if missing:
                raise ApzoraRefused(NOT_A_PATCH.format(why=f"it has no {' or '.join(missing)}"))
            manifest = json.loads(container.read(MANIFEST_FILE))
            recipe = json.loads(container.read(RECIPE_FILE))
    except zipfile.BadZipFile:
        raise ApzoraRefused(NOT_A_PATCH.format(why="it isn't a patch file (not a zip archive)")) from None
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ApzoraRefused(NOT_A_PATCH.format(why="its contents can't be read")) from None
    if not isinstance(manifest, dict) or not isinstance(recipe, dict):
        raise ApzoraRefused(NOT_A_PATCH.format(why="its contents can't be read"))
    if manifest.get("game") != GAME:
        raise ApzoraRefused(NOT_A_PATCH.format(why=f"it is a patch for {manifest.get('game')!r}, not {GAME}"))
    if recipe.get("format") != archipelago.RECIPE_FORMAT:
        raise ApzoraRefused(NOT_A_PATCH.format(why="its recipe is not ZORA's"))
    return manifest, recipe


def version_problem(recipe: Mapping[str, Any]) -> dict[str, Any] | None:
    """Why this page's ZORA can't rebuild the recipe, read from its producer before anything is built, or
    None: another version (with that version's archived page), another build of this version, or a refusal
    of check_recipe's (another recipe format)."""
    producer = recipe.get("producer")
    version = producer.get("version") if isinstance(producer, Mapping) else None
    if not isinstance(version, str) or not version:
        return {"reason": NOT_A_PATCH.format(why="its recipe names no ZORA version")}
    if version != ZORA_VERSION:
        return {"reason": f"This patch was made by ZORA {version}, and this page is ZORA {ZORA_VERSION}: a patch "
                          f"is rebuilt only by the ZORA version that made it. Build it on ZORA {version}'s page, "
                          f"or with Archipelago's own patcher, which keeps the look and feel chosen in the YAML.",
                "version": version, "archiveUrl": archive_url(version)}
    try:
        archipelago.check_recipe(recipe)
    except archipelago.RecipeRefused as refused:
        if (recipe.get("format"), recipe.get("formatVersion")) == (archipelago.RECIPE_FORMAT,
                                                                  archipelago.RECIPE_FORMAT_VERSION):
            return {"reason": f"This patch was made by another build of ZORA {version} (its source hash differs "
                              f"from this page's), so this page can't rebuild it. Build it on the page that came "
                              f"with its zora.apworld, or with Archipelago's own patcher.", "version": version}
        return {"reason": f"This patch can't be built here: {refused}."}
    return None


def shown_settings() -> list[archipelago.PlayerSettingSpec]:
    """The look-and-feel settings the step offers: every setting a recipe's playerSettings holds
    (archipelago.player_setting_fields) that the ROM is built with. The Multiworld-only ones (Sound when an item
    arrives) are left as the recipe has them: the client reads them from the generated game, not the ROM."""
    return [spec for spec in archipelago.player_setting_fields() if not spec.multiworld_only]


def _built_in_id(sprite_set: object) -> str | None:
    return next((set_id for set_id, offered in offered_sprite_sets().items()
                 if link_sprite_set_object(offered) == sprite_set), None)


def prefilled(player_settings: Mapping[str, Any]) -> dict[str, Any]:
    """The recipe's own playerSettings as the step's controls hold them (page keys and values; a built-in
    sprite set by its id, another set as OWN_SET), each missing one at its default."""
    values: dict[str, Any] = {}
    for spec in shown_settings():
        value = player_settings.get(spec.key, spec.default)
        if spec.key == PAGE_LINK_SPRITE and value == "set":
            value = _built_in_id(player_settings.get(PAGE_LINK_SPRITE_SET)) or OWN_SET
        values[spec.key] = value
    return values


def _setting_json(spec: archipelago.PlayerSettingSpec, value: Any) -> dict[str, Any]:
    entry: dict[str, Any] = {"key": spec.key, "label": spec.label, "kind": spec.kind, "value": value,
                             "choices": [list(choice) for choice in spec.choices], "colors": list(spec.colors)}
    if spec.key == PAGE_LINK_SPRITE and value == OWN_SET:
        entry["choices"].insert(0, [OWN_SET, "The recipe's own sprite set"])
    if spec.rule is not None:
        entry["rule"] = {"min": spec.rule.min_length, "max": spec.rule.max_length}
    return entry


def read_apzora(data: bytes, file_name: str = "") -> dict[str, Any]:
    """What the step shows for a .apzora: ok with the player's name and slot, the ROM's file name (the
    patch's, as Archipelago names it: the same name with .nes) and the look-and-feel settings prefilled
    from the recipe; or not ok with the reason, and for another ZORA version that version and its
    archived page. Nothing is built here."""
    try:
        manifest, recipe = _read(data)
    except ApzoraRefused as refused:
        return {"ok": False, "reason": str(refused)}
    problem = version_problem(recipe)
    if problem is not None:
        return {"ok": False, **problem}
    values = prefilled(recipe.get("playerSettings") or {})
    return {"ok": True, "playerName": manifest.get("player_name"), "player": manifest.get("player"),
            "romFileName": rom_file_name(file_name), "version": ZORA_VERSION,
            "settings": [_setting_json(spec, values[spec.key]) for spec in shown_settings()]}


def rom_file_name(patch_file_name: str) -> str:
    """The ROM's name as Archipelago's patcher gives it: the patch's name with .nes for .apzora."""
    name = PurePosixPath(patch_file_name.replace("\\", "/")).name or f"ZORA{PATCH_FILE_ENDING}"
    stem = name[:-len(PATCH_FILE_ENDING)] if name.lower().endswith(PATCH_FILE_ENDING) else name
    return stem + ROM_FILE_ENDING


def recipe_with_settings(recipe: Mapping[str, Any], chosen: Mapping[str, Any]) -> dict[str, Any]:
    """A copy of the recipe whose playerSettings are the player's choices (page keys and values, as
    prefilled gives them); nothing else changes. A setting the step doesn't show (Sound when an item
    arrives) stays as the recipe has it; OWN_SET keeps the recipe's own sprite set. PlayerSettingError
    for a choice finish() would refuse."""
    original = dict(recipe.get("playerSettings") or {})
    shown = {spec.key for spec in shown_settings()}
    unknown = sorted(set(chosen) - shown)
    if unknown:
        raise PlayerSettingError(f"not a look-and-feel setting of this step: {unknown}")
    choices = dict(chosen)
    keep_own_set = choices.get(PAGE_LINK_SPRITE) == OWN_SET
    if keep_own_set:
        choices[PAGE_LINK_SPRITE] = "set"
    archipelago.check_player_settings({key: value for key, value in choices.items()
                                       if not (keep_own_set and key == PAGE_LINK_SPRITE)})
    kept = {key: value for key, value in original.items() if key not in shown and key != PAGE_LINK_SPRITE_SET}
    if keep_own_set and PAGE_LINK_SPRITE_SET in original:
        kept[PAGE_LINK_SPRITE_SET] = original[PAGE_LINK_SPRITE_SET]
    return {**recipe, "playerSettings": {**kept, **archipelago.page_player_settings(choices)}}


def build_rom(data: bytes, rom: bytes, chosen: Mapping[str, Any] | None = None) -> bytes:
    """The player's ROM from their .apzora and their own ROM (PRG0 or PRG1), with the chosen look and feel
    (None: the recipe's own), as Archipelago's patcher builds it: archipelago.rom_from_recipe, which runs
    BUILD and FINISH with FINISH's sanity check. ApzoraRefused for a patch this page can't build;
    PlayerSettingError for a refused choice; RecipeNotReproduced as the patcher would raise it."""
    _manifest, recipe = _read(data)
    problem = version_problem(recipe)
    if problem is not None:
        raise ApzoraRefused(problem["reason"])
    if chosen is not None:
        recipe = recipe_with_settings(recipe, chosen)
    return archipelago.rom_from_recipe(recipe, archipelago.checked_rom(rom))
