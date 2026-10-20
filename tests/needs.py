"""Markers for the tests that need something a checkout may not have: the base ROM (never
committed, AGENTS.md "Base ROM"), the measuring corpora (ZORA_CORPORA, zora_measure.corpora) or
the private level encoder (zora.rom.level_encoding). Without it such a test skips with the reason
named here; with it present the test runs exactly as before.

    from tests.needs import needs_base_rom

    @needs_base_rom
    def test_something_on_a_finished_rom() -> None: ...

The checks run when a test is collected: the base ROM's file exists (its hashes are still
verified by whatever reads it), a corpus folder holds ROMs, the encoder module imports.
"""
from pathlib import Path

import pytest

from zora.rom import level_encoding
from zora.rom.base_rom import BASE_ROM_PATH

NEEDS_BASE_ROM = "needs the base ROM"
NEEDS_CORPORA = "needs the corpora"
NEEDS_ENCODER = "needs the encoder"

needs_base_rom = pytest.mark.skipif(not BASE_ROM_PATH.exists(), reason=NEEDS_BASE_ROM)
needs_encoder = pytest.mark.skipif(not level_encoding.is_available(), reason=NEEDS_ENCODER)


def needs_corpus(folder: Path) -> pytest.MarkDecorator:
    """Skip unless FOLDER (a corpus folder, zora_measure.corpora.corpus(name)) holds ROMs."""
    return pytest.mark.skipif(not any(folder.glob("*.nes")), reason=f"{NEEDS_CORPORA} ({folder.name})")
