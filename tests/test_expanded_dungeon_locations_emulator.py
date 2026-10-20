"""Expanded Dungeon Locations (Expanded Brackets) in the emulator, on a 1st Quest overworld:
second-quest entrances open in the first quest and lead to their dealt dungeons (2Q9's bomb wall,
2Q6's recorder on the graveyard), and stay shut where no dungeon was dealt; an unchosen 1Q5 draws
the second quest's fairy fountain, a chosen one the first quest's doorway.

Link is put on a screen through the leave-cave mode (as tests/test_assignment_emulator.py enters a
cave), which sets him down at the screen's cave exit. Seeds of tests/test_expanded_dungeon_locations'
Dungeons Only flags: seed 2 deals dungeon 5 to 2Q9 and dungeon 9 to 2Q6 and leaves 1Q5 unchosen;
seed 1 leaves 2Q9 unchosen and deals dungeon 6 to 1Q5; seed 3 leaves 2Q6 unchosen."""
import pytest

from tests.emulator import (
    CUR_LEVEL,
    GAME_MODE,
    GAME_SUBMODE,
    INV_BOMBS,
    INV_RECORDER,
    OBJ_TYPE,
    OBJ_X,
    OBJ_Y,
    RECORDER_SLOT,
    ROOM_ID,
    SELECTED_ITEM_SLOT,
    Button,
    Emulator,
    Mode,
)
from tests.test_expanded_dungeon_locations import BRACKETS, base, built, finished
from zora.flags.codec import decode, encode
from zora.flags.fields import OverworldQuest
from zora.generate.pipeline import generate_rom
from zora.generate.steps.expanded_dungeon_locations import SPOTS_BY_LABEL
from zora.rom.base_rom import BASE_ROM_PATH

pytestmark = pytest.mark.skipif(not BASE_ROM_PATH.exists(), reason="needs the base ROM")

IS_UPDATING_MODE = 0x11
UNDERGROUND_EXIT_TYPE = 0x5A
LEAVE_CAVE_MODE = 0x0A
ENTER_MODE = 0x10                        # walking into a cave or level mouth
OBJECT_SLOTS = range(0x14)
ROCK_WALL = 0x63                         # ObjType of a bombable rock wall tile object (UpdateRockWall)
BOMB_SLOT = 1                            # SelectedItemSlot of the bombs
FACE_FRAMES, ITEM_READ_FRAMES = 8, 5
BOMB_FRAMES = 150                        # placed, lit, exploded
RECORDER_FRAMES = 300
WALK_FRAMES = 300
TILE = 8
NAMETABLE, NAMETABLE_SIZE = 0x2000, 0x3C0
TILES_PER_ROW = 32
LINK_Y_ON_TILE_ROW = -3                  # Link's Y standing on a tile row: 8 * row - 3
PLAYFIELD_START, PLAYFIELD_SIZE = 0x2100, 0x2C0       # nametable rows 8-29, below the status bar
SEEDS = {"2Q9 and 2Q6 chosen, 1Q5 not": 2, "2Q9 unchosen, 1Q5 chosen": 1, "2Q6 unchosen": 3}


def on_screen(seed: int, screen: int, rom: bytes | None = None) -> Emulator:
    """A new file's Link set down on this screen."""
    emu = Emulator(rom if rom is not None else finished(seed, BRACKETS))
    emu.new_game()
    emu[ROOM_ID] = screen
    emu[CUR_LEVEL] = 0
    emu[UNDERGROUND_EXIT_TYPE] = 1
    emu[GAME_MODE], emu[GAME_SUBMODE], emu[IS_UPDATING_MODE] = LEAVE_CAVE_MODE, 0, 0
    emu.run_until(lambda: emu.mode == Mode.PLAY and emu[IS_UPDATING_MODE] == 1, limit=900)
    emu.run(10)
    return emu


def walk_in(emu: Emulator) -> int:
    """Walk up until the screen gives way; the level then loaded (0: none)."""
    for _ in range(WALK_FRAMES):
        if emu.mode != Mode.PLAY:
            break
        emu.run(1, Button.UP)
    else:
        return 0
    assert emu.mode == ENTER_MODE
    emu.run_until(lambda: emu.mode == Mode.PLAY, limit=900)
    return emu[CUR_LEVEL]


def dealt(seed: int, label: str) -> int | None:
    deal = built(seed, BRACKETS).result.expanded_deal
    assert deal is not None
    return next((dungeon for dungeon, spot in deal.dungeons.items() if spot.label == label), None)


@pytest.mark.parametrize("seed", [SEEDS["2Q9 and 2Q6 chosen, 1Q5 not"], SEEDS["2Q9 unchosen, 1Q5 chosen"]])
def test_2q9s_bomb_wall_opens_onto_its_dungeon_only_when_dealt_one(seed: int) -> None:
    """A bomb by 2Q9's rock wall opens it in the first quest (quest field 0 passes
    IsQuestSecretMismatch) and Link walks into the dealt dungeon; unchosen (field 3), it stays."""
    dungeon = dealt(seed, "2Q9")
    emu = on_screen(seed, SPOTS_BY_LABEL["2Q9"].screen)
    wall = next(slot for slot in OBJECT_SLOTS if emu[OBJ_TYPE + slot] == ROCK_WALL)
    emu[INV_BOMBS], emu[SELECTED_ITEM_SLOT] = 8, BOMB_SLOT
    emu[OBJ_X], emu[OBJ_Y] = emu[OBJ_X + wall], emu[OBJ_Y + wall] + 2 * TILE
    emu.run(FACE_FRAMES, Button.UP)
    emu.run(ITEM_READ_FRAMES)
    emu.press(Button.B, after=BOMB_FRAMES)
    assert (emu[OBJ_TYPE + wall] == 0) == (dungeon is not None)          # the wall's object is gone
    assert walk_in(emu) == (dungeon or 0)


@pytest.mark.parametrize("seed", [SEEDS["2Q9 and 2Q6 chosen, 1Q5 not"], SEEDS["2Q6 unchosen"]])
def test_the_recorder_opens_2q6_only_when_dealt_a_dungeon(seed: int) -> None:
    """On 2Q6's graveyard the recorder reveals stairs in the first quest (the second quest's reveal,
    branch $D0, with only 2Q6's entry live) and they lead to the dealt dungeon; unchosen, nothing."""
    dungeon = dealt(seed, "2Q6")
    emu = on_screen(seed, SPOTS_BY_LABEL["2Q6"].screen)
    before = emu.nametable(NAMETABLE, NAMETABLE_SIZE)
    emu[INV_RECORDER], emu[SELECTED_ITEM_SLOT] = 1, RECORDER_SLOT
    emu.run(FACE_FRAMES, Button.DOWN)
    emu.run(ITEM_READ_FRAMES)
    emu.press(Button.B, after=RECORDER_FRAMES)
    after = emu.nametable(NAMETABLE, NAMETABLE_SIZE)
    changed = [index for index in range(NAMETABLE_SIZE) if before[index] != after[index]]
    if dungeon is None:
        assert changed == []
        return
    row, column = divmod(changed[0], TILES_PER_ROW)            # the stairs' top-left tile
    emu[OBJ_X], emu[OBJ_Y] = column * TILE, row * TILE + LINK_Y_ON_TILE_ROW
    assert walk_in(emu) == dungeon


def playfield(seed: int, rom: bytes | None = None) -> bytes:
    emu = on_screen(seed, SPOTS_BY_LABEL["1Q5"].screen, rom)
    emu.run(30)
    return emu.nametable(PLAYFIELD_START, PLAYFIELD_SIZE)


def test_1q5_draws_the_fountain_unchosen_and_the_doorway_chosen() -> None:
    """Unchosen, 1Q5's screen ($0B) is drawn as the 2nd Quest overworld draws it, the fairy
    fountain; chosen, as the 1st Quest overworld draws it, the doorway."""
    unchosen, chosen = SEEDS["2Q9 and 2Q6 chosen, 1Q5 not"], SEEDS["2Q9 unchosen, 1Q5 chosen"]
    assert dealt(unchosen, "1Q5") is None and dealt(chosen, "1Q5") is not None
    second_quest = encode(decode(BRACKETS).updated(options={"C01": OverworldQuest.SECOND_QUEST}))
    fountain = playfield(unchosen, generate_rom(second_quest, unchosen, base()).rom)
    doorway = playfield(unchosen, generate_rom(BRACKETS, unchosen, base()).rom)
    assert fountain != doorway
    assert playfield(unchosen) == fountain
    assert playfield(chosen) == doorway
