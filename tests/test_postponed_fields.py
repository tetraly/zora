"""Postponed settings (owner ruling 2026-10-22; support.POSTPONED_TOGGLES): a pasted string with
Mirrored Overworld (B06) on or "?" is accepted and generates unmirrored, the same ROM as B06 off,
with a notice in the plan, on the page (the field's row and the list under the button) and in the
seed document and spoiler log. The page itself still offers only off."""
import pytest

from tests.needs import needs_base_rom
from zora.flags import form
from zora.flags.codec import decode, encode
from zora.flags.fields import MIRROR_OVERWORLD, ThreeState
from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
from zora.flags.support import MIRRORED_OVERWORLD_NOTICE, unsupported_fields
from zora.generate.pipeline import build, finish, plan
from zora.rom.base_rom import remember_repo_base_rom
from zora_export.seed_document import seed_document
from zora_export.spoiler_log import spoiler_log

MIRRORED = encode(decode(MVP_BASELINE_LEVEL_ENCODING_OFF).updated(toggles={MIRROR_OVERWORLD.id: ThreeState.ON}))
MIRRORED_RANDOM = encode(decode(MVP_BASELINE_LEVEL_ENCODING_OFF).updated(
    toggles={MIRROR_OVERWORLD.id: ThreeState.POSSIBLE}))


@pytest.mark.parametrize("flag_string", [MIRRORED, MIRRORED_RANDOM])
def test_accepted_with_the_notice(flag_string: str) -> None:
    assert MIRROR_OVERWORLD.id in unsupported_fields(decode(flag_string))      # still not produced
    assert plan(flag_string, 1).notices == (MIRRORED_OVERWORLD_NOTICE,)
    assert plan(flag_string, 1).flag_string == flag_string          # the string keeps B06 as asked


def test_no_notice_with_b06_off() -> None:
    assert plan(MVP_BASELINE_LEVEL_ENCODING_OFF, 1).notices == ()


@needs_base_rom
def test_the_seed_is_not_mirrored_and_the_spoiler_log_says_so() -> None:
    base = remember_repo_base_rom()
    mirrored_plan = plan(MIRRORED, 1)
    rom = finish(build(mirrored_plan, base), base)
    assert rom == finish(build(plan(MVP_BASELINE_LEVEL_ENCODING_OFF, 1), base), base)
    document = seed_document(rom, mirrored_plan)
    assert document["notices"] == [MIRRORED_OVERWORLD_NOTICE]
    assert f"Notice: {MIRRORED_OVERWORLD_NOTICE}." in spoiler_log(document)


def test_the_page_shows_the_notice_and_offers_only_off() -> None:
    state = form.form_state(MIRRORED)
    field = state["fields"][MIRROR_OVERWORLD.id]
    assert not field["problem"] and field["notice"] == MIRRORED_OVERWORLD_NOTICE
    assert state["notices"] == [MIRRORED_OVERWORLD_NOTICE] and not state["generateRefusals"]
    assert str(int(ThreeState.OFF)) not in field["blocked"]
    assert form.supported_values(MIRROR_OVERWORLD) == (int(ThreeState.OFF),)
    assert "notice" not in form.form_state(MVP_BASELINE_LEVEL_ENCODING_OFF)["fields"][MIRROR_OVERWORLD.id]


# An old Uphill Battle string from an out-of-date document: B06 on and five out-of-range option
# slots, each clamped to its last option (FL-ENC-03 rule 3). Since the beta 8 export it has no other
# unsupported field, so it generates (tests/test_tournament_presets.py).
OLD_UPHILL_BATTLE = "143oNtDD4Pw3Yw6SRryTCXlqTsN20hHVl8gF"


def test_the_old_uphill_battle_string_decodes_clamped_and_is_accepted() -> None:
    settings = decode(OLD_UPHILL_BATTLE)
    assert {field_id: settings.option(field_id) for field_id in ("C01", "C07", "C10", "C22", "C23")} == {
        "C01": 4, "C07": 4, "C10": 4, "C22": 4, "C23": 4}
    assert settings.toggle(MIRROR_OVERWORLD) is ThreeState.ON
    assert form.generation_refusals(OLD_UPHILL_BATTLE) == []
