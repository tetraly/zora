"""The hint text's figures (hints-behavior.md)."""

from collections import Counter
from collections.abc import Callable
from typing import Any

from zora.generate.steps.hint_information import BLANK, GREETING
from zora.measure.checkpoints.shapes_and_gate import per_thousand_by_key
from zora.measure.checkpoints.summaries import FLAG_COUNTS, Summary
from zora.model.enums import Destination
from zora.model.game_world import GameWorld
from zora.model.overworld import HintShop

# --- Hint text (hints-behavior.md) ------------------------------------------------

SPEC_HINT = "hints-behavior.md @ 1e0f219"

# The primary/spare selector set after the $26 -> $4C replacement, plus the
# PRG0-retained $32 value (HT-SEL-01).
HINT_SELECTOR_VALUES = frozenset({
    0x28, 0x2A, 0x2C, 0x2E, 0x30, 0x32, 0x34, 0x38, 0x3A, 0x3C, 0x3E, 0x40, 0x42, 0x4C,
})
EXPECTED_OFFER_SELECTORS = (0x18, 0x4E, 0x50, 0x52, 0x54, 0x56)


def _hint_shops(gw: GameWorld) -> tuple[HintShop, HintShop]:
    hs1 = gw.overworld.get_cave(Destination.HINT_SHOP_1, HintShop)
    hs2 = gw.overworld.get_cave(Destination.HINT_SHOP_2, HintShop)
    assert hs1 is not None and hs2 is not None
    return hs1, hs2


def hint_shop_prices(gw: GameWorld) -> tuple[int, ...]:
    hs1, hs2 = _hint_shops(gw)
    return tuple(h.price for h in hs1.hints + hs2.hints)


def white_sword_selector(gw: GameWorld) -> int:
    return gw.white_sword_text_selector or 0


def hint_shop_offer_selectors(gw: GameWorld) -> tuple[int, ...]:
    return gw.hint_shop_offer_selectors or ()


def underworld_selector_tables(gw: GameWorld) -> dict[str, bool]:
    """HT-SEL-01: the first eight bytes of tables A and B contain no $26 and
    only values from the primary/spare set (or the retained $32)."""
    a = gw.underworld_text_selectors_a or bytes(8)
    b = gw.underworld_text_selectors_b or bytes(8)
    return {
        "A no $26": 0x26 not in a,
        "A values ok": all(v in HINT_SELECTOR_VALUES for v in a),
        "B no $26": 0x26 not in b,
        "B values ok": all(v in HINT_SELECTOR_VALUES for v in b),
    }


def _per_thousand_counts(keys: tuple[str, ...]) -> Summary:
    """Per-ROM Counters (after a cross-sample resolve), reported per 1,000 ROMs."""
    def text(values: list[Counter[str]]) -> str:
        total: Counter[str] = sum(values, Counter())
        return " ".join(f"{key} {1000 * total[key] / len(values):.0f}" for key in keys)
    return Summary(text, lambda counts: {key: float(counts[key]) for key in keys})


def _hint_information(keys: tuple[str, ...],
                      resolve: Callable[[list[Any]], list[Any]]) -> Summary:
    base = _per_thousand_counts(keys)
    return Summary(base.text, base.components, resolve)


def _location_summary() -> Summary:
    from zora.generate.steps.hint_information import location_results
    return Summary(FLAG_COUNTS.text, FLAG_COUNTS.components, location_results)


def _hint_summaries() -> tuple[Summary, Summary, Summary]:
    from zora.generate.steps.hint_information import (
        FORMS,
        NAME_FORMS,
        TRIO_PARTS,
        name_results,
        requirement_results,
        trio_results,
    )
    return (_hint_information(FORMS, requirement_results),
            _hint_information((*NAME_FORMS, "shown 3", "shown 6", "shown 7"), name_results),
            _hint_information(TRIO_PARTS, trio_results))


REQUIREMENT_SUMMARY, NAME_SUMMARY, TRIO_SUMMARY = _hint_summaries()


def _inside_dungeon_summary() -> Summary:
    from zora.generate.steps.hint_information import INSIDE_DUNGEON_KEYS
    return per_thousand_by_key(INSIDE_DUNGEON_KEYS)
LOCATION_SUMMARY = _location_summary()


def _text_kind_summary(slots: tuple[int, ...], kinds: tuple[str, ...]) -> Summary:
    """HT-TEXT-02's text kinds (zora/generate/steps/hint_information.py text_kind_results)
    over some slots: totals per 1,000 ROMs in the cell, each slot and kind as
    a component."""
    from zora.generate.steps.hint_information import text_kind_results
    keys = tuple(f"{slot} {kind}" for slot in slots for kind in kinds)

    def text(values: list[Counter[str]]) -> str:
        total: Counter[str] = sum(values, Counter())
        scale = 1000 / len(values)
        cells = [f"{kind} {sum(total[f'{slot} {kind}'] for slot in slots) * scale:.0f}" for kind in kinds]
        fallbacks = {slot: total[f"{slot} {GREETING}"] + total[f"{slot} {BLANK}"] for slot in slots}
        if len(slots) > 1 and any(fallbacks.values()):
            worst = max(slots, key=lambda slot: fallbacks[slot])
            cells.append(f"(fallback most in slot {worst}: {fallbacks[worst] * scale:.0f})")
        return " ".join(cells)
    return Summary(text, lambda counts: {key: float(counts[key]) for key in keys}, text_kind_results)


def _white_sword_hint_summary() -> Summary:
    from zora.generate.steps.hint_information import white_sword_hint_results
    keys = ("when matching", "otherwise")

    def text(values: list[dict[str, tuple[int, int]]]) -> str:
        return ", ".join(f"{sum(v[key][0] for v in values)}/{sum(v[key][1] for v in values)} {key}"
                         for key in keys)
    return Summary(text, lambda value: {key: (float(value[key][0]), float(value[key][1])) for key in keys},
                   white_sword_hint_results)


def _hint_record(name: str) -> Callable[[GameWorld], Any]:
    def record(gw: GameWorld) -> Any:
        import zora.generate.steps.hint_information as information
        return getattr(information, name)(gw)
    record.__name__ = name
    return record
