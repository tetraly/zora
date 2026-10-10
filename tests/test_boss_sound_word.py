"""The boss-sound label's word (FP-ROAR-01, a player setting; zora/rom/player_settings.py).

Where it shows: the status bar's nine-tile label above the hearts (PPU $2076) reads " -LIFE-  "
everywhere and " -ROAR-  " while a dungeon room's boss sound plays. fp-roar-01's
CheckBossSoundEffectUW hook sets its flag on each room entry, and FormatStatusBarText copies one of
fp-roar-01's two 13-byte transfer records (bank 5, asm/fp-roar-01/bank_05.s) at every status-bar
text build. The second record's four letters (ZORA_B5_BossSoundWord) sit between its two dash
tiles, in -LIFE-'s place: exactly four fit. The player picks ROAR (the patch's own: nothing
written), Random (a listed word, by a hash of the title screen's seed number) or a word of exactly
four of the font's characters."""
import json
import shutil
import subprocess
from collections import Counter
from functools import cache

import pytest

from tests.test_feature_patches import vanilla
from tests.test_level_word import page_function
from zora.flags import form as flag_form
from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
from zora.generate.pipeline import generate_rom
from zora.rom.code_patch_data import PATCHES
from zora.rom.code_patches import seed_code
from zora.rom.parse.rom_file import parse_rom
from zora.rom.player_settings import (
    BOSS_SOUND_WORD_ADDRESS,
    BOSS_SOUND_WORD_CHARACTERS,
    BOSS_SOUND_WORD_LENGTH,
    BOSS_SOUND_WORDS,
    DEFAULT_BOSS_SOUND_WORD,
    RANDOM_BOSS_SOUND_WORD,
    PlayerSettingError,
    PlayerSettings,
    apply_player_settings,
    boss_sound_word_problem,
    normalized_boss_sound_word,
    player_settings_from_page,
    random_boss_sound_word,
    title_seed_number,
    written_offsets,
)
from zora.rom.text_encoding import BYTE_TO_CHAR, CHAR_TO_BYTE

SEED = 1
LABEL_ADDRESS, LABEL_TILES = 0x2076, 9
USUAL_LABEL = " -LIFE-  "
BOSS_LEVEL = 9
QUICK_WORDS = ("ROAR", "MEOW", "HI !", RANDOM_BOSS_SOUND_WORD)
CUSTOM_CASES = {
    "meow": "MEOW", " Moo! ": "MOO!", "A.B?": "A.B?", "1234": "1234", "HI !": "HI !",
    "MOO": None, "GROWL": None, "": None, "A~BC": None, "AB_C": None, "ÄBCD": None, "random": "RANDOM",
}
# The game's own RAM and modes (tests/emulator.py has the rest).
IS_UPDATING_MODE = 0x11
LOAD_LEVEL_MODE, ENTER_ROOM_MODE, PLAY_MODE = 0x02, 0x04, 0x05
LEVEL_LOAD_FRAMES, ROOM_FRAMES = 300, 200


def label(word: str) -> str:
    return f" -{word}-  "


@cache
def zora_rom(seed: int = SEED) -> bytes:
    return generate_rom(MVP_BASELINE_LEVEL_ENCODING_OFF, seed, vanilla()).rom


def test_the_patch_draws_roar_between_the_dashes() -> None:
    """fp-roar-01's second record: address $2076, nine tiles, " -ROAR-  ", the end byte (PRG0's $FF
    after the patch); the exported word is its four letters, as in ZORA's output."""
    (segment, code), = [(offset, piece) for offset, piece in PATCHES["fp-roar-01"] if offset == 0x17950]
    assert isinstance(code, bytes)
    record = (code + bytes([0xFF]))[-13:]
    assert record == bytes([0x20, 0x76, 0x09, *(CHAR_TO_BYTE[char] for char in " -ROAR-  "), 0xFF])
    assert BOSS_SOUND_WORD_ADDRESS == segment + len(code) - 7
    word = zora_rom()[BOSS_SOUND_WORD_ADDRESS:BOSS_SOUND_WORD_ADDRESS + BOSS_SOUND_WORD_LENGTH]
    assert "".join(BYTE_TO_CHAR[tile] for tile in word) == DEFAULT_BOSS_SOUND_WORD


def test_the_default_leaves_the_output_byte_identical() -> None:
    assert apply_player_settings(zora_rom(), PlayerSettings()) == zora_rom()


@pytest.mark.parametrize("word", [*BOSS_SOUND_WORDS, RANDOM_BOSS_SOUND_WORD, "HI !"])
def test_a_word_changes_only_its_four_bytes(word: str) -> None:
    rom = apply_player_settings(zora_rom(), PlayerSettings(boss_sound_word=word))
    changed = {offset for offset, (a, b) in enumerate(zip(zora_rom(), rom, strict=True)) if a != b}
    assert changed <= written_offsets("boss_sound_word")
    assert seed_code(rom) == seed_code(zora_rom())


# --- Random ----------------------------------------------------------------------------------------

def test_random_draws_only_listed_words_and_all_of_them() -> None:
    drawn = Counter(random_boss_sound_word(seed) for seed in range(5000))
    assert set(drawn) == set(BOSS_SOUND_WORDS)
    assert min(drawn.values()) > 5000 / len(BOSS_SOUND_WORDS) / 2


@pytest.mark.parametrize("seed", [1, 2, 12345])
def test_random_is_the_seeds_word(seed: int) -> None:
    """Random reads the title screen's seed number: the same seed gives the same word, and the word
    depends on nothing else (generation never sees it)."""
    rom = zora_rom(seed)
    assert title_seed_number(rom) == seed
    word = random_boss_sound_word(seed)
    for _ in range(2):
        random = apply_player_settings(rom, PlayerSettings(boss_sound_word=RANDOM_BOSS_SOUND_WORD))
        assert random == apply_player_settings(rom, PlayerSettings(boss_sound_word=word))
    assert random_boss_sound_word(seed) == random_boss_sound_word(seed)


def test_random_needs_a_seed_number() -> None:
    with pytest.raises(PlayerSettingError):
        apply_player_settings(vanilla(), PlayerSettings(boss_sound_word=RANDOM_BOSS_SOUND_WORD))


# --- custom words and the page ----------------------------------------------------------------------

@pytest.mark.parametrize(("typed", "word"), list(CUSTOM_CASES.items()))
def test_custom_words(typed: str, word: str | None) -> None:
    normalized = normalized_boss_sound_word(typed)
    assert (boss_sound_word_problem(normalized) is None) == (word is not None)
    if word is None:
        with pytest.raises(PlayerSettingError):
            player_settings_from_page({"bossSoundWord": typed})
    else:
        assert player_settings_from_page({"bossSoundWord": typed}).boss_sound_word == word


def test_the_page_gets_the_rule_from_the_metadata() -> None:
    metadata = json.loads(json.dumps(flag_form.metadata()))["bossSoundWord"]
    assert metadata == {"default": DEFAULT_BOSS_SOUND_WORD, "random": RANDOM_BOSS_SOUND_WORD,
                        "choices": list(BOSS_SOUND_WORDS), "length": BOSS_SOUND_WORD_LENGTH,
                        "characters": BOSS_SOUND_WORD_CHARACTERS}
    assert len(BOSS_SOUND_WORDS) == 22 and all(boss_sound_word_problem(word) is None for word in BOSS_SOUND_WORDS)


def test_the_pages_check_agrees_with_pythons() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is not installed")
    rule = json.loads(json.dumps(flag_form.metadata()))["bossSoundWord"]
    cases = [*CUSTOM_CASES, *BOSS_SOUND_WORDS, "ROAR", "AB C"]
    script = "\n".join([page_function("normalizedLevelWord"), page_function("bossSoundWordProblem"),
                        f"const rule = {json.dumps(rule)};", f"const cases = {json.dumps(cases)};",
                        "console.log(JSON.stringify(cases.map((typed) => { const word = normalizedLevelWord(typed);"
                        " return [word, bossSoundWordProblem(word, rule)]; })));"])
    answers = json.loads(subprocess.run([node, "-e", script], capture_output=True, text=True, check=True).stdout)
    assert answers == [[normalized_boss_sound_word(typed), boss_sound_word_problem(normalized_boss_sound_word(typed))]
                       for typed in cases]


# --- in the emulator --------------------------------------------------------------------------------

@cache
def boss_sound_rooms() -> tuple[int, ...]:
    level = next(level for level in parse_rom(zora_rom()).levels if level.level_num == BOSS_LEVEL)
    return tuple(room.room_num for room in level.rooms if room.boss_sound)


def labels_in_level_9(word: str) -> tuple[str, str, object]:
    """The label at level 9's entrance and in its first boss-sound room Link survives entering,
    and that room's frame."""
    from tests.emulator import CUR_LEVEL, GAME_MODE, GAME_SUBMODE, ROOM_ID, Emulator
    rom = apply_player_settings(zora_rom(), PlayerSettings(boss_sound_word=word))

    def shown(emu: Emulator) -> str:
        return "".join(BYTE_TO_CHAR.get(tile, "?") for tile in emu.nametable(LABEL_ADDRESS, LABEL_TILES))

    for room in boss_sound_rooms():
        emu = Emulator(rom)
        emu.new_game()
        emu.run(30)
        emu[CUR_LEVEL], emu[GAME_MODE], emu[GAME_SUBMODE], emu[IS_UPDATING_MODE] = BOSS_LEVEL, LOAD_LEVEL_MODE, 0, 0
        emu.run(LEVEL_LOAD_FRAMES)
        entrance = shown(emu)
        emu[ROOM_ID], emu[GAME_MODE], emu[GAME_SUBMODE], emu[IS_UPDATING_MODE] = room, ENTER_ROOM_MODE, 0, 0
        emu.run(ROOM_FRAMES)
        if emu.mode == PLAY_MODE:
            return entrance, shown(emu), emu.last_frame
    raise AssertionError("Link survives no boss-sound room of level 9")


def check_word(word: str) -> None:
    entrance, boss_room, _ = labels_in_level_9(word)
    expected = random_boss_sound_word(SEED) if word == RANDOM_BOSS_SOUND_WORD else word
    assert (entrance, boss_room) == (USUAL_LABEL, label(expected))


@pytest.mark.parametrize("word", QUICK_WORDS)
def test_the_label_shows_the_word(word: str) -> None:
    check_word(word)


@pytest.mark.slow
@pytest.mark.parametrize("word", [word for word in BOSS_SOUND_WORDS if word not in QUICK_WORDS])
def test_every_listed_word_shows(word: str) -> None:
    check_word(word)
