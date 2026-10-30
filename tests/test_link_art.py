"""Built-in-art Link sprite sets (zora/rom/link_art.py): arrangements of the game's own tiles, assembled
from the player's ROM. Each built-in one reads and writes back to its file, holds no tile data, and
assembles from the ROM it is given (so custom graphics carry through); a wrong arrangement is refused
with a message; a finished ROM with one differs from the original Link's only in Link's groups; the
page offers them, sends them back as Python reads them, and previews them as Python assembles them."""
import json
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from tests.needs import needs_base_rom
from tests.test_link_sprite_built_in import PAGE_SCRIPT, page_function
from zora.flags.form import metadata
from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
from zora.generate.pipeline import generate_rom
from zora.rom.base_rom import PRG1_ROM_PATH, remember_repo_base_rom, verify_prg1_rom
from zora.rom.link_art import (
    ART_BLOCKS,
    ArtHalf,
    ArtSet,
    ArtSwap,
    art_set_file,
    art_set_from_object,
    art_set_object,
    art_tiles,
    built_in_art_sets,
    half_tiles,
    has_swap,
    offered_sprite_sets,
    original_link_half,
    swap_writes,
)
from zora.rom.link_sprite import HALF_SIZE, LINK_HALVES, SPRITE_SET_SIZE, SpriteSetError, link_tile_offsets, link_tiles
from zora.rom.player_settings import (
    LinkSprite,
    PlayerSettingError,
    PlayerSettings,
    apply_player_settings,
    player_settings_from_page,
    resolved_player_settings,
    written_offsets,
)

FOLDER = Path(__file__).resolve().parent.parent / "zora" / "rom" / "link_art"
BUILT_IN_ART = {"darknut": "Darknut", "gibdo": "Gibdo", "goriya": "Goriya", "lynel": "Lynel", "merchant": "Merchant",
                "moblin": "Moblin", "old-man": "Old Man", "old-woman": "Old Woman", "stalfos": "Stalfos",
                "wizzrobe": "Wizzrobe", "zelda": "Zelda"}
PEOPLE = {"merchant", "old-man", "old-woman", "zelda"}         # the sets with a swap
# Where the playable character's colors go (the tunics, colors 2 and 3), which a set's own colors write
COLOR_BYTES = written_offsets("tunic_colors") | written_offsets("link_colors")


def reader(rom: bytes) -> Callable[[int, int], bytes]:
    return lambda offset, length: rom[offset:offset + length]


def test_the_built_in_art_sets() -> None:
    sets = built_in_art_sets()
    assert {set_id: art.name for set_id, art in sets.items()} == BUILT_IN_ART
    for set_id, art in sets.items():
        text = (FOLDER / f"{set_id}.json").read_text()
        assert art_set_file(art) == text and art_set_from_object(json.loads(text)) == art
        assert "tiles" not in json.loads(text)              # an arrangement ships no tile data


def test_offered_sets_are_both_kinds_without_a_shared_id() -> None:
    offered = offered_sprite_sets()
    assert list(offered)[-len(BUILT_IN_ART):] == list(BUILT_IN_ART)


@needs_base_rom
def test_each_set_is_assembled_from_the_rom_it_is_given() -> None:
    """From PRG0 the set's halves are the source halves (mirrored, recolored); from a ROM with other
    art in a source half, that half changes and nothing else."""
    base = remember_repo_base_rom()
    for art in built_in_art_sets().values():
        tiles = art_tiles(art, reader(base))
        assert len(tiles) == SPRITE_SET_SIZE
        for index, half in enumerate(art.halves):
            source = base[half.offset:half.offset + HALF_SIZE]
            assert tiles[index * HALF_SIZE:(index + 1) * HALF_SIZE] == half_tiles(source, half.mirror, art.colors)
    moblin = built_in_art_sets()["moblin"]
    changed = bytearray(base)
    first = moblin.halves[0]
    changed[first.offset:first.offset + HALF_SIZE] = bytes(range(HALF_SIZE))
    before, after = art_tiles(moblin, reader(base)), art_tiles(moblin, reader(bytes(changed)))
    differing = {index // HALF_SIZE for index in range(SPRITE_SET_SIZE) if before[index] != after[index]}
    assert differing == {index for index, half in enumerate(moblin.halves) if half.offset == first.offset}


def test_mirroring_and_recoloring() -> None:
    # One row of colors 0, 1, 2, 3, 0, 1, 2, 3 in the top tile; the bottom tile empty.
    source = bytes([0b01010101] + [0] * 7 + [0b00110011] + [0] * 7) + bytes(16)
    mirrored = half_tiles(source, True, (1, 2, 3))
    assert mirrored[0] == 0b10101010 and mirrored[8] == 0b11001100
    swapped = half_tiles(source, False, (2, 1, 3))           # colors 1 and 2 exchanged
    assert swapped[0] == 0b00110011 and swapped[8] == 0b01010101


@needs_base_rom
def test_a_finished_rom_differs_only_in_links_groups() -> None:
    base = remember_repo_base_rom()
    rom = generate_rom(MVP_BASELINE_LEVEL_ENCODING_OFF, 1, base).rom
    groups = link_tile_offsets()
    for art in built_in_art_sets().values():
        styled = apply_player_settings(rom, PlayerSettings(link_sprite=LinkSprite.SET, sprite_set=art))
        assert link_tiles(styled) == art_tiles(art, reader(base))
        # the set's own colors too, the default (Playable character's colors: The set's own)
        assert all(styled[i] == rom[i] for i in range(len(rom)) if i not in groups | COLOR_BYTES)


@pytest.mark.skipif(not PRG1_ROM_PATH.exists(), reason="needs the PRG1 ROM")
@needs_base_rom
def test_prg1_holds_the_same_art() -> None:
    prg1 = verify_prg1_rom().read_bytes()
    base = remember_repo_base_rom()
    for art in built_in_art_sets().values():
        assert art_tiles(art, reader(prg1)) == art_tiles(art, reader(base))


def arrangement(**changes: Any) -> dict[str, Any]:
    data = art_set_object(built_in_art_sets()["moblin"])
    data["halves"] = dict(data["halves"])
    for key, value in changes.items():
        if key.startswith("$"):
            data["halves"][key] = value
        elif value is None:
            del data[key]
        else:
            data[key] = value
    return data


@pytest.mark.parametrize(("change", "message"), [
    ({"$00": {"block": "PatternBlockNope", "tile": "$F0"}}, "unknown block"),
    ({"$00": {"block": "PatternBlockOWSP", "tile": "$F1"}}, "top tile of a half"),
    ({"$00": {"block": "PatternBlockOWSP", "tile": "$80"}}, "top tile of a half"),
    ({"$00": {"block": "PatternBlockOWSP", "tile": "F0"}}, '"$XX"'),
    ({"$00": {"block": "PatternBlockOWSP", "tile": "$F0", "mirror": "yes"}}, "half $00"),
    ({"colors": [1, 2, 4]}, '"colors"'),
    ({"colors": [1, 2]}, '"colors"'),
    ({"name": ""}, "needs a name"),
    ({"version": 2}, "version 2"),
])
def test_a_wrong_arrangement_is_refused_with_a_message(change: dict[str, Any], message: str) -> None:
    with pytest.raises(SpriteSetError, match=message.replace("$", r"\$")):
        art_set_from_object(arrangement(**change))


def test_every_half_is_named() -> None:
    data = arrangement()
    del data["halves"]["$60"]
    with pytest.raises(SpriteSetError, match="each of Link's halves once"):
        art_set_from_object(data)
    with pytest.raises(SpriteSetError, match="all 20"):
        ArtSet("A", "B", "", (ArtHalf("PatternBlockOWSP", 0xF0),) * 19)


def test_the_page_offers_them_and_sends_them_back() -> None:
    offered = metadata()["linkSpriteSet"]
    built_in = {entry["id"]: entry for entry in offered["builtIn"]}
    for set_id, art in built_in_art_sets().items():
        assert built_in[set_id] == {"id": set_id, **art_set_object(art)}
        settings = player_settings_from_page({"linkSprite": "set", "linkSpriteSet": built_in[set_id]})
        assert settings.sprite_set == art
    assert offered["art"]["halves"] == list(LINK_HALVES)
    assert offered["art"]["blocks"] == {name: [block.offset, block.first_tile] for name, block in ART_BLOCKS.items()}


@needs_base_rom
def test_the_preview_assembles_them_as_python_does() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is not installed")
    base = remember_repo_base_rom()
    art_metadata = metadata()["linkSpriteSet"]["art"]
    for headerless in (False, True):
        rom = base[16:] if headerless else base
        for art in built_in_art_sets().values():
            script = "\n".join([
                f"const metadata = {{linkSpriteSet: {{art: {json.dumps(art_metadata)}}}}};",
                page_function("headerShift"), page_function("artSetTiles"),
                f"const rom = Uint8Array.from({json.dumps(list(rom))});",
                f"console.log(JSON.stringify(Array.from(artSetTiles({json.dumps(art_set_object(art))}, rom))));"])
            drawn = json.loads(subprocess.run([node, "-e", script], capture_output=True, text=True,
                                              check=True).stdout)
            assert bytes(drawn) == art_tiles(art, reader(base))
    assert "artSetTiles(builtIn, baseRom)" in PAGE_SCRIPT


@pytest.mark.slow
@needs_base_rom
def test_the_game_draws_link_from_the_assembled_tiles() -> None:
    """In the emulator, in play: the pattern tables hold the set's common-sprite tiles ($00-$1B)."""
    from tests.emulator import Button, Emulator
    base = remember_repo_base_rom()
    art = built_in_art_sets()["moblin"]
    emu = Emulator(generate_rom(MVP_BASELINE_LEVEL_ENCODING_OFF, 1, base,
                                PlayerSettings(link_sprite=LinkSprite.SET, sprite_set=art)).rom)
    emu.new_game()
    emu.run(30, Button.UP)
    assert art_tiles(art, reader(base))[:28 * 16] in emu.pattern_tables()



def test_the_people_have_a_swap_and_the_monsters_none() -> None:
    assert {set_id for set_id, art in built_in_art_sets().items() if has_swap(art)} == PEOPLE


@needs_base_rom
def test_the_swap_draws_the_person_as_the_original_link() -> None:
    """With the swap, a person set also writes the person's halves, each the original Link's half (from
    the player's ROM, whatever sprite Link gets) mirrored and recolored as the set says; nothing else."""
    base = remember_repo_base_rom()
    rom = generate_rom(MVP_BASELINE_LEVEL_ENCODING_OFF, 1, base).rom
    groups = link_tile_offsets()
    for set_id in sorted(PEOPLE):
        art = built_in_art_sets()[set_id]
        plain = apply_player_settings(rom, PlayerSettings(link_sprite=LinkSprite.SET, sprite_set=art))
        swapped = apply_player_settings(rom, PlayerSettings(link_sprite=LinkSprite.SET, sprite_set=art,
                                                            link_sprite_swap=True))
        targets = {swap.target.offset + i for swap in art.swaps for i in range(HALF_SIZE)}
        assert {i for i in range(len(rom)) if swapped[i] != plain[i]} <= targets
        for swap in art.swaps:
            link_half = original_link_half(swap.link_half, reader(base))
            assert swapped[swap.target.offset:swap.target.offset + HALF_SIZE] == half_tiles(link_half, swap.mirror,
                                                                                           swap.colors)
        assert all(plain[i] == rom[i] for i in range(len(rom)) if i not in groups | COLOR_BYTES)


@needs_base_rom
def test_the_swap_leaves_z1rr_coops_ranges() -> None:
    from tests.test_coop_reserved import RESERVED_BYTES
    for art in built_in_art_sets().values():
        assert not any(offset + i in RESERVED_BYTES for offset, data in swap_writes(art) for i in range(len(data)))


def test_the_swap_needs_a_person_set_and_random_never_swaps() -> None:
    for sprite_set in (None, built_in_art_sets()["moblin"]):
        with pytest.raises(PlayerSettingError, match="the swap needs"):
            PlayerSettings(link_sprite=LinkSprite.SET if sprite_set else LinkSprite.LINK, sprite_set=sprite_set,
                           link_sprite_swap=True)
    asked = PlayerSettings(link_sprite=LinkSprite.RANDOM, link_sprite_swap=True)
    assert not any(resolved_player_settings(asked, seed).link_sprite_swap for seed in range(1, 101))
    zelda = next(entry for entry in metadata()["linkSpriteSet"]["builtIn"] if entry["id"] == "zelda")
    page = {"linkSprite": "set", "linkSpriteSet": zelda, "linkSpriteSwap": "on"}
    assert player_settings_from_page(page).link_sprite_swap
    with pytest.raises(PlayerSettingError, match="linkSpriteSwap"):
        player_settings_from_page({"linkSpriteSwap": "maybe"})


def test_a_wrong_swap_is_refused() -> None:
    with pytest.raises(SpriteSetError, match="Link's half"):
        ArtSwap(ArtHalf("PatternBlockOWSP", 0x98), "$99")
    with pytest.raises(SpriteSetError, match="a person's own half"):      # a Moblin's tiles: not a swap's
        ArtSwap(ArtHalf("PatternBlockOWSP", 0xF0), "$0A")
    with pytest.raises(SpriteSetError, match='"swap" is a list'):
        art_set_from_object(arrangement(swap={"block": "PatternBlockOWSP"}))
