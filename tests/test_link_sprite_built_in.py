"""ZORA's built-in Link sprite sets (zora/rom/link_sprites/, Irenepunmaster's, 2026-10-26), the sheet
converter they were made with (scripts/link_sprite_sheet.py), the page's three-ring preview, the sets'
recommended colors and Link's other colors: each set reads, is offered to the page, and holds no run
of the original game's bytes; the converter reads PRG0's Link back from a sheet drawn in its layout;
the preview draws the main pose from the same tiles Python reads; Link's colors 2 and 3 land on
every palette copy the game loads them from, and nowhere else."""
import importlib.util
import json
import shutil
import struct
import subprocess
import sys
import zlib
from pathlib import Path

import pytest

from scripts import link_sprite_sheet as sheet
from tests.needs import needs_base_rom
from zora.flags.form import metadata
from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
from zora.generate.pipeline import generate_rom
from zora.rom.base_rom import PRG1_ROM_PATH, remember_repo_base_rom, verify_prg1_rom
from zora.rom.link_sprite import (
    LINK_FIXED_COLORS,
    LINK_TILE_GROUPS,
    SPRITE_SET_SIZE,
    SpriteSetError,
    built_in_sprite_sets,
    link_tiles,
    sprite_set_from_object,
    sprite_set_object,
)
from zora.rom.player_settings import (
    RANDOM_COLOR,
    PlayerSettingError,
    PlayerSettings,
    apply_player_settings,
    link_other_colors,
    link_palette_color_offsets,
    player_settings_from_page,
)

REPO = Path(__file__).resolve().parent.parent
MAKE_RELEASE = REPO / "scripts" / "make_release.py"
PAGE_SCRIPT = (REPO / "web" / "zora-web.js").read_text()
BUILT_IN = {"abobo": "Abobo", "agumon": "Agumon", "jason-voorhees": "Jason Voorhees", "mini-ganon": "Mini-Ganon",
            "twilight-sparkle": "Twilight Sparkle Humanoid Pony Edition",
            # ZeroMeaning's, from Z1M1 (scripts/z1m1_link_sprites.py; tests/test_z1m1_link_sprites.py)
            "zeromeaning-ganon": "Ganon", "zeromeaning-justin-bailey": "Justin Bailey", "zeromeaning-kraid": "Kraid",
            "zeromeaning-link-bunny": "Link (Bunny)", "zeromeaning-link-female": "Link (Female)",
            "zeromeaning-link-invisible": "Link (Invisible)", "zeromeaning-mother-brain": "Mother Brain",
            "zeromeaning-samus": "Samus", "zeromeaning-zelda": "Zelda"}
# Runs of a set's tiles equal to the game's that were reviewed and accepted (ruling, 2026-10-26: original
# art by Irenepunmaster whose shield and sword rows match the game's pixel for pixel), by set: any
# other run, in these sets or another, still fails.
REVIEWED_RUNS = {
    "abobo": {"3e6f466e6e7e00003f7f7f7f7f7f3e0000", "ffffe78181e7e7e77e"},
    "jason-voorhees": {"3f3f3f7fffe10000", "f7efdeecf0f83c3c", "6f466e6e7e00003f7f7f7f7f7f3e0000",
                       "ffffe78181e7e7e77e"},
    # ZeroMeaning's sets ship the original Link's bytes they keep as blanks (fromGame); what is left are
    # coincidences (ruling, 2026-10-28): Zelda's nine bytes across tiles 29 and 30 match level 9's Zelda
    # (0x0EB63), not Link; Kraid's three bytes of its own beside a blanked run read as a run elsewhere.
    "zeromeaning-zelda": {"383c3b303020200000"},
    "zeromeaning-kraid": {"04060b0000000000"},
}
BACKGROUND = (116, 116, 116)
BORDER_COLOR = (0, 128, 0)


def test_the_built_in_sets() -> None:
    sets = built_in_sprite_sets()
    assert {set_id: sprite_set.name for set_id, sprite_set in sets.items()} == BUILT_IN
    assert list(sets) == sorted(sets)                 # Random's order
    assert all(sprite_set.author == ("ZeroMeaning" if set_id.startswith("zeromeaning-") else "Irenepunmaster")
               and sprite_set.provenance for set_id, sprite_set in sets.items())
    assert all(len(sprite_set.tiles) == SPRITE_SET_SIZE for sprite_set in sets.values())


@pytest.mark.skipif(not MAKE_RELEASE.exists(), reason="scripts/make_release.py is not released")
def test_no_set_holds_original_game_bytes(monkeypatch: pytest.MonkeyPatch) -> None:
    """The release's byte check (scripts/make_release.py check_game_bytes) on each set's tiles, which it
    cannot read as base64: no run of 8 or more equal to PRG0 (or PRG1), filler and REVIEWED_RUNS aside."""
    monkeypatch.syspath_prepend(str(REPO))              # make_release imports zora from the repo root
    spec = importlib.util.spec_from_file_location("make_release_under_test", MAKE_RELEASE)
    assert spec and spec.loader
    make_release = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, make_release)     # its dataclasses look themselves up
    spec.loader.exec_module(make_release)
    roms = [remember_repo_base_rom(), *([verify_prg1_rom().read_bytes()] if PRG1_ROM_PATH.exists() else [])]
    for set_id, sprite_set in built_in_sprite_sets().items():
        text = [(f"zora/rom/link_sprites/{set_id}.json", f'fromhex("{sprite_set.tiles.hex()}")')]
        for rom in roms:
            runs = {hit.rsplit(": ", 1)[1] for hit in make_release.check_game_bytes(text, rom).hits}
            assert runs == REVIEWED_RUNS.get(set_id, set()), set_id


def test_the_page_is_offered_the_sets_and_the_preview_data() -> None:
    offered = metadata()["linkSpriteSet"]
    # ZORA's 640-byte sets first, then the built-in-art ones (tests/test_link_art.py)
    assert [entry["id"] for entry in offered["builtIn"]][:len(BUILT_IN)] == list(BUILT_IN)
    assert offered["builtIn"][0] == {"id": "abobo", **sprite_set_object(built_in_sprite_sets()["abobo"])}
    assert offered["groups"] == [list(group) for group in LINK_TILE_GROUPS]
    assert offered["fixedColors"] == list(LINK_FIXED_COLORS) == [0x27, 0x17]


def drawn_sheet(tiles: bytes) -> list[list[tuple[int, int, int]]]:
    """A set drawn in the converter's sheet layout: every use of every half, as the game draws it."""
    colors = [BACKGROUND, *sheet.GAME_LINK_COLORS]
    width = sheet.BORDER + sheet.CELLS_PER_ROW * (sheet.CELL + sheet.BORDER)
    pixels = [[BORDER_COLOR] * width for _ in range(sheet.CELL + 2 * sheet.BORDER)]
    for number, name in enumerate(sheet.SET_HALVES):
        rows = []
        for tile in (2 * number, 2 * number + 1):
            data = tiles[tile * 16:(tile + 1) * 16]
            rows += [[(data[y] >> (7 - x) & 1) | (data[y + 8] >> (7 - x) & 1) << 1 for x in range(8)]
                     for y in range(8)]
        for use in sheet.SOURCES[name]:
            for y, line in enumerate(rows):
                for x, value in enumerate(line[::-1] if use.flipped else line):
                    left = sheet.BORDER + use.cell * (sheet.CELL + sheet.BORDER) + use.side * sheet.HALF
                    pixels[sheet.BORDER + y][left + x] = colors[value]
    return pixels


def png(pixels: list[list[tuple[int, int, int]]]) -> bytes:
    """An RGB PNG, each row with the Sub filter, so the reader's unfiltering is exercised."""
    raw = b""
    for row in pixels:
        flat = bytes(channel for pixel in row for channel in pixel)
        raw += b"\x01" + bytes((flat[i] - (flat[i - 3] if i >= 3 else 0)) & 0xFF for i in range(len(flat)))

    def chunk(kind: bytes, body: bytes) -> bytes:
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body))
    header = struct.pack(">IIBBBBB", len(pixels[0]), len(pixels), 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")


@needs_base_rom
def test_the_converter_reads_prg0s_link_back(tmp_path: Path) -> None:
    """PRG0's Link drawn as a sheet, written as a PNG and converted: the same 640 bytes, and no cell the
    game cannot show (every shared and mirrored half agrees)."""
    original = link_tiles(remember_repo_base_rom())
    path = tmp_path / "link.png"
    path.write_bytes(png(drawn_sheet(original)))
    tiles, differences = sheet.convert(sheet.read_png(path), 0, sheet.GAME_LINK_COLORS, BACKGROUND)
    assert tiles == original and differences == []


def test_the_converter_names_a_cell_the_game_cannot_show() -> None:
    tiles = built_in_sprite_sets()["twilight-sparkle"].tiles
    pixels = drawn_sheet(tiles)
    lift_right = sheet.BORDER + 9 * (sheet.CELL + sheet.BORDER) + sheet.HALF
    pixels[sheet.BORDER][lift_right] = sheet.GAME_LINK_COLORS[0]
    back, differences = sheet.convert(pixels, 0, sheet.GAME_LINK_COLORS, BACKGROUND)
    assert back == tiles
    assert differences == ["cell 9 right: 1 pixels differ from cell 1's (the game draws both from tile $08)"]


def page_function(name: str) -> str:
    start = PAGE_SCRIPT.index(f"function {name}(")
    return PAGE_SCRIPT[start:PAGE_SCRIPT.index("\n}\n", start) + 2]


def test_the_preview_draws_the_main_pose_from_the_sets_tiles() -> None:
    """The page's previewFrame on a built-in set: walking down with the small shield, tile $58 on the
    left and $0A on the right (the converter's cell 0), as Python reads them."""
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is not installed")
    tiles = built_in_sprite_sets()["mini-ganon"].tiles
    constant = next(line for line in PAGE_SCRIPT.splitlines() if line.startswith("const PREVIEW_HALVES = "))
    script = "\n".join([constant, page_function("previewFrame"),
                        f"console.log(JSON.stringify(previewFrame({json.dumps(list(tiles))})));"])
    frame = json.loads(subprocess.run([node, "-e", script], capture_output=True, text=True, check=True).stdout)
    left, right = (sheet.SET_HALVES.index(name) for name in ("$58", "$0A"))
    assert sheet.SOURCES["$58"][0] == sheet.Use(0, 0) and sheet.SOURCES["$0A"][0] == sheet.Use(0, 1)
    expected = []
    for y in range(16):
        line = []
        for half in (left, right):
            tile = (2 * half + y // 8) * 16
            line += [(tiles[tile + y % 8] >> (7 - x) & 1) | (tiles[tile + 8 + y % 8] >> (7 - x) & 1) << 1
                     for x in range(8)]
        expected.append(line)
    assert frame == expected


def test_the_page_sends_a_built_in_set_as_the_set() -> None:
    choice = page_function("currentPlayerSettings")
    assert "builtInLinkSpriteSet(settings.linkSprite)" in choice and "settings.linkSpriteSet = builtIn" in choice
    row = page_function("linkSpriteRow")
    assert "metadata.linkSpriteSet.builtIn" in row and "linkSpritePreview()" in row


def test_every_built_in_set_recommends_colors() -> None:
    for sprite_set in built_in_sprite_sets().values():
        assert sprite_set.recommended is not None
        assert sprite_set_from_object(sprite_set_object(sprite_set)) == sprite_set


def test_recommended_colors_are_checked() -> None:
    data = sprite_set_object(built_in_sprite_sets()["twilight-sparkle"])
    for bad in ({"tunics": [0x29, 0x32], "other": [0x27, 0x17]}, {"tunics": [0x29, 0x32, 0x0D], "other": [1, 2]},
                {"tunics": [0x29, 0x32, 0x16], "other": [0x27, 0x40]}, "red"):
        with pytest.raises(SpriteSetError):
            sprite_set_from_object({**data, "recommendedColors": bad})
    assert sprite_set_from_object({key: value for key, value in data.items() if key != "recommendedColors"}
                                  ).recommended is None          # optional: an older file has none


@needs_base_rom
def test_link_other_colors_land_on_every_palette_copy_and_nowhere_else() -> None:
    """Each changed color on its 14 bytes (ten level palettes, the title story's, three file-select
    Links), which hold the game's color there; a color left at the game's writes nothing."""
    rom = remember_repo_base_rom()
    for number, game in ((2, 0x27), (3, 0x17)):
        offsets = link_palette_color_offsets(number)
        assert len(offsets) == 14
        assert {rom[offset] for offset in offsets} == {game, {2: 0x37, 3: 0x07}[number]}
    out = bytearray(rom)
    link_other_colors(out, (0x32, 0x17))
    assert [i for i in range(len(rom)) if out[i] != rom[i]] == sorted(
        i for i in link_palette_color_offsets(2) if rom[i] != 0x32)
    assert all(out[i] == 0x32 for i in link_palette_color_offsets(2))
    unchanged = bytearray(rom)
    link_other_colors(unchanged, (0x27, 0x17))
    assert unchanged == rom


def test_the_page_sends_link_other_colors() -> None:
    assert player_settings_from_page({"linkColor2": 0x32, "linkColor3": 0x14}).link_colors == (0x32, 0x14)
    assert player_settings_from_page({"linkColor3": 0x30}).link_colors == (0x27, 0x30)
    assert player_settings_from_page({}).link_colors == (0x27, 0x17)
    for bad in (0x0D, 0x40, RANDOM_COLOR):
        with pytest.raises(PlayerSettingError):
            player_settings_from_page({"linkColor2": bad})


@needs_base_rom
def test_link_other_colors_on_a_finished_rom() -> None:
    base = remember_repo_base_rom()
    rom = generate_rom(MVP_BASELINE_LEVEL_ENCODING_OFF, 7, base).rom
    plain = apply_player_settings(rom, PlayerSettings())
    colored = apply_player_settings(rom, PlayerSettings(link_colors=(0x32, 0x14)))
    changed = {i for i in range(len(rom)) if plain[i] != colored[i]}
    assert changed <= set(link_palette_color_offsets(2)) | set(link_palette_color_offsets(3)) and changed
