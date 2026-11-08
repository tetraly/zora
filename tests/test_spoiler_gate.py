"""The spoiler log's gate (owner rulings 2 and 6, 2026-11-06; docs/seed-format/README.md): the log only at
Spoiler Log Detail Level Basic, Medium or Full, as the seed resolved it; the seed document, the Visualizer's
hand-off, whenever Encode level data is off; "Copy race info" names the level as asked."""
import json
import re
from pathlib import Path

import pytest

from tests.needs import needs_base_rom
from zora.flags.codec import decode, encode
from zora.flags.fields import PRINT_QUEST_INFO, ThreeState
from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
from zora.flags.zora_flags import SpoilerLevel, ZoraFlags
from zora.flags.zora_flags import encode as encode_zora
from zora.generate.pipeline import generate_rom, plan
from zora.rom.base_rom import remember_repo_base_rom
from zora_web import api

REPO = Path(__file__).resolve().parent.parent
PAGE_SCRIPT = (REPO / "web" / "zora-web.js").read_text()
BASELINE = decode(MVP_BASELINE_LEVEL_ENCODING_OFF)
DETAILED = encode_zora(ZoraFlags(detailed_spoiler_log=True))
SEED = 2


def flags_with(b51: ThreeState) -> str:
    return encode(BASELINE.updated(toggles={PRINT_QUEST_INFO.id: b51}))


@needs_base_rom
@pytest.mark.parametrize(("b51", "zora", "level"), [
    (ThreeState.OFF, "", SpoilerLevel.NONE), (ThreeState.ON, "", SpoilerLevel.BASIC),
    (ThreeState.OFF, DETAILED, SpoilerLevel.MEDIUM), (ThreeState.ON, DETAILED, SpoilerLevel.FULL)])
def test_the_log_only_above_none(b51: ThreeState, zora: str, level: SpoilerLevel) -> None:
    flags = flags_with(b51)
    made = generate_rom(flags, SEED, remember_repo_base_rom(), zora_flag_string=zora)
    assert made.spoiler_level is level
    report = api.seed_report(made.rom, flags, SEED, zora)
    assert report["spoilerLevel"] == level
    assert json.loads(str(report["json"]))["seed"]["number"] == str(SEED)       # the Visualizer's hand-off
    if level is SpoilerLevel.NONE:
        assert "spoiler" not in report and "spoilerName" not in report
        with pytest.raises(api.SpoilerLogOff):
            api.spoiler_report(made.rom, flags, SEED, zora)
    else:
        assert api.spoiler_report(made.rom, flags, SEED, zora)["spoiler"] == report["spoiler"]


def test_random_follows_the_level_the_seed_resolved_to() -> None:
    flags = flags_with(ThreeState.POSSIBLE)
    levels = {plan(flags, seed).spoiler_level for seed in range(40)}
    assert levels == set(SpoilerLevel) - {SpoilerLevel.NONE}       # Random always gives a log (2026-11-07)


def page_function(name: str) -> str:
    match = re.search(rf"^function {name}\(.*?^}}$", PAGE_SCRIPT, re.MULTILINE | re.DOTALL)
    assert match, name
    return match.group(0)


def test_the_page_shows_the_log_button_by_level_and_the_visualizer_by_encoding() -> None:
    buttons = page_function("addSeedReportButtons")
    assert "if (result.spoilerLevel > 0) {" in buttons and '"download-spoiler"' in buttons
    assert '"download-tracker"' in buttons and "if (encoded) return;" in buttons
    assert buttons.index("if (encoded) return;") < buttons.index('"view-visualizer"')
    assert "addSeedReportButtons(result, requested.encoded);" in PAGE_SCRIPT
    worker = (REPO / "web" / "zora-worker.js").read_text()
    assert '"spoilerLevel": int(result.spoiler_level)' in worker


def test_the_page_knows_the_spoiler_field() -> None:
    assert api.flag_form.metadata()["spoilerLevelField"] == PRINT_QUEST_INFO.id


@needs_base_rom
def test_an_encoded_seed_with_a_log_gets_its_log_and_tracker_file_but_no_document() -> None:
    """Rulings of 2026-11-06: an encoded seed above None gets its log and tracker file, read from its ROM before
    encoding (GeneratedRom.report_rom); the visualizer's document stays off. At None it gets nothing."""
    from zora.flags.fields import ENCODE_LEVEL_DATA
    from zora.rom import level_encoding
    if not level_encoding.is_available():
        pytest.skip("needs the private level-encoding module")
    base = remember_repo_base_rom()
    with_log = encode(BASELINE.updated(toggles={PRINT_QUEST_INFO.id: ThreeState.ON, ENCODE_LEVEL_DATA.id: ThreeState.ON}))
    made = generate_rom(with_log, SEED, base)
    assert made.encode_level_data and made.report_rom and made.report_rom != made.rom
    report = api.seed_report(made.report_rom, with_log, SEED)
    assert "json" not in report and report["spoilerLevel"] == SpoilerLevel.BASIC
    assert report["spoiler"].startswith("ZORA ") and json.loads(report["tracker"])["Seed"] == str(SEED)
    no_log = encode(BASELINE.updated(toggles={ENCODE_LEVEL_DATA.id: ThreeState.ON}))
    plain = generate_rom(no_log, SEED, base)
    assert plain.report_rom == b""
    with pytest.raises(api.EncodedSeedRefused):
        api.seed_report(plain.rom, no_log, SEED)


@needs_base_rom
def test_the_report_carries_the_tracker_file_and_the_ztracker_note() -> None:
    flags = flags_with(ThreeState.ON)
    made = generate_rom(flags, SEED, remember_repo_base_rom())
    report = api.seed_report(made.rom, flags, SEED)
    assert report["trackerName"].endswith(f"-seed-{SEED}-tracker.json")
    assert isinstance(report["ztrackerNote"], str)
    page = PAGE_SCRIPT
    assert '["Tracker file saved.", report.ztrackerNote].filter(Boolean)' in page and "ZTRACKER_NOTE" not in page
