"""The level word in the hints (FP-LEVEL-01's player setting, part 2; zora/rom/player_settings.py
relabel_hint_text).

Hint text is written at generation, before the player settings, so the setting rewrites it in
place. Each hint line holding a level label ("LEVEL-3") gets the word's label ("LAIR-3",
"PALACE3"), is centred again on the box's width and padded at its end to its old length. A label
is never longer than LEVEL-n, so every line only gets shorter and every hint still fits: each text
keeps its length, place and pointer.

Tested over every listed word (and custom words with a space and punctuation), every item (by its
own name, by its upgrade line with Progressive Items, and as another player's item), every region,
every level and every opener, as hint_text composes and wraps them; and on generated ROMs."""
from dataclasses import replace
from functools import cache

import pytest

from tests.test_feature_patches import vanilla
from zora.flags import zora_flags
from zora.flags.codec import decode, encode
from zora.flags.fields import ThreeState
from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
from zora.generate.pipeline import generate_rom
from zora.generate.steps.hint_text import (
    ITEM_NAMES,
    LINE_WIDTH,
    MAX_LINES,
    OPENERS,
    POOL,
    PROGRESSIVE_NAMES,
    REGION_PHRASES,
    VANILLA_NAMES,
    ItemNames,
    encode_text,
    hint_lines,
    item_location_sentence,
    level_location_sentence,
    with_opener,
)
from zora.rom.layout import QUOTE_DATA_ADDRESS
from zora.rom.player_settings import (
    DEFAULT_LEVEL_WORD,
    HINT_LEVEL_LABEL,
    LEVEL_WORD_CHOICES,
    PlayerSettings,
    apply_player_settings,
    hint_text_offsets,
    level_label,
    relabel_hint_text,
    text_body,
    written_offsets,
)
from zora.rom.text_encoding import BYTE_TO_CHAR, QUOTE_CHAR_MASK, QUOTE_END_BITS

PAD = "~"
LEVELS = range(1, 10)
FOREIGN_CODE = 0x22               # any code: Archipelago's FINISH writes another player's item as one
WORDS = (*LEVEL_WORD_CHOICES[1:], "OH NO", "R2-D2", "A.B,C", "X")
SEEDS = (1, 2, 3)
PROGRESSIVE_ZORA_FLAGS = zora_flags.encode(replace(zora_flags.DEFAULT, progressive_items=True))
# Progressive Items refuses Extra Candles (B09).
PROGRESSIVE_BASE = encode(decode(MVP_BASELINE_LEVEL_ENCODING_OFF).updated(toggles={"B09": ThreeState.OFF}))


def decoded_lines(body: bytes) -> list[str]:
    lines, current = [], ""
    for byte in body:
        current += BYTE_TO_CHAR[byte & QUOTE_CHAR_MASK]
        if byte & QUOTE_END_BITS:
            lines.append(current)
            current = ""
    return lines


def hint_sentences() -> list[str]:
    """Every location sentence hint_text can compose."""
    namings = (VANILLA_NAMES, PROGRESSIVE_NAMES, ItemNames(foreign_code=FOREIGN_CODE))
    sentences = {item_location_sentence(code, level, names)
                 for code in range(len(ITEM_NAMES)) for level in LEVELS for names in namings}
    sentences |= {level_location_sentence(level, region) for level in LEVELS for region in REGION_PHRASES}
    return sorted(sentences)


@cache
def hint_texts() -> list[tuple[str, list[str]]]:
    """(the full text, its lines) for every sentence alone and with every opener that fits, as
    hint_text wraps them."""
    texts = []
    for sentence in hint_sentences():
        texts.append((sentence, hint_lines(sentence)))
        for opener in OPENERS:
            lines = with_opener(opener, sentence)
            if lines is not None:
                texts.append((f"{opener} {sentence}", lines))
    return texts


def with_word(text: str, word: str) -> str:
    return HINT_LEVEL_LABEL.sub(lambda label: level_label(word).replace("1", label.group(1)), text)


def test_the_texts_cover_every_item_region_level_and_opener() -> None:
    texts = [text for text, _ in hint_texts()]
    assert all(HINT_LEVEL_LABEL.search(text) for text in texts)
    for opener in OPENERS:
        assert any(text.startswith(opener) for text in texts), opener
    for phrase in REGION_PHRASES.values():
        assert any(phrase in text for text in texts), phrase
    assert len(texts) > 3000


@pytest.mark.parametrize("word", WORDS)
def test_every_hint_takes_the_word_and_still_fits(word: str) -> None:
    for text, lines in hint_texts():
        body = bytes(encode_text(lines))
        relabelled = relabel_hint_text(body, word)
        assert len(relabelled) == len(body)
        new_lines = decoded_lines(relabelled)
        assert len(new_lines) == len(lines) <= MAX_LINES
        assert all(len(line) <= LINE_WIDTH for line in new_lines), (word, new_lines)
        assert " ".join(line.strip(PAD) for line in new_lines) == with_word(text, word)
        for old, new in zip(decoded_lines(body), new_lines, strict=True):
            if old != new:
                shown = new.strip(PAD)
                assert new.startswith(PAD * ((LINE_WIDTH - len(shown)) // 2) + shown), (word, new)
        assert relabelled[-1] & QUOTE_END_BITS == QUOTE_END_BITS


def test_no_other_text_says_level() -> None:
    """PRG0's texts and the community pool never show a level label, so the setting changes
    only ZORA's location hints."""
    assert not any(HINT_LEVEL_LABEL.search(" ".join(entry.lines)) for entry in POOL)
    prg0 = vanilla()
    for offset in hint_text_offsets(prg0):
        assert not HINT_LEVEL_LABEL.search(" ".join(decoded_lines(text_body(prg0, offset)))), hex(offset)


@cache
def finished(seed: int, zora_flag_string: str) -> bytes:
    flags = PROGRESSIVE_BASE if zora_flag_string else MVP_BASELINE_LEVEL_ENCODING_OFF
    return generate_rom(flags, seed, vanilla(), zora_flag_string=zora_flag_string).rom


@pytest.mark.parametrize("zora_flag_string", ["", PROGRESSIVE_ZORA_FLAGS], ids=["vanilla names", "progressive"])
@pytest.mark.parametrize("seed", SEEDS)
def test_generated_hints_take_the_word(seed: int, zora_flag_string: str) -> None:
    rom = finished(seed, zora_flag_string)
    offsets = hint_text_offsets(rom)
    labelled = [offset for offset in offsets
                if HINT_LEVEL_LABEL.search(" ".join(decoded_lines(text_body(rom, offset))))]
    assert labelled, "no location hint in this seed"
    pointers = rom[QUOTE_DATA_ADDRESS:offsets[0]]
    for word in ("LAIR", "PALACE"):
        new = apply_player_settings(rom, PlayerSettings(level_word=word))
        assert new[QUOTE_DATA_ADDRESS:offsets[0]] == pointers
        changed = {offset for offset, (a, b) in enumerate(zip(rom, new, strict=True)) if a != b}
        assert changed <= written_offsets("level_word")
        for offset in offsets:
            before, after = text_body(rom, offset), text_body(new, offset)
            assert len(after) == len(before)
            text = " ".join(line.strip(PAD) for line in decoded_lines(after))
            assert not HINT_LEVEL_LABEL.search(text)
            assert text == with_word(" ".join(line.strip(PAD) for line in decoded_lines(before)), word)


def test_the_default_leaves_the_hints() -> None:
    rom = finished(SEEDS[0], "")
    assert apply_player_settings(rom, PlayerSettings(level_word=DEFAULT_LEVEL_WORD)) == rom
