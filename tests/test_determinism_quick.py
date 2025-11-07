import io
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from logic.flags import Flags
from logic.randomizer import Z1Randomizer


ROM_PATH = Path(__file__).resolve().parents[1] / "roms" / "Z1.nes"


@pytest.mark.skipif(not ROM_PATH.exists(), reason="Required test ROM missing: roms/Z1.nes")
@pytest.mark.parametrize("seed", [12345, 8675309, 99999, 42])
def test_randomizer_is_deterministic(seed):
    """Ensure identical inputs produce identical patches across multiple runs."""
    rom_data = ROM_PATH.read_bytes()
    flags = Flags()

    hashes = []
    for _ in range(3):
        rom_bytes = io.BytesIO(rom_data)
        randomizer = Z1Randomizer(rom_bytes, seed, flags)
        patch = randomizer.GetPatch()
        hashes.append(patch.GetHashCode())

    assert len(set(hashes)) == 1, f"Seed {seed} produced varying hashes: {hashes}"
