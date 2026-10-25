"""Every kind of item taken from every kind of cave and shop, in the emulator, without a crash.

2.0 beta 9 crashed on cave takes with randomized music: fairy-refill's TakeCaveItem, which every
cave take calls (zora/rom/fairy_refill.py), sat at bank 1 $A450, and lozft writes its own code over
bank 1 $A423-$A456, so the take ran 7 of lozft's bytes first. Here each cave kind (the take-any
cave, the wood, white and magical sword caves, the letter cave, a shop and the potion shop) has
each item kind (a heart container, a potion, rupees, a fairy, an upgrade) put in its first ware's
place and taken, on PRG0 and PRG1, with the original music and with Music: Random. The second test
keeps every claim of asm/rom_space.toml out of lozft's bytes but the two that never meet it.
"""
from functools import cache

import pytest

from tests.emulator import FRAME_COUNTER
from tests.needs import needs_base_rom
from tests.test_bait_in_pool import CAVE_ITEM_IDS, CAVE_MODE, ITEM_INACTIVE, Console
from tests.test_progressive_emulator import INV_LETTER, LETTER_DELIVERED
from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
from zora.generate.pipeline import generate_rom
from zora.model.enums import Destination, Item
from zora.rom.base_rom import PRG1_ROM_PATH, remember_repo_base_rom
from zora.rom.music.pin import MusicAssets
from zora.rom.parse.rom_file import parse_rom
from zora.rom.player_settings import Music, PlayerSettings

SEED = 1
CAVES = (Destination.TAKE_ANY, Destination.WOOD_SWORD_CAVE, Destination.WHITE_SWORD_CAVE,
         Destination.MAGICAL_SWORD_CAVE, Destination.LETTER_CAVE, Destination.SHOP_1,
         Destination.POTION_SHOP)
ITEMS = (Item.HEART_CONTAINER, Item.RED_POTION, Item.FIVE_RUPEES, Item.FAIRY, Item.BLUE_RING)
SETTLE_FRAMES = 180                         # the lift, the tune and the hearts' fill
# Claims lozft's bytes may meet: the statistics screen's original-music code in bank 0 (with Music on
# the setting writes asm/fp-stats-01-music instead), and z1rr-coop's reserve (no coop ROM has music).
LOZFT_NEIGHBOURS = {"setting:statistics_screen", "z1rr-coop"}


def _music_assets() -> MusicAssets:
    from scripts.music_assets import assets_available, pinned_assets
    if not assets_available():
        pytest.skip("needs the music clone (scripts/music_assets.py)")
    return pinned_assets()


def _base(revision: str) -> bytes:
    if revision == "prg0":
        return remember_repo_base_rom()
    if not PRG1_ROM_PATH.exists():
        pytest.skip(f"needs {PRG1_ROM_PATH.name}")
    remember_repo_base_rom()
    return PRG1_ROM_PATH.read_bytes()


@cache
def _rom(revision: str, music: bool) -> tuple[bytes, dict[Destination, int]]:
    """The finished ROM and the screen of each cave kind."""
    base = _base(revision)
    settings = PlayerSettings(music=Music.RANDOM_STANDARD) if music else PlayerSettings()
    rom = generate_rom(MVP_BASELINE_LEVEL_ENCODING_OFF, SEED, base, settings).rom
    world = parse_rom(rom)
    screens = {destination: next(screen.screen_num for screen in world.overworld.screens
                                 if screen.destination == destination) for destination in CAVES}
    if music:
        from zora.rom.music.randomize import randomize_music
        rom = randomize_music(rom, base, _music_assets(), SEED).rom
    return rom, screens


@needs_base_rom
@pytest.mark.parametrize("music", [False, True], ids=["original music", "Music: Random"])
@pytest.mark.parametrize("revision", ["prg0", "prg1"])
def test_every_item_from_every_cave_is_taken_without_a_crash(revision: str, music: bool) -> None:
    rom, screens = _rom(revision, music)
    for destination in CAVES:
        for item in ITEMS:
            console = Console(rom)
            console.emu[INV_LETTER] = LETTER_DELIVERED           # the potion shop opens
            console.enter_cave(screens[destination])
            position = next(position for position in range(3)
                            if console.emu[CAVE_ITEM_IDS + position] != ITEM_INACTIVE)
            console.emu[CAVE_ITEM_IDS + position] = item
            console.take_ware(position)
            before = console.emu[FRAME_COUNTER]
            console.emu.run(SETTLE_FRAMES)
            case = (revision, music, destination.name, item.name)
            assert not console.emu.nes.has_crashed, case
            assert console.emu[FRAME_COUNTER] != before, case
            assert console.emu.mode == CAVE_MODE, case          # Link still in the cave, playing


@needs_base_rom
def test_lozft_writes_no_zora_claim() -> None:
    """Every byte lozft owns in banks 0-6 is clear of asm/rom_space.toml's claims (builders, slots,
    sites, reservations, placements) but LOZFT_NEIGHBOURS'."""
    from zora.rom.music.lozft import lozft_bytes
    _, mask = lozft_bytes(_music_assets().patch, remember_repo_base_rom())
    from tests.test_rom_space import rom_space as load_rom_space
    rom_space = load_rom_space()
    space = rom_space.table()
    placed = [area for row in rom_space.placements() for area in row.areas()]
    claimed = rom_space.claims(space, rom_space.builder_bytes(), placed)
    header, bank_size = 0x10, 0x4000
    met = {(owner, offset) for offset in range(header, header + 7 * bank_size) if mask[offset]
           for owner in claimed.get(offset, ()) if owner not in LOZFT_NEIGHBOURS}
    assert not met, sorted(f"{owner} 0x{offset:05X}" for owner, offset in met)[:20]
