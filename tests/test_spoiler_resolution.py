"""The spoiler log's flag list shows each setting's final state after every rule that can change a
resolved value, with the "?" resolution still shown where it differs (owner request 2026-10-22):
the seed document's resolution stages end where plan() does, and the line names the rule."""
import pytest

from zora.flags.codec import decode, encode
from zora.flags.fields import ThreeState
from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
from zora.generate.pipeline import plan
from zora_export.seed_document import CAVE_RULE, MONSTER_RULE, resolution_stages, setting_entries
from zora_export.spoiler_log import flag_breakdown

CP5 = decode(MVP_BASELINE_LEVEL_ENCODING_OFF)
MONSTER_COIN = encode(CP5.updated(toggles={"B32": ThreeState.POSSIBLE}))
CAVE_COIN = encode(CP5.updated(options={"C05": 4}))
SEEDS = range(1, 25)
WATCHED_TOGGLES = ("B02", "B04", "B09", "B32", "B33", "B36", "B88")


@pytest.mark.parametrize("flag_string", [MONSTER_COIN, CAVE_COIN])
def test_the_last_stage_is_what_generation_used(flag_string: str) -> None:
    for seed in SEEDS:
        chosen = plan(flag_string, seed)
        final = resolution_stages(chosen)[-1][1]
        assert final.option("C05") == chosen.settings.option("C05")
        assert all(final.toggle(field_id) is chosen.settings.toggle(field_id) for field_id in WATCHED_TOGGLES)


def entry(chosen_plan: object, field_id: str) -> dict[str, str]:
    return next(item for item in setting_entries(chosen_plan) if item.get("id") == field_id)  # type: ignore[arg-type]


def test_a_coin_after_a_random_resolution_shows_both() -> None:
    """B32 "?" resolving off, then rule 3's coin turning it on: "? -> Off -> On (monster shuffle coin)";
    the document's changedBy keeps the spec rule, the log leaves it out."""
    found = []
    for seed in SEEDS:
        chosen = plan(MONSTER_COIN, seed)
        shown = entry(chosen, "B32")
        if "final" in shown:
            assert (shown["chosen"], shown["resolved"], shown["final"], shown["changedBy"]) == (
                "?", "Off", "On", MONSTER_RULE)
            line = " ".join(flag_breakdown({"settings": [shown]})[4:])
            assert "? -> Off -> On (monster shuffle coin)" in line and "FL-DEP" not in line
            found.append(seed)
    assert found


def test_the_cave_coin_is_named() -> None:
    found = [seed for seed in SEEDS if entry(plan(CAVE_COIN, seed), "C05").get("changedBy") == CAVE_RULE]
    assert found


def test_unchanged_settings_show_no_final() -> None:
    chosen = plan(MVP_BASELINE_LEVEL_ENCODING_OFF, 1)
    assert all("final" not in item for item in setting_entries(chosen))
