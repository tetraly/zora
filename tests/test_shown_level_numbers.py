"""Level numbering in the seed document and the spoiler log (owner ruling 2026-10-11): the
document keeps the data number (the door code, `Level.level_num`) where the visualizer reads it
and adds the number the status bar shows (`Level.rom_level_num`) beside it; the spoiler log
prints only the shown number. The two differ only for a second-quest set's paired levels, so
these tests force the pairs' shown numbers on a first-quest seed."""
import re
from functools import cache
from typing import Any

import pytest

from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
from zora.generate.pipeline import generate_rom
from zora.model.game_world import GameWorld
from zora.rom.base_rom import BASE_ROM_PATH, verify_base_rom
from zora.rom.parse.rom_file import parse_rom
from zora_export.seed_document import seed_document_for
from zora_export.spoiler_log import spoiler_log

pytestmark = pytest.mark.skipif(not BASE_ROM_PATH.exists(), reason="needs the base ROM")

SEED = 7
# The second quest's pairs: each level shows its partner's number.
PAIRED = {2: 3, 3: 2, 4: 5, 5: 4, 7: 8, 8: 7}
SHOWN = {number: PAIRED.get(number, number) for number in range(1, 10)}


@cache
def finished() -> bytes:
    return generate_rom(MVP_BASELINE_LEVEL_ENCODING_OFF, SEED, verify_base_rom().read_bytes()).rom


def paired_document(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """The seed's document with the second quest's shown numbers in place of its own."""
    def parse_with_pairs(rom: bytes, *args: Any, **kwargs: Any) -> GameWorld:
        world = parse_rom(rom, *args, **kwargs)
        for level in world.levels:
            level.rom_level_num = SHOWN[level.level_num]
        return world

    monkeypatch.setattr("zora_export.seed_document.parse_rom", parse_with_pairs)
    return seed_document_for(finished(), MVP_BASELINE_LEVEL_ENCODING_OFF, SEED)


def as_shown(text: str) -> str:
    return re.sub(r"Level (\d)", lambda match: f"Level {SHOWN[int(match.group(1))]}", text)


def test_a_first_quest_seed_shows_its_data_numbers() -> None:
    document = seed_document_for(finished(), MVP_BASELINE_LEVEL_ENCODING_OFF, SEED)
    assert [(level["number"], level["shownNumber"]) for level in document["levels"]] == [
        (number, number) for number in range(1, 10)]
    doors = [screen["cave"] for screen in document["overworld"]["screens"] if "shownName" in screen["cave"]]
    assert len(doors) == 9
    assert all((door["shownName"], door["shownShortName"]) == (door["name"], door["shortName"]) for door in doors)
    assert all(hint["shownSpeaker"] == hint["speaker"] for hint in document["hints"] if "shownSpeaker" in hint)


def test_the_document_keeps_data_numbers_and_adds_the_shown_ones(monkeypatch: pytest.MonkeyPatch) -> None:
    document = paired_document(monkeypatch)
    assert [level["number"] for level in document["levels"]] == list(range(1, 10))
    assert [level["shownNumber"] for level in document["levels"]] == [SHOWN[n] for n in range(1, 10)]
    doors = {screen["cave"]["name"]: screen["cave"] for screen in document["overworld"]["screens"]
             if "shownName" in screen["cave"]}
    assert set(doors) == {f"Level {number}" for number in range(1, 10)}
    for number in range(1, 10):
        door = doors[f"Level {number}"]
        assert door["shortName"] == f"L{number}"
        assert (door["shownName"], door["shownShortName"]) == (f"Level {SHOWN[number]}", f"L{SHOWN[number]}")
    in_levels = [hint for hint in document["hints"] if "shownSpeaker" in hint]
    assert in_levels
    assert all(hint["shownSpeaker"] == as_shown(hint["speaker"]) for hint in in_levels)
    assert any(hint["shownSpeaker"] != hint["speaker"] for hint in in_levels)


def test_the_spoiler_log_prints_only_shown_numbers(monkeypatch: pytest.MonkeyPatch) -> None:
    unpaired = spoiler_log(seed_document_for(finished(), MVP_BASELINE_LEVEL_ENCODING_OFF, SEED))
    document = paired_document(monkeypatch)
    log = spoiler_log(document)
    items = log.split("Major items by place")[1].split("\nOverworld\n")[0]
    headings = re.findall(r"^Level (\d)$", items, re.M)
    assert headings == [str(number) for number in range(1, 10)]
    # data level 2's items are listed under the heading its status bar shows, "Level 3"
    sections = dict(zip(headings, re.split(r"^Level \d$", items, flags=re.M)[1:], strict=True))
    plain = unpaired.split("Major items by place")[1].split("\nOverworld\n")[0]
    plain_sections = dict(zip(re.findall(r"^Level (\d)$", plain, re.M),
                              re.split(r"^Level \d$", plain, flags=re.M)[1:], strict=True))
    for number in range(1, 10):                                # each line names its level as shown
        assert sections[str(SHOWN[number])] == as_shown(plain_sections[str(number)])
    # every "said by" line names a dungeon person's level by its shown number
    said = [hint for hint in document["hints"] if "shownSpeaker" in hint and hint["shownSpeaker"] != hint["speaker"]]
    assert said
    flat = " ".join(log.split())
    for hint in said:
        assert f"said by {hint['shownSpeaker']}" in flat
        assert f"said by {hint['speaker']}" not in flat
