"""tests/needs.py's markers skip a test only when what it needs is missing: with the base ROM, the
level encoder and the corpora present, as in the owner's checkout, none of them skips, so no test
marked with them is quietly left out of a run there (and a cloud checkout without them skips).
Each check holds either way, so it also runs in a release tree, which has no encoder or corpora."""
import pytest

from tests.needs import needs_base_rom, needs_corpus, needs_encoder
from zora.rom import level_encoding
from zora.rom.base_rom import BASE_ROM_PATH
from zora_measure.corpora import CLEAN, corpus


def skips(marker: pytest.MarkDecorator) -> bool:
    """Whether a skipif marker skips: its condition."""
    [condition] = marker.mark.args
    return bool(condition)


def test_needs_base_rom_skips_only_without_the_base_rom() -> None:
    assert skips(needs_base_rom) == (not BASE_ROM_PATH.exists())


def test_needs_encoder_skips_only_without_the_encoder() -> None:
    assert skips(needs_encoder) == (not level_encoding.is_available())


def test_needs_corpus_skips_only_without_its_roms() -> None:
    folder = corpus(CLEAN)
    assert skips(needs_corpus(folder)) == (not any(folder.glob("*.nes")))

