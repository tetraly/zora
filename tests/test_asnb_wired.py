"""All Swords No Boards wired into ZORA (docs/design/asnb.md sections 1, 2, 4, 5 and 7; C2's
patches from asm/asnb/, written by zora/rom/owner_patches.py):
  - flags: Add L4 Sword's three-way control over two encoded fields and Level 9 Entrance, their
    spellings, no random option, every refusal of section 2, and the ASNB preset;
  - the ROM: the patch data is C2's build, verbatim; take-l4's copies and sword-cap's three copies are
    identical, sword-cap's switch is $01, level-9-gate and the refusal text are written with
    the entrance, l4-sword-take is retired, no two patches write one byte and z1rr-coop's
    reserved bytes are untouched;
  - the generator: level 2 has exactly one item cellar with Add L4 Sword = Level 2 and none
    without; its sword joins the shuffle (tracked with the level-4-sword entrance), the places
    and Archipelago's locations take it; the logic needs four swords for level 9 (ZORA's closure
    and Archipelago's model); hints call it a sword upgrade;
  - a batch over the ASNB preset: every seed passes the acceptance walk on its finished ROM and
    the finished-ROM checks (more seeds marked slow);
  - in the emulator, an ASNB ROM: the seed's four swords taken where they lie open level 9 with
    no triforce pieces, and three of them do not."""
from __future__ import annotations

from dataclasses import replace
from functools import cache
from pathlib import Path

import pytest

from tests.emulator import CUR_LEVEL, CUR_OPENED_DOORS, INV_TRIFORCE, ITEMS, OBJ_TYPE, ROOM_ID, SHUTTER_TRIGGER, Mode
from tests.owner_flags_replay import replay
from tests.test_assignment_emulator import ENTER_ROOM_MODE, Console
from tests.test_coop_reserved import assert_reserved_bytes_are_prg0
from zora.flags import zora_flags, zora_form
from zora.flags.codec import decode, encode
from zora.flags.fields import DungeonLayoutSource, ThreeState, WoodenSwordState
from zora.flags.form import presets
from zora.flags.presets import ASNB_FLAGS, ASNB_ZORA_FLAGS, MVP_BASELINE_LEVEL_ENCODING_OFF
from zora.flags.zora_flags import L4Sword, ZoraFlags
from zora.generate.acceptance_check import LEVEL9_ENTRY, AcceptanceCheck
from zora.generate.finish import FOREIGN, Foreign
from zora.generate.logic import SWORD, CountTerm, logic_model, rule_of, sweep
from zora.generate.pipeline import Built, FlagsRefused, build, extra_options, generate_rom, plan
from zora.generate.places import PlaceKind, major_pool, read_item
from zora.generate.steps.extra_pool_items import item_cellars, with_tracked
from zora.generate.steps.hint_text import ItemNames
from zora.model.enums import Destination, Item
from zora.model.game_world import GameWorld
from zora.rom.asnb_patch_data import PATCHES as ASNB_PATCHES
from zora.rom.asnb_patch_data import RESOLVE_COPIES, SYMBOLS, TAKE_COPIES
from zora.rom.base_rom import BASE_ROM_PATH, piece_length, remember_repo_base_rom
from zora.rom.flags2_patch_data import PATCHES as FLAGS2_PATCHES
from zora.rom.layout import REFUSAL_TEXT_ADDRESS
from zora.rom.owner_patches import LEVEL_9_ENTRANCE, PATCHES_BY_FLAG, owner_patch_writes
from zora.rom.parse.rom_file import parse_rom
from zora_measure.checks import finished_rom_checks, run_checks

pytestmark = pytest.mark.skipif(not BASE_ROM_PATH.exists(), reason="PRG0 base ROM not found")

REPO = Path(__file__).resolve().parent.parent
ON, OFF, MAYBE = ThreeState.ON, ThreeState.OFF, ThreeState.POSSIBLE
WITHOUT_CANDLES = encode(decode(MVP_BASELINE_LEVEL_ENCODING_OFF).updated(toggles={"B09": OFF}))
LEVEL_2 = ZoraFlags(progressive_items=True, add_l4_sword=ON, l4_sword_in_level_2=True)
ASNB = replace(LEVEL_2, level_9_entrance_sword=True)
LEVEL_9 = ZoraFlags(progressive_items=True, add_l4_sword=ON)
SEEDS = (1, 2, 3, 4)
BATCH_CHUNKS = range(5)              # 50 seeds (owner, 2026-10-08: the QA sweep covers scale)
BATCH_CHUNK_SEEDS = 10
SWORD_SLOT, SWORD_LEVEL_4 = 0x00, 4
GATE_FRAMES = 120
LEVEL_9_ENTRANCE_PERSON = 0x4B       # the man at level 9's entrance (object type)
MONSTER_SLOTS = range(1, 0x0C)
LINK_INVINCIBILITY_TIMER, INVINCIBLE = 0x4F0, 0xFF
ITEM_CAVE_WARE = 1


def z1r_with(**options: int) -> str:
    return encode(decode(WITHOUT_CANDLES).updated(options=options))


@cache
def base() -> bytes:
    return remember_repo_base_rom()


@cache
def built(zora: ZoraFlags, seed: int) -> Built:
    return build(plan(WITHOUT_CANDLES, seed, zora_flags.encode(zora)), base())


@cache
def asnb_rom(seed: int) -> bytes:
    return generate_rom(ASNB_FLAGS, seed, base(), zora_flag_string=ASNB_ZORA_FLAGS).rom


# --- flags (section 1) -------------------------------------------------------------------------

@pytest.mark.parametrize(("control", "entrance", "expected"), [
    (0, 0, ZoraFlags()), (1, 0, LEVEL_2), (1, 1, ASNB), (2, 0, LEVEL_9),
])
def test_the_three_way_control_round_trips_through_two_fields(control: int, entrance: int, expected: ZoraFlags) -> None:
    values = {name: zora_form.control_value(ZoraFlags(progressive_items=True), name) for name in zora_form.FIELD_NAMES}
    values |= {"progressive_items": int(expected.progressive_items), zora_form.L4_SWORD_FIELD: control,
               zora_form.LEVEL_9_ENTRANCE_FIELD: entrance}
    string = zora_form.zora_flags_from_values(values)
    assert zora_flags.decode(string) == expected
    state = zora_form.zora_state(string, None)
    assert state["values"][zora_form.L4_SWORD_FIELD] == control
    assert state["values"][zora_form.LEVEL_9_ENTRANCE_FIELD] == entrance


def test_level_9_keeps_the_released_spelling_and_level_2_is_version_4() -> None:
    assert zora_flags.encode(LEVEL_9).startswith("3.")
    assert zora_flags.encode(LEVEL_2).startswith("4.") and zora_flags.encode(ASNB) == ASNB_ZORA_FLAGS
    assert zora_flags.decode(zora_flags.encode(ASNB)).l4_sword is L4Sword.LEVEL_2
    assert zora_flags.encode(ZoraFlags()) == ""


def test_neither_control_offers_a_random_option() -> None:
    """The page offers no "?" for either; a released string's "?" still works."""
    fields = {field["name"]: field for field in zora_form.FIELDS}
    assert [value["label"] for value in fields["add_l4_sword"]["values"]] == ["Off", "Level 2", "Level 9"]
    assert [value["label"] for value in fields["level_9_entrance_sword"]["values"]] == \
        ["Triforce pieces", "Level 4 sword"]
    assert all(field["kind"] == "option" for name, field in fields.items()
               if name in ("add_l4_sword", "level_9_entrance_sword"))
    # a released string's "?" keeps beta 1's meaning, Off or Level 9 (owner ruling, 2026-10-08);
    # with Level 2 or the level-4-sword entrance it is refused
    released = ZoraFlags(progressive_items=True, add_l4_sword=MAYBE)
    assert zora_flags.validate(released, decode(WITHOUT_CANDLES)) == []
    assert zora_flags.validate(replace(released, l4_sword_in_level_2=True, level_9_entrance_sword=True),
                               decode(WITHOUT_CANDLES)) == [zora_flags.L4_SWORD_RANDOM_WITH_ASNB]


# --- refusals (section 2) ----------------------------------------------------------------------

def refusals(zora: ZoraFlags, z1r: str = WITHOUT_CANDLES) -> list[str]:
    return zora_flags.validate(zora, decode(z1r))


def test_the_entrance_needs_level_2() -> None:
    off = replace(ASNB, add_l4_sword=OFF, l4_sword_in_level_2=False)
    for l4 in (off, replace(LEVEL_9, level_9_entrance_sword=True)):
        assert zora_flags.ENTRANCE_NEEDS_LEVEL_2 in refusals(l4)
    assert refusals(ASNB) == []


def test_add_l4_sword_needs_progressive_items_refused_not_turned_off() -> None:
    for l4 in (LEVEL_2, LEVEL_9):
        without = replace(l4, progressive_items=False)
        assert refusals(without) == [zora_flags.L4_SWORD_CONFLICT]
        with pytest.raises(FlagsRefused, match="needs Progressive Items"):
            plan(WITHOUT_CANDLES, 1, zora_flags.encode(without))


@pytest.mark.parametrize("layout", [source for source in DungeonLayoutSource
                                    if source != DungeonLayoutSource.GENERATED_SHAPES])
def test_level_2_needs_generated_shapes(layout: DungeonLayoutSource) -> None:
    assert zora_flags.LEVEL_2_NEEDS_SHAPES in refusals(LEVEL_2, z1r_with(C02=int(layout)))
    assert zora_flags.LEVEL_2_NEEDS_SHAPES not in refusals(LEVEL_9, z1r_with(C02=int(layout)))


@pytest.mark.parametrize("state", [state for state in WoodenSwordState if state != WoodenSwordState.NORMAL])
def test_the_entrance_needs_the_normal_wooden_sword(state: WoodenSwordState) -> None:
    assert refusals(ASNB, z1r_with(C07=int(state))) == [zora_flags.ENTRANCE_NEEDS_NORMAL_SWORD]
    assert refusals(LEVEL_2, z1r_with(C07=int(state))) == []


def test_progressive_items_still_refuses_extra_candles() -> None:
    assert refusals(ASNB, MVP_BASELINE_LEVEL_ENCODING_OFF) == [zora_flags.EXTRA_CANDLES_CONFLICT]


def test_the_level_2_field_without_add_l4_sword_is_refused() -> None:
    assert refusals(replace(LEVEL_2, add_l4_sword=OFF)) == [zora_flags.LEVEL_2_WITHOUT_L4_SWORD]


def test_the_asnb_preset() -> None:
    entry = next(preset for preset in presets() if preset["name"] == "All Swords No Boards")
    assert entry["available"] and entry["zoraFlags"] == ASNB_ZORA_FLAGS
    settings = decode(ASNB_FLAGS)
    assert settings.option("C02") == DungeonLayoutSource.GENERATED_SHAPES
    assert settings.option("C07") == WoodenSwordState.NORMAL and settings.toggle("B09") is OFF
    assert zora_flags.decode(ASNB_ZORA_FLAGS) == ASNB
    assert encode(decode(MVP_BASELINE_LEVEL_ENCODING_OFF).updated(toggles={"B09": OFF})) == ASNB_FLAGS


# --- the ROM -----------------------------------------------------------------------------------

def written(pieces: tuple[tuple[int, object], ...] | list[tuple[int, bytes]]) -> set[int]:
    return {offset + index for offset, piece in pieces for index in range(piece_length(piece))}  # type: ignore[arg-type]


def test_the_patch_data_is_c2s_build_verbatim() -> None:
    """zora/rom/asnb_patch_data.py is a verbatim copy of asm/asnb/asnb_data.py."""
    source = REPO / "asm" / "asnb" / "asnb_data.py"
    if not source.exists():
        pytest.skip("asm/ is not in this tree")
    assert (REPO / "zora" / "rom" / "asnb_patch_data.py").read_bytes() == source.read_bytes()


@pytest.mark.parametrize("seed", SEEDS[:2])
def test_an_asnb_rom_holds_the_patches(seed: int) -> None:
    rom = asnb_rom(seed)
    copies = {rom[start:end] for start, end in TAKE_COPIES.values()}
    assert len(copies) == 1 and len(TAKE_COPIES) == 7
    assert len({rom[start:end] for start, end in RESOLVE_COPIES.values()}) == 1
    assert {rom[offset] for offset in SYMBOLS.values()} == {0x01}
    for offset, data in owner_patch_writes(["add_l4_sword"], level_9_entrance_sword=True):
        assert rom[offset:offset + len(data)] == data, hex(offset)
    assert parse_rom(rom).level9_refusal_text.replace("~", "").split("\n") == \
        ["ONES WHO DOES NOT HAVE", "FOUR SWORD UPGRADES", "CAN'T GO IN."]
    assert all(len(line.strip("~")) <= 24 for line in parse_rom(rom).level9_refusal_text.split("\n"))
    assert_reserved_bytes_are_prg0(rom, f"ASNB seed {seed}")


def test_the_gate_is_written_only_with_the_entrance() -> None:
    gate = written(ASNB_PATCHES["level-9-gate"])
    level_2 = generate_rom(WITHOUT_CANDLES, 1, base(), zora_flag_string=zora_flags.encode(LEVEL_2)).rom
    assert all(level_2[offset] == base()[offset] for offset in gate)
    assert parse_rom(level_2).level9_refusal_text != parse_rom(asnb_rom(1)).level9_refusal_text
    assert REFUSAL_TEXT_ADDRESS not in gate


def test_l4_sword_take_is_retired() -> None:
    """Add L4 Sword = Level 9 (today's setting) writes take-l4 and sword-cap; l4-sword-take's bank-7
    stub, bank-1 routine and TryTakeItem hook hold PRG0's bytes again."""
    rom = generate_rom(WITHOUT_CANDLES, 1, base(), zora_flag_string=zora_flags.encode(LEVEL_9)).rom
    assert "l4-sword-take" not in PATCHES_BY_FLAG["add_l4_sword"]
    for offset in written(FLAGS2_PATCHES["l4-sword-take"]):
        assert rom[offset] == base()[offset], hex(offset)
    for offset, data in owner_patch_writes(["add_l4_sword"]):
        assert rom[offset:offset + len(data)] == data, hex(offset)


def test_no_byte_is_written_by_two_owner_patches() -> None:
    every = [*zora_flags.OWNER_2_0_FIELDS, LEVEL_9_ENTRANCE]
    seen: dict[int, str] = {}
    for flag in every:
        for offset in written(owner_patch_writes([flag])):
            assert offset not in seen, (hex(offset), seen.get(offset), flag)
            seen[offset] = flag


# --- the generator (section 4) -------------------------------------------------------------------

def level_2_cellars(world: GameWorld) -> int:
    level2 = next(level for level in world.levels if level.level_num == 2)
    return len(list(item_cellars(level2)))


@pytest.mark.parametrize("seed", SEEDS)
def test_level_2_has_one_item_cellar_with_level_2_and_none_without(seed: int) -> None:
    assert level_2_cellars(built(ASNB, seed).world) == 1
    assert level_2_cellars(built(LEVEL_9, seed).world) == 0
    assert level_2_cellars(built(ZoraFlags(), seed).world) == 0
    assert all(check.passed for check in run_checks(built(ASNB, seed).world, finished_rom_checks(level_2_sword=True)))


def sword_places(result: Built) -> list[str]:
    return [place.name for place in result.places if read_item(result.world, place) == Item.WOOD_SWORD]


def test_the_sword_joins_the_shuffle() -> None:
    """One sword upgrade among the places, wherever the join put it (not always the cellar, which
    then holds a pool item and is a place, Archipelago's location too)."""
    landed = set()
    for seed in range(1, 9):
        result = built(ASNB, seed)
        places = sword_places(result)
        assert len(places) == 1, (seed, places)
        landed.add(places[0])
        cellar = next(place for place in result.places if place.kind == PlaceKind.CELLAR and place.level == 2)
        assert read_item(result.world, cellar) in major_pool(extra_options(result.plan)), seed
    assert len(landed) > 1


@pytest.mark.parametrize("seed", SEEDS)
def test_the_sword_is_tracked_only_with_the_entrance(seed: int) -> None:
    for flags, tracked in ((ASNB, 1), (LEVEL_2, 0)):
        state = built(flags, seed).result.item_shuffle_result
        assert state is not None
        assert sum(record.item == Item.WOOD_SWORD for record in state.tracked) == tracked


# --- the logic (section 5) ------------------------------------------------------------------------

def closure_holds_entry(result: Built, without: Item | None = None) -> bool:
    state = result.result.item_shuffle_result
    assert state is not None and result.result.overworld is not None
    tracked = [record for record in state.tracked if record.item != without]
    check = AcceptanceCheck(result.world.levels, with_tracked(state, tracked), result.world.overworld,
                            result.result.overworld, extra_options(result.plan).logic_rules)
    return LEVEL9_ENTRY in check.closure()[0]


@pytest.mark.parametrize("seed", SEEDS[:2])
def test_level_9_needs_four_swords_and_no_triforce(seed: int) -> None:
    result = built(ASNB, seed)
    assert closure_holds_entry(result)
    for missing in (Item.WOOD_SWORD, Item.WHITE_SWORD):         # the level-2 sword, the white sword
        assert not closure_holds_entry(result, missing), missing


@pytest.mark.parametrize("seed", SEEDS[:2])
def test_archipelagos_model_counts_four_swords(seed: int) -> None:
    result = built(ASNB, seed)
    model = logic_model(result)
    assert model.events["Level 9 Entry"] == rule_of(CountTerm(SWORD, 4))
    assert model.lines[SWORD].starting == 1 and model.lines[SWORD].ware_event == "Magical Sword Cave"
    assert {Item.WOOD_SWORD, Item.WHITE_SWORD, Item.MAGICAL_SWORD} <= model.progression
    assignment: dict[str, Item | Foreign] = {place.name: read_item(result.world, place) for place in result.places}
    assert sweep(model, assignment).reaches_goal
    sword = sword_places(result)[0]
    elsewhere = {**assignment, sword: FOREIGN}
    assert "Level 9 Entry" not in sweep(model, elsewhere).events
    assert sweep(model, elsewhere, received=[Item.WOOD_SWORD]).reaches_goal


def test_the_triforce_entry_is_unchanged_without_the_entrance() -> None:
    model = logic_model(built(LEVEL_2, 1))
    assert SWORD not in model.lines
    assert all(term.name.startswith("Level ") for clause in model.events["Level 9 Entry"] for term in clause)  # type: ignore[union-attr]


def test_hints_call_it_a_sword_upgrade() -> None:
    assert ItemNames(progressive_items=True).phrase(Item.WOOD_SWORD) == "A SWORD UPGRADE"
    for seed in SEEDS:
        texts = " ".join(quote.text for quote in parse_rom(asnb_rom(seed)).quotes)
        assert "WOOD SWORD" not in texts and "WOODEN SWORD" not in texts, seed


# --- a batch over the ASNB preset (section 7) ------------------------------------------------------

def check_batch(seeds: range | tuple[int, ...]) -> None:
    for seed in seeds:
        result = replay(ASNB_FLAGS, seed, ASNB_ZORA_FLAGS, base())
        assert result.beatable, (seed, result.problems)
        world = parse_rom(result.rom)
        assert level_2_cellars(world) == 1, seed
        failed = [check.check_id for check in run_checks(world, finished_rom_checks(level_2_sword=True))
                  if not check.passed]
        assert not failed, (seed, failed)


def test_the_asnb_preset_passes_on_a_few_seeds() -> None:
    check_batch(SEEDS)


@pytest.mark.slow
@pytest.mark.parametrize("chunk", BATCH_CHUNKS)
def test_the_asnb_preset_passes_on_50_seeds(chunk: int) -> None:
    check_batch(range(1000 + chunk * BATCH_CHUNK_SEEDS, 1000 + (chunk + 1) * BATCH_CHUNK_SEEDS))


# --- the emulator: four sword pickups open level 9 -----------------------------------------------

# The swords' places the emulator test can visit: one-item caves, level rooms and item cellars.
CAVE_NAMES = {"Wood Sword Cave": Destination.WOOD_SWORD_CAVE, "White Sword Cave": Destination.WHITE_SWORD_CAVE,
              "Magical Sword Cave": Destination.MAGICAL_SWORD_CAVE, "Letter Cave": Destination.LETTER_CAVE}


class SwordConsole(Console):
    """A console that keeps its inventory from one visit to the next (carry_inventory)."""

    def __init__(self, rom: bytes) -> None:
        super().__init__(rom)
        self.first = self.start


def take_at(console: SwordConsole, result: Built, name: str) -> None:
    """Take the item of the named place (a one-item cave, a room or a cellar), keeping the
    inventory for the next visit."""
    if name in CAVE_NAMES:
        screen = next(screen.screen_num for screen in parse_rom(asnb_rom(EMULATOR_SEED)).overworld.screens
                      if screen.destination == CAVE_NAMES[name])
        console.enter_cave(screen)
        console.take_ware(ITEM_CAVE_WARE)
    else:
        place = next(place for place in result.places if place.name == name)
        assert place.level is not None and place.room_num is not None
        console.enter_room(place.level, place.room_num)
        console.clear_monsters()
        console.emu[LINK_INVINCIBILITY_TIMER] = INVINCIBLE
        console.take_room_item()
    carry_inventory(console)


INVENTORY = range(ITEMS, ITEMS + 0x28)        # the Items block the game saves ($0657-$067E)


def carry_inventory(console: SwordConsole) -> None:
    """The next visit starts from the new file's state with this inventory (a state saved in a
    cave or a cellar does not start an overworld visit cleanly)."""
    held = {address: console.emu[address] for address in INVENTORY}
    console.emu.load(console.first)
    for address, value in held.items():
        console.emu[address] = value
    console.start = console.emu.save()


EMULATOR_SEED = 1


def meets_the_man(console: SwordConsole) -> bool:
    """Whether the level-9 man lets Link in: he leaves and the shutters open."""
    console.emu.load(console.start)
    console.emu[INV_TRIFORCE] = 0
    level9 = next(level for level in parse_rom(asnb_rom(EMULATOR_SEED)).levels if level.level_num == 9)
    console.emu[CUR_LEVEL] = 9
    console._mode(Mode.LOAD_LEVEL)
    console._wait()
    console.emu[ROOM_ID] = level9.entrance_room - 0x10
    console._mode(ENTER_ROOM_MODE)
    triggered = False
    for _ in range(GATE_FRAMES):
        console.emu.run(1)
        triggered |= bool(console.emu[SHUTTER_TRIGGER])
    present = any(console.emu[OBJ_TYPE + slot] == LEVEL_9_ENTRANCE_PERSON for slot in MONSTER_SLOTS)
    return triggered and not present and bool(console.emu[CUR_OPENED_DOORS])


def test_four_sword_pickups_open_level_9_with_no_triforce() -> None:
    result = build(plan(ASNB_FLAGS, EMULATOR_SEED, ASNB_ZORA_FLAGS), base())
    sword = sword_places(result)[0]
    white = next(place.name for place in result.places if read_item(result.world, place) == Item.WHITE_SWORD)
    console = SwordConsole(asnb_rom(EMULATOR_SEED))
    for step, name in enumerate(("Wood Sword Cave", white, "Magical Sword Cave", sword), start=1):
        if step == 4:
            assert console.emu[ITEMS + SWORD_SLOT] == 3 and not meets_the_man(console)
        take_at(console, result, name)
        assert console.emu[ITEMS + SWORD_SLOT] == step, (step, name)
    assert console.emu[ITEMS + SWORD_SLOT] == SWORD_LEVEL_4
    assert meets_the_man(console)


def test_archipelago_builds_and_finishes_an_asnb_world() -> None:
    """The level-2 sword's place (and the cellar it left) are Archipelago locations: the build's
    places, with their own checks, and FINISH by names makes ZORA's ROM."""
    from zora import archipelago
    from zora.model.item_names import ITEM_NAMES
    result = archipelago.build_from_strings(ASNB_FLAGS, ASNB_ZORA_FLAGS, 1, base())
    names = {place.name for place in result.places}
    assert "Wood Sword" in result.pool and set(sword_places(result.state)) <= names
    checks = archipelago.pickup_checks(result)
    assert len(set(checks.values())) == len(checks)
    assignment = {place.name: ITEM_NAMES[read_item(result.state.world, place)] for place in result.state.places}
    sword = sword_places(result.state)[0]
    rom = archipelago.finish(result, assignment)
    place = next(place for place in result.state.places if place.name == sword)
    assert read_item(parse_rom(rom), place) == Item.WOOD_SWORD
