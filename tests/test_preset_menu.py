"""The page's preset menu (owner, beta 5): published variants A and C under their community names,
Consternation Remastered and Hopla, each with Encode level data on as published (form.PRESET_LABELS);
no variant A without level encoding, and no Random% (published variant B, form.HIDDEN_PRESETS), both
kept in presets.py. Three community flagsets (owner, 2026-10-18), each its published string:
OHK0HPla Remastered, TTP5: Muffle Rug (B22 off with B23 on, kept as given: FL-DEP-06) and TTP5: Pick
5. The other presets are unchanged. The browser half (Pyodide gives the same bytes as
Python) is the manual check in docs/packaging.md; here the worker's own call (zora-worker.js:
generate_rom with the page's player settings) is checked to give the Python build's bytes."""
import json

import pytest

from zora.flags import form
from zora.flags.codec import decode
from zora.flags.fields import ENCODE_LEVEL_DATA, ThreeState
from zora.flags.presets import (
    CONSTERNATION_REMASTERED,
    HOPLA,
    PRESETS,
    PUBLISHED_VARIANT_A,
    PUBLISHED_VARIANT_A_LEVEL_ENCODING_OFF,
    PUBLISHED_VARIANT_B,
    PUBLISHED_VARIANT_C,
    TTP5_MUFFLE_RUG_FLAGS,
)
from zora.generate.pipeline import generate_rom
from zora.rom import level_encoding
from zora.rom.base_rom import remember_repo_base_rom
from zora_web.api import player_settings_from_page

# The published strings, as the community uses them (FL-PRE-02, FL-PRE-04)
ENCODED_PRESETS = {
    "Consternation Remastered": ("Published variant A", "oIbnPfPb01Hll3D295IGDxxjR4UwfEok8P4MD"),
    "Hopla": ("Published variant C", "oIbnRjuMUKqwdnOXzOMO7PuDtwAvU3boJnaXW"),
}
# The rest of the menu, as before: (name, label, flags, ZORA flags)
OTHER_PRESETS = [
    ("MVP baseline", "Consternation", "oIbnPfPb01Hll3D29Bc2!etrojQOSjJQZUJ3A", ""),
    ("MVP baseline, level encoding off", "Consternation without level encoding", "8hq4BeR1JXo89BJ2!TFpTP02u8UJ3A", ""),
    ("All Swords No Boards", "All Swords No Boards", "8hq4BeR1JXo7yjOOHjbxryVQW!UJ3A", "4.T9Jvg"),
    ("Vanilla", "Vanilla", "CEERPCkLslB6BApr1Him1SiR28Y", ""),         # owner, 2026-10-17 (e38d746)
]
# The community flagsets (owner, 2026-10-18): each label and the string it loads
COMMUNITY_PRESETS = {
    "OHK0HPla Remastered": "oIbnRjuQKp1DXiYCys9LwvSpzqZbXk1pRmZzr",
    "TTP5: Muffle Rug": "2487lt0moGMFLRug1ofQdxPuUBWnJVSsi7d202I",
    "TTP5: Pick 5": "p8GIOeYEAonHy5131VdG6b94Ts3EMMvBaQoWR",
}
SEED = 1
ENCODED_ONLY = pytest.mark.skipif(not level_encoding.is_available(), reason="needs the encoder")


def _menu() -> dict[str, dict]:
    return {preset["label"]: preset for preset in form.presets()}


@pytest.mark.parametrize("label", ENCODED_PRESETS)
def test_the_menu_loads_the_encoded_preset_exactly(label: str) -> None:
    name, published = ENCODED_PRESETS[label]
    preset = _menu()[label]
    assert (preset["name"], preset["flags"], preset["zoraFlags"]) == (name, published, "")
    assert decode(preset["flags"]).toggle(ENCODE_LEVEL_DATA) is ThreeState.ON
    assert (CONSTERNATION_REMASTERED, HOPLA) == (PUBLISHED_VARIANT_A, PUBLISHED_VARIANT_C)


def test_the_menu_has_no_unencoded_variant_a_and_no_random_percent() -> None:
    menu = form.presets()
    shown = {preset["flags"] for preset in menu} | {preset["name"] for preset in menu}
    assert PUBLISHED_VARIANT_A_LEVEL_ENCODING_OFF not in shown
    assert PUBLISHED_VARIANT_B not in shown and "Published variant B" not in shown
    assert not any("Random%" in preset["label"] or "variant A without" in preset["label"] for preset in menu)
    assert PRESETS["Published variant B"] == PUBLISHED_VARIANT_B               # kept in the code


def test_the_other_presets_are_unchanged() -> None:
    others = [(preset["name"], preset["label"], preset["flags"], preset["zoraFlags"])
              for preset in form.presets() if preset["label"] not in {*ENCODED_PRESETS, *COMMUNITY_PRESETS}]
    assert others == OTHER_PRESETS


@ENCODED_ONLY
@pytest.mark.parametrize("label", ENCODED_PRESETS)
def test_the_encoded_preset_generates_and_the_workers_call_gives_the_same_bytes(label: str) -> None:
    """Available on the page with level encoding installed, and generated (encoded) in Python; the
    worker's call, with the page's default player settings, gives the same bytes."""
    preset = _menu()[label]
    assert preset["available"]
    base = remember_repo_base_rom()
    python = generate_rom(preset["flags"], SEED, base)
    assert python.encode_level_data
    worker = generate_rom(preset["flags"], SEED, base, player_settings_from_page(json.loads("{}")), "")
    assert worker.rom == python.rom


@pytest.mark.parametrize("label", COMMUNITY_PRESETS)
def test_the_menu_loads_the_community_preset_exactly(label: str) -> None:
    """Listed last, by its own name, loading exactly its string with no ZORA string; loading it
    gives back the same string (the page's form state), and ZORA can produce it."""
    preset = _menu()[label]
    assert (preset["name"], preset["flags"], preset["zoraFlags"]) == (label, COMMUNITY_PRESETS[label], "")
    assert form.form_state(preset["flags"])["flags"] == preset["flags"]
    assert preset["available"] or not level_encoding.is_available()
    assert [p["label"] for p in form.presets()][-len(COMMUNITY_PRESETS):] == list(COMMUNITY_PRESETS)


def test_muffle_rug_is_its_published_string_kept_as_given() -> None:
    """The published string's B22 off and B23 on stay as they are, with no note (FL-DEP-06)."""
    loaded = form.form_state(TTP5_MUFFLE_RUG_FLAGS)
    assert loaded["flags"] == COMMUNITY_PRESETS["TTP5: Muffle Rug"] == TTP5_MUFFLE_RUG_FLAGS
    assert loaded["adjustments"] == []
    settings = decode(TTP5_MUFFLE_RUG_FLAGS)
    assert (settings.toggle("B22"), settings.toggle("B23")) == (ThreeState.OFF, ThreeState.ON)


@ENCODED_ONLY
@pytest.mark.parametrize("label", COMMUNITY_PRESETS)
def test_the_community_preset_generates_and_the_workers_call_gives_the_same_bytes(label: str) -> None:
    preset = _menu()[label]
    assert preset["available"]
    base = remember_repo_base_rom()
    python = generate_rom(preset["flags"], SEED, base)
    worker = generate_rom(preset["flags"], SEED, base, player_settings_from_page(json.loads("{}")), "")
    assert worker.rom == python.rom
