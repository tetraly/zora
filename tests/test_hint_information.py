"""Wording-free hint-information measures (zora/generate/steps/hint_information.py) and the
HT-HINT-01 rules they rebuild (zora/generate/steps/hint_text.py)."""
from zora.generate.steps.hint_information import Shown, classify
from zora.generate.steps.person_appearances import (
    CAVE_PERSON_TYPES, draw_person_appearances, person_appearance,
)
from zora.generate.rng import ScriptedRng
from zora.generate.steps.hint_text import (
    HUMAN_FORM, ITEM_NAMES, SAME_FORM, Form, Requirement, name_form, requirement_text,
)

OLD_MAN, OLD_WOMAN, MERCHANT, MOBLIN = 0x58, 0x59, 0x5A, 0x5B


def test_name_forms() -> None:
    """HT-HINT-01: "same" when equal, "the human" when the giver is the
    Moblin, else the target's own name."""
    assert name_form(MERCHANT, MERCHANT) == SAME_FORM
    assert name_form(MOBLIN, MOBLIN) == SAME_FORM
    assert name_form(MOBLIN, OLD_MAN) == HUMAN_FORM
    assert name_form(OLD_WOMAN, MOBLIN) == "MOBLIN"
    assert name_form(OLD_MAN, OLD_WOMAN) == "OLD WOMAN"


def test_item_name_table() -> None:
    """HT-HINT-01: 36 names, one per item code $00-$23."""
    assert len(ITEM_NAMES) == 36 and len(set(ITEM_NAMES)) == 36


def test_requirement_texts_render() -> None:
    texts = [requirement_text(Requirement(Form.BOSS, 0x1D, 3)),
             requirement_text(Requirement(Form.LADDER, 0x0A)),
             requirement_text(Requirement(Form.BRACELET, 0x13, white_sword_cave=True)),
             requirement_text(Requirement(Form.NO_RAFT))]
    assert all(1 <= len(t) <= 3 and all(len(line) <= 24 for line in t) for t in texts)
    assert len({tuple(t) for t in texts}) == 4


def _rom(slot: int, text: str, fact: tuple) -> list[Shown]:
    return [Shown(slot, text, frozenset({fact}))]


def test_classify_separates_helpful_from_pool() -> None:
    """A text that always comes with one uncommon fact conveys it; a pool
    text recurring with varying facts, or a text seen once, does not."""
    roms = []
    for i in range(200):
        region = i % 10
        if i % 2 == 0:
            text = f"helpful {region}"               # a function of the fact
        else:
            text = f"pool {i % 7}"                   # unrelated to it
        roms.append(_rom(33, text, ("location", 1, region)))
    roms.append(_rom(33, "once", ("location", 1, 3)))
    verdicts = [rom[0] for rom in classify(roms)]
    for rom, verdict in zip(roms, verdicts):
        text = rom[0].text
        if text.startswith("helpful"):
            assert verdict == ("location", 1, int(text.split()[1]))
        else:
            assert verdict is None


def test_classify_tolerates_rare_misses() -> None:
    """At least 90% of the occurrences carrying the fact is enough (a few
    finished-ROM walk replays miss it)."""
    roms = [_rom(24, "needs ladder", ("requirement", "ladder", 10, None)) for _ in range(19)]
    roms.append(_rom(24, "needs ladder", ("requirement", "boss", 10, 3)))
    for i in range(400):
        roms.append(_rom(24, f"pool {i % 9}", ("requirement", "boss", i % 14, 1 + i % 8)))
    verdicts = [rom[0] for rom in classify(roms)]
    assert all(v == ("requirement", "ladder", 10, None) for v in verdicts[:20])


def test_classify_universal_fact_by_share() -> None:
    """A fact every ROM holds is taken by the text shown in over a quarter
    of the ROMs at its slot (the silver arrow's fixed phrase)."""
    roms = []
    for i in range(400):
        text = "silver elsewhere" if i % 2 == 0 else f"pool {i % 8}"
        roms.append(_rom(35, text, ("silver", "elsewhere")))
    verdicts = [rom[0] for rom in classify(roms)]
    assert verdicts[0] == ("silver", "elsewhere") and verdicts[1] is None


class _World:
    """Just the cave person appearance table."""
    class enemies:
        overworld_npc_pointers = [0] * 43


def test_person_appearances_are_drawn_once_per_type() -> None:
    """FP-PERSON-01 draws the 17 cave person types in type order, $58 + n;
    the hint pass reads its name pairs from them (no draws of its own)."""
    world = _World()
    values = [i % 4 for i in range(len(CAVE_PERSON_TYPES))]
    draw_person_appearances(world, ScriptedRng(values))  # type: ignore[arg-type]
    assert [person_appearance(world, t) for t in CAVE_PERSON_TYPES] == [0x58 + v for v in values]  # type: ignore[arg-type]


def test_b10_refusal_text_leaves_every_hint_slot_in_place() -> None:
    """FP-TRIF-01's refusal text lives outside the hint block (slot 34's
    pointer, as in the corpus finals), so with the B10 features on and off
    the finished ROM holds every generated slot text unchanged, and
    round-trips byte for byte. (The two runs' texts differ: B10 draws the
    sword hearts before the hint text, which picks heart-count quotes by
    them.)"""
    import pytest
    from zora.rom.base_rom import BASE_ROM_PATH, verify_base_rom
    from zora.rom.game_config import GameConfig, HintMode
    from zora.rom.parse.rom_file import load_rom, parse_rom
    from zora.rom.serialize.rom_file import serialize_to_rom
    from zora.generate.rng import Rng
    from zora.generate.generation_pass import generate_shapes
    from zora.generate.shapes.options import ShapeOptions
    if not BASE_ROM_PATH.exists():
        pytest.skip("vanilla ROM missing")
    base = load_rom(verify_base_rom())
    seed = 3
    for b10 in (False, True):
        world = parse_rom(base)
        generate_shapes(world, Rng(seed), ShapeOptions(), feature_data=b10, seed=seed)
        config = GameConfig(hint_mode=HintMode.CONSTERNATION, features_b10=b10)
        out = serialize_to_rom(world, base, config=config)
        finished = parse_rom(out)
        assert serialize_to_rom(finished, out, config=config) == out   # round trip
        assert finished.hint_text_bytes == world.hint_text_bytes
        if b10:
            assert "EIGHT" in finished.level9_refusal_text
