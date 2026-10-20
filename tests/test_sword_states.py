"""Swords (C07; features-behavior.md FP-WOOD-01 to FP-WOOD-04, acceptance.md VA-REJ-22): Wood Sword
Only, No Wood Sword, Swordless and Random. The refusals of the sword ZORA flags with any value but
Normal; the walk's rules; the cave wares and code bytes per state; the hints' bomb-upgrade name; and
in the emulator: item $02 as a bomb upgrade (both store layouts, docs/deviations.md), the Book still
mapping with its routine extended, the Triforce of Power still triggering the ending (FP-FIX-04),
and the wand-only Ganon fight. Muffle Rug (C07 = Random) generates."""
import dataclasses
from functools import cache
from typing import Any

import pytest

from tests.emulator import (
    CUR_OPENED_DOORS,
    ITEMS,
    LAST_BOSS_DEFEATED,
    OBJ_STATE,
    OBJ_TYPE,
    OBJ_X,
    OBJ_Y,
    ROOM_ITEM_SLOT,
    SELECTED_ITEM_SLOT,
    TRIFORCE_FANFARE_ACTIVE,
    Button,
    Emulator,
)
from tests.needs import needs_base_rom
from tests.test_assignment_emulator import Console, floor_room, with_items
from tests.test_assignment_emulator import MONSTER_SLOTS
from tests.test_november_settings import OBJ_HP, _enter_room
from zora.flags import codec, zora_flags
from zora.flags.dependencies import resolve
from zora.flags.fields import ThreeState, WoodenSwordState
from zora.flags.form import metadata
from zora.flags.support import Support, support
from zora.generate.acceptance_check import WOOD_SWORD_FROM_START, LogicRules, logic_rules
from zora.generate.pipeline import Built, FlagsRefused, build, finish, plan
from zora.generate.rng import Rng
from zora.generate.steps.change_enemy_hp import GANON
from zora.generate.steps.hint_text import BOMB_UPGRADE_NAME, VANILLA_NAMES
from zora.model.enums import Item, RoomAction, WallType
from zora.rom.serialize.rom_file import serialize_to_rom
from zora.rom import sword_states as patches
from zora.rom.base_rom import remember_repo_base_rom
from zora.rom.game_config import GameConfig

DEFAULT_SETTINGS = codec.decode(metadata()["defaultFlags"])      # CP-5 (B09 and B49 on)
MUFFLE_RUG = "2487lt0moGMFLRug1ofQdxPuUBWnJVSsi7d202I"
S = WoodenSwordState
SEEDS = range(1, 4)
WOOD_SWORD_CAVE_WARES, MAGICAL_SWORD_CAVE_WARES = slice(0x18610, 0x18613), slice(0x18619, 0x1861C)
SWORD_FLAGS: dict[str, Any] = {"add_l4_sword": ThreeState.ON, "randomize_magical_sword": True, "shuffle_wood_sword": ThreeState.ON,
               "progressive_items": True}
# RAM (aldonunez Variables.inc)
INV_SWORD, INV_BOMBS, MAX_BOMBS, INV_WAND = ITEMS, 0x658, 0x67C, ITEMS + 8
BOOK_MAP_FLAG = 0x4E5                 # SetItemValueAndBookMap's STX for the Book (fp-book-01), cleared once used
BOOK_SLOT = 10
TAKE_FRAMES = 180
LINK_INVINCIBILITY_TIMER, INVINCIBLE = 0x4F0, 0xFF
WAND_ITEM_SLOT = 8                    # SelectedItemSlot of the wand
GANON_HOLD_FRAMES = 300               # Link is held while Ganon appears
FIGHT_FRAMES, PRESS_FRAMES = 90, (2, 40)
ABOVE_LINK = 0x10
WAND_DAMAGE, WOOD_SWORD_DAMAGE = 0x20, 0x10
PRG0_MAX_BOMBS = 8
PICKUP_FRAMES = 400


def flags(state: int, **toggles: int) -> str:
    return codec.encode(DEFAULT_SETTINGS.updated(options={"C07": state}, toggles=toggles))


# --- settings, refusals and rules (no ROM) ----------------------------------------------------------

@pytest.mark.parametrize("state", list(S))
def test_every_state_is_supported(state: S) -> None:
    assert support(DEFAULT_SETTINGS.updated(options={"C07": state}))["C07"] is Support.SUPPORTED


@pytest.mark.parametrize("state", [S.WOODEN_SWORD_ONLY, S.NO_WOODEN_SWORD, S.SWORDLESS, S.RANDOM])
@pytest.mark.parametrize("name", list(SWORD_FLAGS))
def test_the_sword_flags_are_refused(state: S, name: str) -> None:
    """Owner decision 2026-10-17: each refused with its own message, at both settings."""
    zora = dataclasses.replace(zora_flags.ZoraFlags(), **{name: SWORD_FLAGS[name]})
    found = zora_flags.sword_state_conflicts(zora, DEFAULT_SETTINGS.updated(options={"C07": state}))
    assert [names for _message, names in found] == [(name, "C07")]
    assert "Swords" in found[0][0] and zora_flags.SWORD_FLAG_LABELS[name] in found[0][0]
    assert not zora_flags.sword_state_conflicts(zora, DEFAULT_SETTINGS)


def test_a_refused_pair_does_not_plan() -> None:
    zora = zora_flags.encode(zora_flags.ZoraFlags(progressive_items=True))
    with pytest.raises(FlagsRefused, match="Progressive Items cannot be used with Swords"):
        plan(flags(S.SWORDLESS), 1, zora)


def test_b25_is_forced_on_under_swordless() -> None:
    """FL-DEP-04 (FP-WOOD-04): a possible B25 is on under Swordless, also through Random."""
    swordless = DEFAULT_SETTINGS.updated(options={"C07": S.SWORDLESS}, toggles={"B25": ThreeState.POSSIBLE})
    assert all(resolve(swordless, Rng(seed)).toggle("B25") is ThreeState.ON for seed in range(1, 21))


@pytest.mark.parametrize("state", [S.NORMAL, S.WOODEN_SWORD_ONLY, S.NO_WOODEN_SWORD, S.SWORDLESS])
def test_the_walk_rules(state: S) -> None:
    """VA-REJ-22: the wooden sword from the start under Normal and Wood Sword Only, in the target but
    under Swordless; Swordless with B25 off adds the wand to level 9."""
    rules: LogicRules = logic_rules(False, False, wooden_sword_state=state)
    assert rules.wood_sword_from_start == (state in WOOD_SWORD_FROM_START)
    assert rules.wood_sword_in_target == (state is not S.SWORDLESS)
    assert (Item.WAND in rules.level_9_entry_needs) == (state is S.SWORDLESS)
    with_b25 = logic_rules(False, False, wooden_sword_state=state, important_items_in_level_9=True)
    assert Item.WAND not in with_b25.level_9_entry_needs


def test_item_02s_hint_name() -> None:
    names = dataclasses.replace(VANILLA_NAMES, bomb_upgrade=True)
    assert names.label(Item.WHITE_SWORD) == BOMB_UPGRADE_NAME and names.phrase(Item.WHITE_SWORD) == "A BOMB UPGRADE"
    assert names.phrase(Item.MAGICAL_SWORD) == VANILLA_NAMES.phrase(Item.MAGICAL_SWORD)


# --- seeds ------------------------------------------------------------------------------------------

@cache
def _built(flag_string: str, seed: int) -> Built:
    return build(plan(flag_string, seed), remember_repo_base_rom())


@cache
def _rom(flag_string: str, seed: int) -> bytes:
    return finish(_built(flag_string, seed), remember_repo_base_rom())


@needs_base_rom
@pytest.mark.parametrize(("state", "b09", "wood_cave", "magical_cave"), [
    (S.NORMAL, 1, "06017f", "7f037f"),
    (S.WOODEN_SWORD_ONLY, 1, "06017f", "7f027f"),
    (S.NO_WOODEN_SWORD, 1, "063f7f", "7f037f"),
    (S.SWORDLESS, 1, "06067f", "7f027f"),               # Extra Candles' candle in ware 0 too
    (S.SWORDLESS, 0, "3f067f", "7f027f"),
])
def test_the_cave_wares(state: S, b09: int, wood_cave: str, magical_cave: str) -> None:
    rom = _rom(flags(state, B09=b09), 1)
    assert (rom[WOOD_SWORD_CAVE_WARES].hex(), rom[MAGICAL_SWORD_CAVE_WARES].hex()) == (wood_cave, magical_cave)


@needs_base_rom
@pytest.mark.parametrize("state", [S.NORMAL, S.WOODEN_SWORD_ONLY, S.NO_WOODEN_SWORD, S.SWORDLESS])
def test_the_code_bytes(state: S) -> None:
    rom, base = _rom(flags(state), 1), remember_repo_base_rom()
    upgrade, wand = state in (S.WOODEN_SWORD_ONLY, S.SWORDLESS), state is S.SWORDLESS
    assert rom[patches.ITEM_02_DESCRIPTOR] == (patches.BOMB_UPGRADE_DESCRIPTOR if upgrade
                                               else patches.ITEM_02_DESCRIPTOR_PRG0)
    tail = rom[patches.BOMB_COUNT_TAIL:patches.BOMB_COUNT_TAIL + len(patches.BOMB_COUNT_TAIL_BYTES)]
    assert (tail == patches.BOMB_COUNT_TAIL_BYTES) == upgrade
    ganon = rom[patches.GANON_SWORD_TEST:patches.GANON_SWORD_TEST + len(patches.GANON_WAND_TEST)]
    assert (ganon == patches.GANON_WAND_TEST) == wand
    assert rom[patches.GANON_MASK_OPERAND] == (patches.GANON_MASK_WAND if wand else patches.GANON_MASK_PRG0)
    if not upgrade:      # every site keeps PRG0's bytes but the code patches' own
        assert rom[patches.PATTERN_TARGET:patches.PATTERN_TARGET + 32] == base[patches.PATTERN_TARGET:patches.PATTERN_TARGET + 32]


@needs_base_rom
@pytest.mark.parametrize("state", [S.WOODEN_SWORD_ONLY, S.NO_WOODEN_SWORD, S.SWORDLESS, S.RANDOM])
def test_each_state_generates(state: S) -> None:
    for seed in SEEDS:
        assert _rom(flags(state), seed)


@needs_base_rom
def test_swordless_seeds_pass_e6() -> None:
    """VA-REJ-22's E6: in an accepted Swordless seed the last bomb shop has a plain front door."""
    from zora.generate.steps.shuffle_shop_items import bomb_shop_door_failure
    for seed in SEEDS:
        built = _built(flags(S.SWORDLESS), seed)
        assert built.result.overworld is not None
        assert not bomb_shop_door_failure(built.world.overworld, built.result.overworld)


@needs_base_rom
def test_muffle_rug_generates() -> None:
    from zora.rom import level_encoding
    if not level_encoding.is_available():
        pytest.skip("needs the private level encoder")
    for seed in SEEDS:
        assert _rom(MUFFLE_RUG, seed)


# --- the emulator -----------------------------------------------------------------------------------

def _take_from_the_floor(state: S, item: Item, b49: int) -> tuple[Emulator, bool]:
    """Item on a room's floor of a seed under the state, taken in play; and whether the Book's
    status-bar map trigger (fp-book-01's STX) was set on some frame of the pickup."""
    built = _built(flags(state, B49=b49), 1)
    place = floor_room(built)
    console = Console(finish(built, remember_repo_base_rom(), with_items(built, {place.name: item})))
    assert place.level is not None and place.room_num is not None
    console.enter_room(place.level, place.room_num)
    console.clear_monsters()
    emu = console.emu
    emu[OBJ_X], emu[OBJ_Y] = emu[OBJ_X + ROOM_ITEM_SLOT], emu[OBJ_Y + ROOM_ITEM_SLOT]
    triggered = False
    for _ in range(TAKE_FRAMES):
        emu.run(1)
        triggered |= emu[BOOK_MAP_FLAG] != 0
    return emu, triggered


@needs_base_rom
@pytest.mark.parametrize("b49", [1, 0])
@pytest.mark.parametrize("state", [S.WOODEN_SWORD_ONLY, S.SWORDLESS, S.NORMAL])
def test_item_02_in_play(state: S, b49: int) -> None:
    """FP-WOOD-02: item $02 adds 2 to MaxBombs and fills the bomb count, the sword slot untouched,
    in either store layout; under Normal it is the white sword."""
    emu, _ = _take_from_the_floor(state, Item.WHITE_SWORD, b49)
    if state is S.NORMAL:
        assert (emu[INV_SWORD], emu[MAX_BOMBS]) == (2, PRG0_MAX_BOMBS)
    else:
        assert (emu[INV_SWORD], emu[MAX_BOMBS], emu[INV_BOMBS]) == (0, PRG0_MAX_BOMBS + 2, PRG0_MAX_BOMBS + 2)


@needs_base_rom
def test_the_book_still_maps_with_its_routine_extended() -> None:
    """With B49 on, fp-book-01's routine runs on into the bomb-count tail: the Book still sets its
    status-bar map trigger and is held, as under Normal."""
    for state in (S.NORMAL, S.WOODEN_SWORD_ONLY):
        emu, triggered = _take_from_the_floor(state, Item.BOOK, 1)
        assert triggered and emu[ITEMS + BOOK_SLOT] == 1, state


@needs_base_rom
@pytest.mark.parametrize("book_is_an_atlas", [True, False])
def test_the_triforce_of_power_still_triggers_the_ending(book_is_an_atlas: bool) -> None:
    """FP-FIX-04's pickup with the bomb upgrade's patches: LastBossDefeated 2 and slot 0's type 1
    at once, as without them (docs/deviations.md: the spec's 0x1EDA4 would lose both)."""
    from tests import test_feature_patches as fixes
    config = GameConfig(features_b10=True, book_is_an_atlas=book_is_an_atlas, bomb_upgrade_item=True)
    world = fixes._prg0_world()
    room = next(level for level in world.levels if level.level_num == 1).block.room(fixes.LEVEL_1_START_ROOM)
    room.item = Item.TRIFORCE_OF_POWER
    room.item_position = fixes.ITEM_SPOT_ON_LINKS_PATH
    room.room_action = RoomAction.LAST_BOSS
    room.walls = dataclasses.replace(room.walls, east=WallType.SHUTTER_DOOR)
    emu = Emulator(serialize_to_rom(world, fixes.vanilla(), config=config))
    emu.new_game()
    emu.walk_into_level_1()
    emu[OBJ_STATE + ROOM_ITEM_SLOT] = 0      # Ganon_ActivateRoomItem
    result: dict[str, int] = {}
    for frame in range(PICKUP_FRAMES):
        emu.run(1, Button(0) if "taken" in result else Button.UP)
        if "taken" not in result and emu[TRIFORCE_FANFARE_ACTIVE]:
            result.update(taken=frame, last_boss=emu[LAST_BOSS_DEFEATED], obj_type_0=emu[OBJ_TYPE])
        if "opened" not in result and emu[CUR_OPENED_DOORS] & fixes.EAST_DOOR:
            result["opened"] = frame
    assert (result["last_boss"], result["obj_type_0"]) == (2, 1)
    assert result["opened"] - result["taken"] < fixes.FANFARE_HALT_FRAMES // 8


def _ganon_damage(state: S, button: Button) -> int:
    """In Ganon's room once Link may move, Ganon held above him (Link invincible), two strokes of
    the button (B: the wand, selected; A: the wooden sword): the hit points Ganon lost."""
    built = _built(codec.encode(DEFAULT_SETTINGS.updated(options={"C07": state, "C10": 0})), 1)
    emu = Emulator(finish(built, remember_repo_base_rom()))
    emu.new_game()
    _enter_room(emu, built.world.levels[8].level_num, built.world.levels[8].boss_room)
    emu.run(GANON_HOLD_FRAMES)
    slot = next(slot for slot in MONSTER_SLOTS if emu[OBJ_TYPE + slot] == GANON)
    emu[INV_SWORD], emu[INV_WAND], emu[SELECTED_ITEM_SLOT] = 1, 1, WAND_ITEM_SLOT
    emu.run(10, Button.UP)
    x, y = emu[OBJ_X], emu[OBJ_Y]
    start = lowest = emu[OBJ_HP + slot]
    for frame in range(FIGHT_FRAMES):
        if frame in PRESS_FRAMES:
            emu.press(button, after=0)
        emu[OBJ_X + slot], emu[OBJ_Y + slot] = x, y - ABOVE_LINK
        emu[LINK_INVINCIBILITY_TIMER] = INVINCIBLE
        emu.run(1)
        lowest = min(lowest, emu[OBJ_HP + slot])
    return start - lowest


@needs_base_rom
def test_the_wand_only_ganon_fight() -> None:
    """FP-WOOD-03: under Swordless the wand's stab harms Ganon ($20) and the sword does not; under
    Normal the sword does ($10, the wooden sword) and the wand does not."""
    assert _ganon_damage(S.SWORDLESS, Button.B) == WAND_DAMAGE
    assert _ganon_damage(S.SWORDLESS, Button.A) == 0
    assert _ganon_damage(S.NORMAL, Button.A) == WOOD_SWORD_DAMAGE
    assert _ganon_damage(S.NORMAL, Button.B) == 0
