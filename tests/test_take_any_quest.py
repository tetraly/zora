"""The take-any hearts count only the screens the seed's overworld quest shows (bug fix,
2026-10-17). The game always plays as the first quest: a screen whose quest field is the second
quest's or neither's never opens. A first-quest overworld keeps PRG0's second-quest Take Any
screens $06, $20 and $3A hidden, which the heart check and the logic model once counted, three
take-any hearts no game can take."""
from functools import cache

import pytest

from tests.emulator import CUR_LEVEL, GAME_MODE, GAME_SUBMODE, OBJ_TYPE, OBJ_X, OBJ_Y, ROOM_ID, Button, Emulator
from zora.flags.codec import decode, encode
from zora.flags.fields import OVERWORLD_QUEST, OverworldQuest
from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
from zora.generate.logic import logic_model, take_any_event
from zora.generate.pipeline import build, generate_rom, generate_world, plan
from zora.generate.steps.mixed_overworld_quest import SHOWN
from zora.generate.steps.randomize_magical_sword import reachable_take_any_hearts, take_any_heart_screens
from zora.model.enums import Destination, Item
from zora.model.game_world import GameWorld
from zora.rom.base_rom import verify_base_rom

SEEDS = range(1, 4)
QUESTS = (OverworldQuest.FIRST_QUEST, OverworldQuest.SECOND_QUEST, OverworldQuest.MIXED_FIRST_QUEST_VARIANT,
          OverworldQuest.MIXED_SECOND_QUEST_VARIANT)
SECOND_QUEST_TAKE_ANY_SCREENS = frozenset({0x06, 0x20, 0x3A})
FIRST_QUEST_TAKE_ANY_COUNT = 4                 # PRG0's first quest: four code-17 screens shown
EVERY_NEED = frozenset({Item.RAFT, Item.RECORDER, Item.LADDER, Item.POWER_BRACELET})

# the emulator check: screen $20's secret, a gravestone (tile object $65) pushed up
GRAVESTONE_SCREEN = 0x20
GRAVESTONE = 0x65
TILE_OBJECT_SLOT = 11
LEVEL_BLOCK_ATTRS_F = 0x6AFE                   # the loaded block's F bytes; bits 7-6 the quest field
QUEST_FIELD_CLEARED = 0x3F                     # field 0: the secret applies to both quests
IS_UPDATING_MODE = 0x11
UNDERGROUND_EXIT_TYPE = 0x5A
LEAVE_CAVE_MODE = 0x0A
PLAY_MODE = 0x05
CAVE_MODE = 0x0B
ONE_SQUARE = 0x10
PUSH_FRAMES = 150                              # push, then walk on into the stairs if they opened


@cache
def base() -> bytes:
    return verify_base_rom().read_bytes()


def flags_for(quest: OverworldQuest) -> str:
    return encode(decode(MVP_BASELINE_LEVEL_ENCODING_OFF).updated({OVERWORLD_QUEST.id: quest}))


@cache
def world(quest: OverworldQuest, seed: int) -> GameWorld:
    return generate_world(plan(flags_for(quest), seed), base())[0]


def take_any_screens(gw: GameWorld, shown: bool) -> set[int]:
    return {screen.screen_num for screen in gw.overworld.screens
            if screen.destination == Destination.TAKE_ANY and (screen.quest_visibility in SHOWN) == shown}


@pytest.mark.parametrize("quest", QUESTS, ids=lambda quest: quest.name)
@pytest.mark.parametrize("seed", SEEDS)
def test_only_shown_take_any_screens_count(quest: OverworldQuest, seed: int) -> None:
    gw = world(quest, seed)
    assert take_any_screens(gw, shown=False), "every overworld quest hides some code-17 screens"
    assert set(take_any_heart_screens(gw.overworld)) == take_any_screens(gw, shown=True)
    assert reachable_take_any_hearts(gw.overworld, EVERY_NEED) == len(take_any_screens(gw, shown=True))


@pytest.mark.parametrize("seed", SEEDS)
def test_a_first_quest_overworld_counts_its_four_take_any_caves(seed: int) -> None:
    gw = world(OverworldQuest.FIRST_QUEST, seed)
    assert take_any_screens(gw, shown=False) == SECOND_QUEST_TAKE_ANY_SCREENS
    assert len(take_any_heart_screens(gw.overworld)) == FIRST_QUEST_TAKE_ANY_COUNT


@pytest.mark.parametrize("quest", QUESTS, ids=lambda quest: quest.name)
def test_the_logic_model_counts_only_shown_take_any_caves(quest: OverworldQuest) -> None:
    model = logic_model(build(plan(flags_for(quest), 1), base()))
    assert set(model.take_any_events) == {take_any_event(screen)
                                          for screen in take_any_screens(world(quest, 1), shown=True)}
    assert not set(model.events) & {take_any_event(screen) for screen in take_any_screens(world(quest, 1), shown=False)}


def push_gravestone(rom: bytes, clear_quest_field: bool) -> int:
    """Stand below screen $20's gravestone and push it up; the game mode afterwards (the cave's
    when the push opened its stairs and Link walked in). Clearing the quest field in work RAM
    is the control: the same screen with a secret for both quests."""
    emu = Emulator(rom)
    emu.new_game()
    if clear_quest_field:
        emu[LEVEL_BLOCK_ATTRS_F + GRAVESTONE_SCREEN] &= QUEST_FIELD_CLEARED
    emu[ROOM_ID], emu[CUR_LEVEL], emu[UNDERGROUND_EXIT_TYPE] = GRAVESTONE_SCREEN, 0, 1
    emu[GAME_MODE], emu[GAME_SUBMODE], emu[IS_UPDATING_MODE] = LEAVE_CAVE_MODE, 0, 0
    emu.run_until(lambda: emu.mode == PLAY_MODE and emu[IS_UPDATING_MODE] == 1, limit=900)
    emu.run(10)
    assert emu[OBJ_TYPE + TILE_OBJECT_SLOT] == GRAVESTONE
    emu[OBJ_X] = emu[OBJ_X + TILE_OBJECT_SLOT]
    emu[OBJ_Y] = emu[OBJ_Y + TILE_OBJECT_SLOT] + ONE_SQUARE
    emu.run(PUSH_FRAMES, Button.UP)
    return emu.mode


def test_a_second_quest_take_any_never_opens_in_a_first_quest_game() -> None:
    rom = generate_rom(flags_for(OverworldQuest.FIRST_QUEST), 1, base()).rom
    assert GRAVESTONE_SCREEN in take_any_screens(world(OverworldQuest.FIRST_QUEST, 1), shown=False)
    assert push_gravestone(rom, clear_quest_field=False) == PLAY_MODE
    assert push_gravestone(rom, clear_quest_field=True) == CAVE_MODE
