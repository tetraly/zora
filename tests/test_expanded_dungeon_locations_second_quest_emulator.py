"""Expanded Dungeon Locations (Expanded Brackets) in the emulator, on a 2nd Quest overworld (phase
2): first-quest entrances open on it and lead to their dealt dungeons (1Q9's bomb wall, 1Q7's
recorder lake, 1Q5's doorway), and stay shut where no dungeon was dealt (1Q9, 1Q7 and 2Q3's pond,
whose recorder entries are off); an unchosen 1Q5 draws the fairy fountain.

Seeds of tests/test_expanded_dungeon_locations_second_quest's Dungeons Only flags: seed 0 deals
dungeon 7 to 1Q9 and dungeon 1 to 2Q3's pond and leaves 1Q5 unchosen; seed 2 deals dungeon 9 to 1Q7
and leaves 1Q9 and 2Q3 unchosen; seed 3 deals dungeon 3 to 1Q5; seed 5 leaves 1Q7 unchosen."""
import pytest

from tests.emulator import (
    INV_BOMBS,
    INV_RECORDER,
    OBJ_TYPE,
    OBJ_X,
    OBJ_Y,
    RECORDER_SLOT,
    SELECTED_ITEM_SLOT,
    Button,
    Emulator,
)
from tests.test_expanded_dungeon_locations import base
from tests.test_expanded_dungeon_locations_emulator import (
    BOMB_FRAMES,
    BOMB_SLOT,
    FACE_FRAMES,
    ITEM_READ_FRAMES,
    LINK_Y_ON_TILE_ROW,
    NAMETABLE,
    NAMETABLE_SIZE,
    OBJECT_SLOTS,
    PLAYFIELD_SIZE,
    PLAYFIELD_START,
    RECORDER_FRAMES,
    ROCK_WALL,
    TILE,
    TILES_PER_ROW,
    on_screen,
    walk_in,
)
from tests.test_expanded_dungeon_locations_second_quest import BRACKETS, built, finished
from zora.flags.codec import decode, encode
from zora.flags.fields import OverworldQuest
from zora.generate.pipeline import generate_rom
from zora.generate.steps.expanded_dungeon_locations import SECOND_QUEST
from zora.rom.base_rom import BASE_ROM_PATH

pytestmark = pytest.mark.skipif(not BASE_ROM_PATH.exists(), reason="needs the base ROM")

SPOT = SECOND_QUEST.by_label
SEEDS = {"1Q9 and 2Q3 chosen, 1Q5 not": 0, "1Q7 chosen, 1Q9 and 2Q3 not": 2, "1Q5 chosen": 3, "1Q7 unchosen": 5}
SETTLE_FRAMES = 30
APPROACH_TILES = 2
STEP_OFF_FRAMES = 20
STAIRS_TILES = 4                         # the revealed stairs, 2 x 2 tiles: all the recorder changes


def dealt(seed: int, label: str) -> int | None:
    deal = built(seed, BRACKETS).result.expanded_deal
    assert deal is not None
    return next((dungeon for dungeon, spot in deal.dungeons.items() if spot.label == label), None)


@pytest.mark.parametrize("seed", [SEEDS["1Q9 and 2Q3 chosen, 1Q5 not"], SEEDS["1Q7 chosen, 1Q9 and 2Q3 not"]])
def test_1q9s_bomb_wall_opens_onto_its_dungeon_only_when_dealt_one(seed: int) -> None:
    """A bomb by 1Q9's rock wall opens it on the 2nd Quest overworld (quest field 0) and Link walks
    into the dealt dungeon; unchosen (field 3, as 2nd Quest hides it), it stays."""
    dungeon = dealt(seed, "1Q9")
    emu = on_screen(seed, SPOT["1Q9"].screen, finished(seed, BRACKETS))
    wall = next(slot for slot in OBJECT_SLOTS if emu[OBJ_TYPE + slot] == ROCK_WALL)
    emu[INV_BOMBS], emu[SELECTED_ITEM_SLOT] = 8, BOMB_SLOT
    emu[OBJ_X], emu[OBJ_Y] = emu[OBJ_X + wall], emu[OBJ_Y + wall] + 2 * TILE
    emu.run(FACE_FRAMES, Button.UP)
    emu.run(ITEM_READ_FRAMES)
    emu.press(Button.B, after=BOMB_FRAMES)
    assert (emu[OBJ_TYPE + wall] == 0) == (dungeon is not None)          # the wall's object is gone
    assert walk_in(emu) == (dungeon or 0)


def played_recorder(seed: int, label: str) -> tuple[Emulator, list[int]]:
    """The recorder played on a spot's screen: the emulator and the nametable tiles it changed."""
    emu = on_screen(seed, SPOT[label].screen, finished(seed, BRACKETS))
    before = emu.nametable(NAMETABLE, NAMETABLE_SIZE)
    emu[INV_RECORDER], emu[SELECTED_ITEM_SLOT] = 1, RECORDER_SLOT
    emu.run(FACE_FRAMES, Button.DOWN)
    emu.run(ITEM_READ_FRAMES)
    emu.press(Button.B, after=RECORDER_FRAMES)
    after = emu.nametable(NAMETABLE, NAMETABLE_SIZE)
    return emu, [index for index in range(NAMETABLE_SIZE) if before[index] != after[index]]


@pytest.mark.parametrize(("label", "seed"), [
    ("1Q7", SEEDS["1Q7 chosen, 1Q9 and 2Q3 not"]), ("1Q7", SEEDS["1Q7 unchosen"]),
    ("1Q2/2Q3", SEEDS["1Q9 and 2Q3 chosen, 1Q5 not"]), ("1Q2/2Q3", SEEDS["1Q7 chosen, 1Q9 and 2Q3 not"]),
], ids=["1q7-chosen", "1q7-unchosen", "2q3-chosen", "2q3-unchosen"])
def test_the_recorder_opens_a_lake_only_when_dealt_a_dungeon(label: str, seed: int) -> None:
    """On 1Q7's lake the recorder's entry 0 reveals the stairs on the 2nd Quest overworld (entry 0
    works whatever the reversed branch), and on 2Q3's pond entry 6; each leads to the dealt
    dungeon. Unchosen, the entry is off and nothing changes."""
    dungeon = dealt(seed, label)
    emu, changed = played_recorder(seed, label)
    if dungeon is None:
        assert changed == []
        return
    assert len(changed) == STAIRS_TILES
    row, column = divmod(changed[0], TILES_PER_ROW)            # the stairs' top-left tile
    # Two tiles below the stairs: Link enters them by walking on, not by being set down there
    emu[OBJ_X], emu[OBJ_Y] = column * TILE, (row + APPROACH_TILES) * TILE + LINK_Y_ON_TILE_ROW
    assert walk_in(emu) == dungeon


def playfield(seed: int, rom: bytes) -> bytes:
    emu = on_screen(seed, SPOT["1Q5"].screen, rom)
    emu.run(SETTLE_FRAMES)
    return emu.nametable(PLAYFIELD_START, PLAYFIELD_SIZE)


def test_1q5_draws_its_doorway_chosen_and_the_fountain_unchosen() -> None:
    """Chosen, 1Q5's screen ($0B) is drawn as the 1st Quest overworld draws it, and its doorway
    leads to the dealt dungeon; unchosen, as the 2nd Quest overworld draws it, the fairy fountain."""
    chosen, unchosen = SEEDS["1Q5 chosen"], SEEDS["1Q9 and 2Q3 chosen, 1Q5 not"]
    assert dealt(chosen, "1Q5") is not None and dealt(unchosen, "1Q5") is None
    first_quest = encode(decode(BRACKETS).updated(options={"C01": OverworldQuest.FIRST_QUEST}))
    doorway = playfield(unchosen, generate_rom(first_quest, unchosen, base()).rom)
    fountain = playfield(unchosen, generate_rom(BRACKETS, unchosen, base()).rom)
    assert fountain != doorway
    assert playfield(unchosen, finished(unchosen, BRACKETS)) == fountain
    assert playfield(chosen, finished(chosen, BRACKETS)) == doorway
    emu = on_screen(chosen, SPOT["1Q5"].screen, finished(chosen, BRACKETS))
    emu.run(STEP_OFF_FRAMES, Button.DOWN)          # off the cave exit, which re-enters only once left
    assert walk_in(emu) == dealt(chosen, "1Q5")
