"""ZORA's rule (owner, beta 7; docs/zora-extras.md "Randomize Dead Woods"): Randomize Dead Woods on,
asked or from its "?", turns Add Lost Woods Shortcut (B88; FP-WOODS-01) on, whatever the Z1R string
holds. Its sequences end with a step south, so the solved maze lets Link out south, never west, and
without the shortcut the river's west side needs the ladder (or the bridges, B87). The Z1R string
is never rewritten; the page shows the shortcut on and locked, with a note, while Randomize Dead
Woods is on, and a note while it is "?"."""
import json
import shutil
import subprocess
from typing import Any

import pytest

from tests.needs import needs_base_rom
from tests.test_web_conflict_tabs import page_function
from zora.flags import form, zora_flags
from zora.flags.codec import decode, encode
from zora.flags.fields import ThreeState
from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
from zora.generate.pipeline import generate_rom, plan
from zora.rom import overworld_crossings as crossings
from zora.rom.base_rom import remember_repo_base_rom

SHORTCUT = "B88"
DEAD_WOODS = zora_flags.encode(zora_flags.ZoraFlags(randomize_dead_woods=ThreeState.ON))
DEAD_WOODS_RANDOM = zora_flags.encode(zora_flags.ZoraFlags(randomize_dead_woods=ThreeState.POSSIBLE))
SEEDS = range(1, 13)


def with_shortcut(state: ThreeState) -> str:
    return encode(decode(MVP_BASELINE_LEVEL_ENCODING_OFF).updated(toggles={SHORTCUT: state}))


@pytest.mark.parametrize("asked", list(ThreeState))
def test_dead_woods_on_turns_the_shortcut_on(asked: ThreeState) -> None:
    chosen = plan(with_shortcut(asked), 1, DEAD_WOODS)
    assert chosen.settings.toggle(SHORTCUT) is ThreeState.ON and chosen.config.lost_woods_shortcut
    assert decode(chosen.flag_string).toggle(SHORTCUT) is asked          # the string is kept as given


def test_dead_woods_off_leaves_the_shortcut_as_asked() -> None:
    assert not plan(with_shortcut(ThreeState.OFF), 1).config.lost_woods_shortcut
    assert plan(with_shortcut(ThreeState.ON), 1).config.lost_woods_shortcut


def test_a_random_dead_woods_turns_it_on_in_the_seeds_it_comes_up_on() -> None:
    outcomes = set()
    for seed in SEEDS:
        chosen = plan(MVP_BASELINE_LEVEL_ENCODING_OFF, seed, DEAD_WOODS_RANDOM)
        dead_woods = chosen.zora_resolved.is_on("randomize_dead_woods")
        assert chosen.config.lost_woods_shortcut is dead_woods
        outcomes.add(dead_woods)
    assert outcomes == {True, False}


@needs_base_rom
def test_the_rom_has_the_shortcuts_byte() -> None:
    rom = generate_rom(MVP_BASELINE_LEVEL_ENCODING_OFF, 1, remember_repo_base_rom(), zora_flag_string=DEAD_WOODS).rom
    assert rom[crossings.ROOM_51_WEST_EDGE] == crossings.OPEN_TREES_COLUMN


def test_the_page_state_forces_it_while_dead_woods_is_on() -> None:
    state = form.form_state(MVP_BASELINE_LEVEL_ENCODING_OFF, DEAD_WOODS)["zora"]
    assert state["forced"] == [{"field": SHORTCUT, "value": int(ThreeState.ON),
                                "message": zora_flags.SHORTCUT_FORCED_NOTE}]
    assert state["conflicts"] == [] and state["warnings"] == []
    assert form.form_state(MVP_BASELINE_LEVEL_ENCODING_OFF, "")["zora"]["forced"] == []


def test_a_random_dead_woods_notes_it() -> None:
    state = form.form_state(MVP_BASELINE_LEVEL_ENCODING_OFF, DEAD_WOODS_RANDOM)["zora"]
    assert state["forced"] == []
    assert state["warnings"] == [{"message": zora_flags.SHORTCUT_RANDOM_NOTE, "fields": [SHORTCUT]}]
    assert form.form_state(with_shortcut(ThreeState.ON), DEAD_WOODS_RANDOM)["zora"]["warnings"] == []


FAKE_PAGE = """
const buttons = () => new Map([0, 1, 2].map((value) => [value, { disabled: false, pressed: null,
  setAttribute(name, text) { this.pressed = text; } }]));
const control = { kind: "segments", buttons: buttons(), row: { hidden: true, locked: false,
  classList: { add(name) { if (name === "setting--locked") control.row.locked = true; } } },
  reason: { textContent: "" } };
const controls = new Map([["B88", control]]);
const plainText = (text) => text;
function paintSegments(buttons, value) {
  for (const [choice, button] of buttons) button.setAttribute("aria-pressed", String(choice === value));
}
"""


def run(script: str) -> Any:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is not installed")
    source = "\n".join([page_function("showForced"), FAKE_PAGE, script])
    return json.loads(subprocess.run([node, "-e", source], capture_output=True, text=True, check=True).stdout)


def test_the_page_shows_the_shortcut_on_locked_with_the_note() -> None:
    forced = form.form_state(MVP_BASELINE_LEVEL_ENCODING_OFF, DEAD_WOODS)["zora"]["forced"]
    shown = run(f"""
showForced({json.dumps(forced)});
console.log(JSON.stringify({{ pressed: [...control.buttons.values()].map((b) => b.pressed),
  disabled: [...control.buttons.values()].every((b) => b.disabled), hidden: control.row.hidden,
  locked: control.row.locked, note: control.reason.textContent }}));
""")
    assert shown == {"pressed": ["false", "true", "false"], "disabled": True, "hidden": False, "locked": True,
                     "note": zora_flags.SHORTCUT_FORCED_NOTE}
    assert "showForced(zora.forced || [])" in page_function("showZoraState")
