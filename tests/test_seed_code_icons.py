"""The seed code as pictures (zora/rom/seed_code_icons.py; owner's backlog, 2026-10-18): each code
item drawn from the finished ROM as its file-select screen draws it. Every check compares with the
screen itself: the ROM booted to the file-select menu in the emulator (tests/emulator.py, cynes),
whose palette the page paints with (web/zora-web.js NES_PALETTE, from cynes' own table)."""
import json
import re
import shutil
import subprocess
from functools import cache
from pathlib import Path

import numpy as np
import pytest

from tests.emulator import Emulator
from tests.test_feature_patches import vanilla
from zora.flags import zora_flags
from zora.flags.fields import ThreeState
from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
from zora.flags.zora_flags import ZoraFlags
from zora.generate.pipeline import generate_rom
from zora.rom.base_rom import PRG1_ROM_PATH
from zora.rom.code_patches import BOOMERANG_CODE, SEED_CODE_ADDRESS, SEED_CODE_ITEMS, SEED_CODE_LENGTH, SEED_CODE_NAMES
from zora.rom.layout import NES_HEADER_SIZE
from zora.rom.player_settings import PlayerSettings
from zora.rom.revision import GRAPHICS_BLOCKS
from zora.rom.seed_code_icons import ICON_SIZE, CodeIcon, seed_code_icons
from zora_web.api import code_icons

REPO = Path(__file__).resolve().parent.parent
PAGE_SCRIPT = (REPO / "web" / "zora-web.js").read_text()
SEED = 12345
# asm/fp-hash-01: the icons' X (CodeIconXs) and the screen line under sprite Y $27.
FIRST_ICON_X, ICON_SPACING, ICON_TOP = 0x68, 0x10, 0x28
BOOTS = zora_flags.encode(ZoraFlags(pegasus_boots=ThreeState.ON))
BOMBS, WOODEN_SWORD, WAND = 0x00, 0x01, 0x10
BOMB_TILE = 0x34                        # Anim_ItemFrameTiles' bomb, a half-width sprite pair $34/$35


def nes_palette() -> list[tuple[int, int, int]]:
    """The page's NES palette, $00-$3F as RGB."""
    table = re.search(r"^const NES_PALETTE = \[(.*?)^\];", PAGE_SCRIPT, re.MULTILINE | re.DOTALL)
    assert table
    return [(int(color[0:2], 16), int(color[2:4], 16), int(color[4:6], 16))
            for color in re.findall(r'"#([0-9a-f]{6})"', table.group(1))]


def rgb(icon: CodeIcon) -> np.ndarray:
    palette = nes_palette()
    return np.array([[palette[color] for color in row] for row in icon.pixels], dtype=np.uint8)


def on_screen(rom: bytes) -> list[np.ndarray]:
    """The four icons' 16x16 squares of the file-select screen, as RGB."""
    emu = Emulator(rom)
    emu.boot_to_file_select()
    left = [FIRST_ICON_X + index * ICON_SPACING for index in range(SEED_CODE_LENGTH)]
    return [emu.last_frame[ICON_TOP:ICON_TOP + ICON_SIZE, x:x + ICON_SIZE] for x in left]


def assert_drawn_as_the_screen(rom: bytes) -> list[CodeIcon]:
    icons = seed_code_icons(rom)
    for icon, shown in zip(icons, on_screen(rom), strict=True):
        assert np.array_equal(rgb(icon), shown), icon.name
    return icons


def with_code(rom: bytes, items: list[int]) -> bytes:
    """The finished ROM showing these four code items instead of its own."""
    changed = bytearray(rom)
    changed[SEED_CODE_ADDRESS:SEED_CODE_ADDRESS + SEED_CODE_LENGTH] = bytes(items)
    return bytes(changed)


@cache
def finished(base: bytes = b"", zora_flag_string: str = "",
             settings: PlayerSettings = PlayerSettings()) -> bytes:
    return generate_rom(MVP_BASELINE_LEVEL_ENCODING_OFF, SEED, base or vanilla(), settings, zora_flag_string).rom


@pytest.mark.parametrize("first", range(0, len(SEED_CODE_ITEMS), SEED_CODE_LENGTH))
def test_every_code_item_is_drawn_as_the_file_select_screen_draws_it(first: int) -> None:
    """All 27 items, four to a screen (the last screen made up with the first items)."""
    items = [*SEED_CODE_ITEMS[first:], *SEED_CODE_ITEMS][:SEED_CODE_LENGTH]
    icons = assert_drawn_as_the_screen(with_code(finished(), items))
    assert [icon.name for icon in icons] == [SEED_CODE_NAMES[item] for item in items]


def test_pegasus_boots_draw_the_boot() -> None:
    plain = seed_code_icons(with_code(finished(), [BOOMERANG_CODE] * SEED_CODE_LENGTH))[0]
    boots = assert_drawn_as_the_screen(with_code(finished(zora_flag_string=BOOTS), [BOOMERANG_CODE] * SEED_CODE_LENGTH))
    assert boots[0].name == "Pegasus Boots" and boots[0].pixels != plain.pixels


def test_custom_sprites_are_drawn_from_the_players_rom() -> None:
    """A ROM with modified graphics (here the bomb's tiles inverted) shows its own bomb."""
    start = next(start for name, start, _ in GRAPHICS_BLOCKS if name == "CommonSpritePatterns")
    bomb = NES_HEADER_SIZE + start + BOMB_TILE * 16
    custom = bytearray(vanilla())
    custom[bomb:bomb + 32] = bytes(byte ^ 0xFF for byte in custom[bomb:bomb + 32])
    plain = seed_code_icons(with_code(finished(), [BOMBS] * SEED_CODE_LENGTH))[0]
    drawn = assert_drawn_as_the_screen(with_code(finished(bytes(custom)), [BOMBS] * SEED_CODE_LENGTH))[0]
    assert drawn.pixels != plain.pixels


def test_the_tunic_color_setting_shows() -> None:
    """The wooden sword and the wand use the save files' rows, whose color 1 is the green tunic's."""
    items = [WOODEN_SWORD, WAND, WOODEN_SWORD, WAND]
    plain = seed_code_icons(with_code(finished(), items))
    blue = assert_drawn_as_the_screen(with_code(finished(settings=PlayerSettings(tunic_colors=(0x02, 0x32, 0x16))),
                                                items))
    assert all(ours.pixels != theirs.pixels for ours, theirs in zip(blue, plain, strict=True))


def test_prg1_draws_the_same_code_as_prg0() -> None:
    if not PRG1_ROM_PATH.exists():
        pytest.skip("needs the PRG1 ROM")
    prg1 = assert_drawn_as_the_screen(finished(PRG1_ROM_PATH.read_bytes()))
    assert prg1 == seed_code_icons(finished())


def test_the_page_gets_each_icon_as_rows_of_palette_values() -> None:
    icons = json.loads(json.dumps(code_icons(finished())))
    assert icons == [[list(row) for row in icon.pixels] for icon in seed_code_icons(finished())]
    assert all(len(icon) == ICON_SIZE and all(len(row) == ICON_SIZE for row in icon) for icon in icons)


def test_the_page_paints_an_icon_with_the_nes_palette() -> None:
    """iconRgba (run in Node): each palette value as its RGB, opaque."""
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is not installed")
    icon = seed_code_icons(finished())[0]
    pieces = [re.search(rf"^const {name} = .*?;$", PAGE_SCRIPT, re.MULTILINE | re.DOTALL)
              for name in ("NES_PALETTE", "SEED_CODE_ICON_SIZE")]
    function = re.search(r"^function iconRgba\(.*?^}\n", PAGE_SCRIPT, re.MULTILINE | re.DOTALL)
    assert all(pieces) and function
    source = "\n".join([*(piece.group(0) for piece in pieces if piece), function.group(0),
                        f"console.log(JSON.stringify(Array.from(iconRgba({json.dumps(icon.pixels)}))));"])
    painted = json.loads(subprocess.run([node, "-e", source], capture_output=True, text=True, check=True).stdout)
    expected = np.concatenate([rgb(icon), np.full((ICON_SIZE, ICON_SIZE, 1), 255, dtype=np.uint8)], axis=2)
    assert painted == expected.flatten().tolist()


def test_the_page_shows_each_icon_beside_its_name() -> None:
    """onGenerate builds each item from its name and icon; the name stays text and the canvas is
    hidden from screen readers."""
    assert "seedCodeItem(name, icons[index])" in PAGE_SCRIPT
    item = re.search(r"^function seedCodeItem\(.*?^}\n", PAGE_SCRIPT, re.MULTILINE | re.DOTALL)
    assert item and 'ariaHidden: "true"' in item.group(0) and "textContent: name" in item.group(0)
