"""The magical-sword cave's hearts in Archipelago (owner rule, 2026-11-23): never more than 12, whatever Randomize
Magical Sword says, as a single-player seed with it on must already (zora_flags.sword_hearts_conflict). With it off the
cave is still a logic event Archipelago must reach, and the solo scan found 7 of 600 seeds whose 13 or 14 asked one
heart more than the seed gives, which stopped generation.

13 and 14 are not offered (zora.archipelago.SWORD_HEARTS_CLAMPED); a value naming one, by number or by key, is read
as 12, never refused; the page's export says so (zora_web.multiworld.sword_hearts_notes). And 12 is within reach:
one starting heart, the pool's heart containers and the take-any allowance give at least 12 in every build."""
import pytest

from tests.needs import needs_base_rom
from zora import archipelago
from zora.generate.logic import HeartsTerm
from zora.rom.base_rom import remember_repo_base_rom
from zora_web import multiworld

pytestmark = needs_base_rom

MAX_HEARTS = 12
TAKE_ANY_FREE = 2           # the take-any allowance counts max(0, k - 2) caves (check_magical_sword_hearts)
EVENT = "Magical Sword Cave"
HEART_FIELDS = ("magical_sword_hearts_min", "magical_sword_hearts_max", "magical_sword_hearts_highest")
# Scan seed 501003's settings: Randomize Magical Sword off, Change Sword Hearts on, one starting heart, Magical Sword
# Hearts (min) 11 and (max) 13 under a cap of 14; on main, its seed 0 asked 13 hearts and the seed gave 12
FLAGS, ZORA = "2M669jNmpUL!6aeMvvhO8bfMwyrrDVLWVXuxhblh!", "23.8r9CT5Q2lXhWD"


def specs() -> dict[str, archipelago.OptionSpec]:
    return {spec.key: spec for spec in archipelago.option_fields()}


def test_no_value_above_12_is_offered() -> None:
    offered = specs()
    for key in HEART_FIELDS:
        spec = offered[key]
        labels = [label for _value, label in spec.choices]
        assert not [label for label in labels if any(hearts in label for hearts in ("13", "14"))], key
        assert spec.default in spec.values
        assert spec.clamped, key
        for _value, read, _key, label in spec.clamped:
            assert any(hearts in label for hearts in ("13", "14"))
            assert "12" in dict(spec.choices)[read], key


@pytest.mark.parametrize("key", HEART_FIELDS)
def test_a_value_above_12_is_read_as_12(key: str) -> None:
    spec = specs()[key]
    for value, read, value_key, _label in spec.clamped:
        assert spec.value_of_key(value_key) == read
        assert archipelago.flag_strings({key: value}) == archipelago.flag_strings({key: read})
        assert archipelago.flag_strings({key: value_key}) == archipelago.flag_strings({key: read})


def test_the_page_s_default_flags_export_as_12_with_a_note() -> None:
    """The page's default preset asks for up to 14 (Magical Sword Hearts (max)): the YAML names 12, and the notes
    say why."""
    exported = multiworld.export_yaml("Tester", archipelago.DEFAULT_FLAGS, "", {})["yaml"]
    assert 'magical_sword_hearts_max: "hearts_12"' in exported
    notes = multiworld.ignored_notes(archipelago.DEFAULT_FLAGS, "")
    assert any("Magical Sword Hearts (max): 14 is read as 12" in note for note in notes)


@pytest.mark.parametrize("seed", range(4))
def test_the_cave_never_asks_more_than_one_starting_heart_and_the_pool_give(seed: int) -> None:
    """The settings read as Archipelago reads them (the flag strings above ask for up to 14): the event's heart term
    asks at most 12, and one starting heart, every heart container of the pool and the take-any allowance reach it."""
    values = {spec.key: spec.read_as(value) for spec, value in zip(archipelago.option_fields(),
                                                                    page_values(FLAGS, ZORA), strict=True)}
    built = archipelago.build_from_strings(*archipelago.flag_strings(values), seed, remember_repo_base_rom())
    model = built.logic
    asked = [term.hearts for clause in model.events[EVENT] for term in clause if isinstance(term, HeartsTerm)]
    assert asked and max(asked) <= MAX_HEARTS
    allowance = max(0, len(model.take_any_events) - TAKE_ANY_FREE)
    assert 1 + built.pool.count("Heart Container") + allowance >= MAX_HEARTS


def page_values(flags: str, zora: str) -> list[int]:
    """Each offered option's value in these strings, in option_fields' order (zora_web.multiworld's reading)."""
    page = multiworld._page_values(flags, zora)
    return [page[spec.id] for spec in archipelago.option_fields()]
