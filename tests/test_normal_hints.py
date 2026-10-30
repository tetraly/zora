"""Hint Type: Normal (C03 = 0; hints-behavior.md HT-HINT-05, the 2026-10-22 export), on generated
seeds:

  - PRG0's text block stays: its text is PRG0's, and of its 38 pointers only slots 27 (the toll),
    34 (the level-9 refusal text), 36 (slot 0's text) and B19's exchanged slots differ.
  - The exchange starts at slot 19: its eleven slots hold a permutation of their PRG0 pointers;
    with B19 off none moves.
  - The level-9 refusal text is outside PRG0's block, at $B780 (the normal-hints place), and says
    what Level 9 Entry asks for; the level word reaches it there.
  - The white-sword cave and the hint shops keep PRG0's selectors and prices; the dungeon hint
    rooms' families never hold $4C.
  - ZORA's rule for a randomized maze (docs/deviations.md): its offer shows the path and costs 1.
  - Archipelago's FINISH keeps normal hints when it recomposes them.
  - ZORA keeps PRG0's text 0 for slot 0 and slot 36 (owner ruling: no greeting; deviations)."""
from functools import cache

import pytest

from tests.needs import needs_base_rom
from tests.test_assignment import identity
from zora.flags import zora_flags
from zora.flags.codec import decode, encode
from zora.flags.fields import HintStyle, Level9Requirement, ThreeState
from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
from zora.generate.pipeline import Built, build, finish, plan
from zora.generate.steps.shuffle_dungeon_text import NORMAL_SHUFFLED_SLOTS
from zora.model.enums import Destination
from zora.model.game_world import GameWorld
from zora.model.overworld import HintShop
from zora.rom.base_rom import remember_repo_base_rom
from zora.rom.layout import NORMAL_REFUSAL_TEXT_POINTER, NUM_QUOTES
from zora.rom.parse.rom_file import parse_rom
from zora.rom.player_settings import PlayerSettings, apply_player_settings

pytestmark = needs_base_rom

SEEDS = range(1, 5)
TOLL_SLOT, REFUSAL_SLOT, GREETING_SLOT, SECOND_GREETING_SLOT = 27, 34, 0, 36
FAMILY_ENTRIES = 8
REPLACED_SELECTOR = 0x4C
MAZE_PRICE = 1
REFUSAL_POINTER = NORMAL_REFUSAL_TEXT_POINTER[0] | NORMAL_REFUSAL_TEXT_POINTER[1] << 8
BOTH_MAZES = zora_flags.encode(zora_flags.ZoraFlags(randomize_lost_hills=ThreeState.ON,
                                                    randomize_dead_woods=ThreeState.ON))


def flags(toggles: dict[str, ThreeState] | None = None, **options: int) -> str:
    return encode(decode(MVP_BASELINE_LEVEL_ENCODING_OFF).updated(
        options={"C03": HintStyle.NORMAL, **options}, toggles=toggles or {}))


@cache
def built(flag_string: str, seed: int, zora: str = "") -> Built:
    return build(plan(flag_string, seed, zora), remember_repo_base_rom())


@cache
def rom(flag_string: str, seed: int, zora: str = "") -> bytes:
    return finish(built(flag_string, seed, zora), remember_repo_base_rom())


@cache
def base_world() -> GameWorld:
    return parse_rom(remember_repo_base_rom())


def pointers(world: GameWorld) -> list[int]:
    raw = world.quotes_raw
    return [raw[2 * slot] | raw[2 * slot + 1] << 8 for slot in range(NUM_QUOTES)]


def prices(world: GameWorld) -> list[int]:
    return [hint.price for destination in (Destination.HINT_SHOP_1, Destination.HINT_SHOP_2)
            for shop in [world.overworld.get_cave(destination, HintShop)] if shop is not None for hint in shop.hints]


@pytest.mark.parametrize("seed", SEEDS)
def test_prg0_s_block_stays_but_for_four_kinds_of_slot(seed: int) -> None:
    world = parse_rom(rom(flags(), seed))
    assert len(world.quotes) == NUM_QUOTES
    shipped, prg0 = pointers(world), pointers(base_world())
    assert world.quotes_raw[2 * NUM_QUOTES:] == base_world().quotes_raw[2 * NUM_QUOTES:]
    changed = {slot for slot in range(NUM_QUOTES) if shipped[slot] != prg0[slot]}
    assert changed <= {TOLL_SLOT, REFUSAL_SLOT, SECOND_GREETING_SLOT, *NORMAL_SHUFFLED_SLOTS}
    assert shipped[SECOND_GREETING_SLOT] == shipped[GREETING_SLOT] == prg0[GREETING_SLOT]
    assert shipped[REFUSAL_SLOT] == REFUSAL_POINTER
    assert sorted(shipped[slot] for slot in NORMAL_SHUFFLED_SLOTS) == sorted(prg0[slot] for slot in NORMAL_SHUFFLED_SLOTS)


@pytest.mark.parametrize("seed", SEEDS)
def test_with_b19_off_no_pointer_is_exchanged(seed: int) -> None:
    world = parse_rom(rom(flags(toggles={"B19": ThreeState.OFF}), seed))
    shipped, prg0 = pointers(world), pointers(base_world())
    assert {slot for slot in range(NUM_QUOTES) if shipped[slot] != prg0[slot]} <= {
        TOLL_SLOT, REFUSAL_SLOT, SECOND_GREETING_SLOT}


@pytest.mark.parametrize("seed", SEEDS)
def test_the_selectors_and_prices_stay_prg0_s(seed: int) -> None:
    world = parse_rom(rom(flags(), seed))
    assert world.white_sword_text_selector == base_world().white_sword_text_selector
    assert world.hint_shop_offer_selectors == base_world().hint_shop_offer_selectors
    assert prices(world) == prices(base_world())
    for family in (world.underworld_text_selectors_a, world.underworld_text_selectors_b):
        assert family is not None and REPLACED_SELECTOR not in family[:FAMILY_ENTRIES]


@pytest.mark.parametrize("seed", (1, 2))
def test_the_refusal_text_states_level_9_s_requirement(seed: int) -> None:
    world = parse_rom(rom(flags(C08=3), seed))
    assert "FIVE" in world.level9_refusal_text


def test_the_level_word_reaches_the_refusal_text_at_its_normal_place() -> None:
    finished = rom(flags(C08=Level9Requirement.SPECIFIC_PIECES), 2)
    shown = parse_rom(apply_player_settings(finished, PlayerSettings(level_word="PALACE"))).level9_refusal_text
    assert "PIECES OF PALACES" in shown or "PIECE OF PALACE" in shown


@pytest.mark.parametrize("seed", (1, 2))
def test_a_randomized_maze_s_offer_shows_its_path_for_1_rupee(seed: int) -> None:
    seed_built = built(flags(), seed, BOTH_MAZES)
    offers = seed_built.result.maze_offers
    assert offers
    world = parse_rom(rom(flags(), seed, BOTH_MAZES))
    selectors = world.hint_shop_offer_selectors
    assert selectors is not None
    shown_prices = prices(world)
    for offer, maze in offers.items():
        text = world.quotes[selectors[offer] // 2].text or ""
        assert all(line.strip() in text for line in maze.lines), (offer, text)
        assert maze.price == shown_prices[offer] == MAZE_PRICE


@pytest.mark.parametrize("seed", (1, 2))
def test_finish_keeps_normal_hints(seed: int) -> None:
    """Archipelago's FINISH recomposes the hint text (B19's exchange with its own draws): still
    PRG0's block, the same kinds of slot changed, and the same room selectors."""
    seed_built = built(flags(), seed)
    again = parse_rom(finish(seed_built, remember_repo_base_rom(), identity(seed_built)))
    once = parse_rom(rom(flags(), seed))
    assert again.quotes_raw[2 * NUM_QUOTES:] == base_world().quotes_raw[2 * NUM_QUOTES:]
    shipped, prg0 = pointers(again), pointers(base_world())
    assert {slot for slot in range(NUM_QUOTES) if shipped[slot] != prg0[slot]} <= {
        TOLL_SLOT, REFUSAL_SLOT, SECOND_GREETING_SLOT, *NORMAL_SHUFFLED_SLOTS}
    assert (again.underworld_text_selectors_a, again.underworld_text_selectors_b) == (
        once.underworld_text_selectors_a, once.underworld_text_selectors_b)
