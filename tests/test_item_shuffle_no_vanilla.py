"""Item Shuffle: Random (No Vanilla) (owner, 2026-10-29; docs/zora-extras.md section 24).

The Z1R string holds Item Shuffle: Random (C06 = 4) and the ZORA field item_shuffle_no_vanilla (version 17) narrows
its draw: each seed gets Item Only, Intra-Dungeon or Full, one in three each, never None, from a stream of its own
(Random's own draw from the Z1R stream still happens, so nothing else in the seed moves). The page shows the pair
as Item Shuffle's sixth choice. Checked: the string (older strings unchanged, the field round-trips), the draw
(never None, each value about a third), the conflicts (the field without Random refused; Extra Raft Blocks, which
Random's possible None refuses, accepted), the page's form, the seed document, and Archipelago (never offered)."""
from collections import Counter
from dataclasses import replace

import pytest

from zora import archipelago
from zora.flags import form, zora_flags
from zora.flags.codec import decode, encode
from zora.flags.fields import ItemShuffleScope, Settings, ThreeState
from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
from zora.flags.zora_flags import NO_VANILLA_ITEM_SHUFFLES, ZoraFlags
from zora.generate.pipeline import FlagsRefused, plan
from zora.generate.rng import Rng
from zora_export.seed_document import setting_entries

ITEM_SHUFFLE = zora_flags.ITEM_SHUFFLE
RANDOM = encode(decode(MVP_BASELINE_LEVEL_ENCODING_OFF).updated(options={ITEM_SHUFFLE.id: ItemShuffleScope.RANDOM}))
NO_VANILLA = zora_flags.encode(ZoraFlags(item_shuffle_no_vanilla=True))
NO_VANILLA_VERSION = 17
SEEDS = range(1, 301)
DRAWS = range(1, 30_001)
# Each value's share of the draws may stray this far from a third (30,000 draws: one standard deviation is 0.27%)
SHARE_TOLERANCE = 0.015
# Extra Raft Blocks with the raft kept in level 3 behind its own raft-blocked entrance (test_owner_flags.RAFT_TRAP),
# Item Shuffle at Random: refused, since Random may draw None
RAFT_TRAP_RANDOM = decode(MVP_BASELINE_LEVEL_ENCODING_OFF).updated(options={"C01": 1, "C02": 3, "C05": 0, "C06": 4})


# --- the string -----------------------------------------------------------------------------------------------------

def test_the_field_round_trips_in_version_17() -> None:
    assert NO_VANILLA.startswith(f"{NO_VANILLA_VERSION}{zora_flags.VERSION_SEPARATOR}")
    assert zora_flags.decode(NO_VANILLA).item_shuffle_no_vanilla
    with_others = replace(zora_flags.decode(NO_VANILLA), progressive_items=True, swordlish=zora_flags.Swordlish.ON)
    assert zora_flags.decode(zora_flags.encode(with_others)) == with_others


def test_older_strings_keep_their_meaning_and_spelling() -> None:
    assert zora_flags.encode(zora_flags.DEFAULT) == ""
    for flags in (ZoraFlags(progressive_items=True), ZoraFlags(swordlish=zora_flags.Swordlish.RANDOM),
                  ZoraFlags(pegasus_boots=ThreeState.POSSIBLE)):
        string = zora_flags.encode(flags)
        assert int(string.split(zora_flags.VERSION_SEPARATOR)[0]) < NO_VANILLA_VERSION
        assert not zora_flags.decode(string).item_shuffle_no_vanilla
        assert zora_flags.encode(zora_flags.decode(string)) == string


# --- the draw -------------------------------------------------------------------------------------------------------

def no_vanilla_draw(seed: int) -> int:
    """The value the field draws for a seed of RANDOM (plan's stream key)."""
    asked = decode(RANDOM)
    key = zora_flags.no_vanilla_rng_key(seed, RANDOM, zora_flags.game_string(zora_flags.decode(NO_VANILLA)))
    resolved = zora_flags.resolve_item_shuffle_no_vanilla(zora_flags.decode(NO_VANILLA), asked, asked, Rng(key).below)
    return resolved.option(ITEM_SHUFFLE)


def test_the_draw_gives_each_non_vanilla_value_a_third() -> None:
    counts = Counter(no_vanilla_draw(seed) for seed in DRAWS)
    assert set(counts) == set(NO_VANILLA_ITEM_SHUFFLES)
    for value in NO_VANILLA_ITEM_SHUFFLES:
        assert abs(counts[value] / len(DRAWS) - 1 / 3) < SHARE_TOLERANCE, counts


def test_plans_never_draw_none_and_move_nothing_else() -> None:
    drawn: Counter[int] = Counter()
    for seed in SEEDS:
        narrowed, random = plan(RANDOM, seed, NO_VANILLA), plan(RANDOM, seed)
        value = narrowed.settings.option(ITEM_SHUFFLE)
        assert value == no_vanilla_draw(seed)
        drawn[value] += 1
        # every other setting is Random's own seed's: the field's stream is its own
        assert narrowed.settings.updated(options={ITEM_SHUFFLE.id: 0}) == \
            random.settings.updated(options={ITEM_SHUFFLE.id: 0}), seed
    assert set(drawn) == set(NO_VANILLA_ITEM_SHUFFLES)


def test_only_random_draws_again() -> None:
    """Resolved values other than Random's are left alone (the field on with them is refused at plan)."""
    flags = zora_flags.decode(NO_VANILLA)
    for value in ItemShuffleScope:
        if value is ItemShuffleScope.RANDOM:
            continue
        asked = decode(RANDOM).updated(options={ITEM_SHUFFLE.id: value})
        assert zora_flags.resolve_item_shuffle_no_vanilla(flags, asked, asked, Rng(1).below) == asked
    off = decode(RANDOM).updated(options={ITEM_SHUFFLE.id: ItemShuffleScope.NONE})
    assert zora_flags.resolve_item_shuffle_no_vanilla(zora_flags.DEFAULT, decode(RANDOM), off, Rng(1).below) == off


# --- the conflicts --------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("value", [value for value in ItemShuffleScope if value is not ItemShuffleScope.RANDOM])
def test_the_field_without_random_is_refused(value: ItemShuffleScope) -> None:
    z1r = encode(decode(RANDOM).updated(options={ITEM_SHUFFLE.id: value}))
    with pytest.raises(FlagsRefused, match="Random \\(No Vanilla\\) needs"):
        plan(z1r, 1, NO_VANILLA)
    found = zora_flags.conflicts(zora_flags.decode(NO_VANILLA), decode(z1r))
    assert (zora_flags.NO_VANILLA_NEEDS_RANDOM, zora_flags.NO_VANILLA_NEEDS_RANDOM_FIELDS) in found


def raft_conflicts(flags: ZoraFlags, z1r: Settings) -> list[str]:
    return [message for message, _ in zora_flags.conflicts(flags, z1r) if message == zora_flags.RAFT_BLOCKS_CONFLICT]


def test_extra_raft_blocks_takes_no_vanilla() -> None:
    """Random is refused beside Extra Raft Blocks with the raft trap's other settings, as it may draw None, the
    trap's Item Shuffle; Random (No Vanilla) never does, so it is accepted, as Item Only, Intra-Dungeon and Full
    are."""
    raft = ZoraFlags(extra_raft_blocks=ThreeState.ON)
    assert raft_conflicts(raft, RAFT_TRAP_RANDOM)
    assert not raft_conflicts(replace(raft, item_shuffle_no_vanilla=True), RAFT_TRAP_RANDOM)
    for value in NO_VANILLA_ITEM_SHUFFLES:
        assert not raft_conflicts(raft, RAFT_TRAP_RANDOM.updated(options={ITEM_SHUFFLE.id: value}))
    z1r = encode(RAFT_TRAP_RANDOM)
    for seed in range(1, 21):
        chosen = plan(z1r, seed, zora_flags.encode(replace(raft, item_shuffle_no_vanilla=True)))
        assert chosen.settings.option(ITEM_SHUFFLE) in NO_VANILLA_ITEM_SHUFFLES
        assert chosen.zora_resolved.extra_raft_blocks is ThreeState.ON


# --- the page -------------------------------------------------------------------------------------------------------

def control_values(state: dict) -> dict[str, str]:
    return {field_id: str(field["value"]) for field_id, field in state["fields"].items()}


def test_the_page_offers_a_sixth_choice_after_random() -> None:
    entry = next(field for field in form.metadata()["fields"] if field["id"] == ITEM_SHUFFLE.id)
    assert [value["label"] for value in entry["values"]] == [
        "None", "Item Only", "Intra-Dungeon", "Full", "Random", "Random (No Vanilla)"]
    assert form.ITEM_SHUFFLE_NO_VANILLA_CHOICE in entry["supportedValues"]
    hidden = [field for field in form.metadata()["zora"]["fields"] if field.get("hidden")]
    assert [field["name"] for field in hidden] == [zora_flags.ITEM_SHUFFLE_NO_VANILLA_FIELD]


def test_the_sixth_choice_writes_both_strings() -> None:
    start = form.form_state(MVP_BASELINE_LEVEL_ENCODING_OFF)
    values = {**control_values(start), ITEM_SHUFFLE.id: str(form.ITEM_SHUFFLE_NO_VANILLA_CHOICE)}
    chosen = form.form_change(start["flags"], values, "")
    assert chosen["flags"] == RANDOM and chosen["zora"]["flags"] == NO_VANILLA
    assert chosen["fields"][ITEM_SHUFFLE.id]["value"] == form.ITEM_SHUFFLE_NO_VANILLA_CHOICE
    assert not chosen["generateRefusals"]
    assert form.form_state(RANDOM, NO_VANILLA)["fields"][ITEM_SHUFFLE.id] == chosen["fields"][ITEM_SHUFFLE.id]
    # another control changed: the choice stays
    other = form.form_change(chosen["flags"], {**control_values(chosen), "B13": "0"}, chosen["zora"]["flags"])
    assert other["zora"]["flags"] == NO_VANILLA and other["fields"][ITEM_SHUFFLE.id]["value"] == 5
    # back to Random, or any other value: the field is off
    for value in ItemShuffleScope:
        back = form.form_change(chosen["flags"], {**control_values(chosen), ITEM_SHUFFLE.id: str(int(value))},
                                chosen["zora"]["flags"])
        assert back["zora"]["flags"] == "" and back["fields"][ITEM_SHUFFLE.id]["value"] == value


def test_random_and_the_sixth_choice_are_blocked_together() -> None:
    for flags in (MVP_BASELINE_LEVEL_ENCODING_OFF, encode(RAFT_TRAP_RANDOM)):
        blocked = form.form_state(flags)["fields"][ITEM_SHUFFLE.id]["blocked"]
        assert blocked.get(str(form.ITEM_SHUFFLE_NO_VANILLA_CHOICE)) == blocked.get(str(int(ItemShuffleScope.RANDOM)))


# --- the seed document and Archipelago --------------------------------------------------------------------------

def test_the_seed_document_shows_the_drawn_value_as_for_random() -> None:
    for seed in range(1, 11):
        chosen = plan(RANDOM, seed, NO_VANILLA)
        entries = setting_entries(chosen)
        item_shuffle = next(entry for entry in entries if entry["id"] == ITEM_SHUFFLE.id)
        drawn = form.value_label(ITEM_SHUFFLE, chosen.settings.option(ITEM_SHUFFLE))
        assert item_shuffle == {"id": ITEM_SHUFFLE.id, "name": "Item Shuffle", "chosen": "?", "resolved": drawn}
        assert {"id": "ZORA", "name": "Item Shuffle: Random (No Vanilla)", "chosen": "on", "resolved": "on"} in entries
    plain = setting_entries(plan(RANDOM, 1))
    assert all(entry["name"] != "Item Shuffle: Random (No Vanilla)" for entry in plain)


def test_archipelago_never_offers_it() -> None:
    assert zora_flags.ITEM_SHUFFLE_NO_VANILLA_FIELD in archipelago.NOT_OFFERED
    assert archipelago.never_offered_refusal(zora_flags.ITEM_SHUFFLE_NO_VANILLA_FIELD, "on") is not None
    assert archipelago.never_offered_refusal(zora_flags.ITEM_SHUFFLE_NO_VANILLA_FIELD, "off") is None
