"""The checkpoint registry measures vanilla and generated worlds and
summarizes every entry."""
import os
from pathlib import Path

import pytest

from zora.rom.base_rom import BASE_ROM_PATH, verify_base_rom
from zora.measure.checkpoints.registry import CHECKPOINTS, measure_rom
from zora.measure.checkpoints.comparison import Difference, Estimate, compare, estimate, summarize
from zora.rom.parse.rom_file import load_rom, parse_rom
from zora.rom.serialize.rom_file import serialize_to_rom
from zora.generate.rng import Rng
from zora.generate.generation_pass import generate_shapes
from zora.generate.shapes.options import ShapeOptions


def _vanilla_rom() -> bytes:
    env = os.environ.get("ZORA_VANILLA_ROM")
    cand = Path(env) if env else BASE_ROM_PATH
    if not cand.exists():
        pytest.skip("vanilla ROM missing")
    verify_base_rom(cand)
    return load_rom(cand)


def test_registry_measures_and_summarizes() -> None:
    rom = _vanilla_rom()
    world = parse_rom(rom)
    generate_shapes(world, Rng(5), ShapeOptions())
    generated = parse_rom(serialize_to_rom(world, rom))
    rows = summarize([measure_rom(parse_rom(rom)), measure_rom(generated)])
    assert len(rows) == len(CHECKPOINTS) and all(isinstance(r, str) and r for r in rows)
    values = dict(zip((cp.measure for cp in CHECKPOINTS), measure_rom(generated)))
    assert values["ROMs with exactly one hungry goriya"] is True
    blank, unowned = values["unowned cells carrying the blank room"]
    assert blank == unowned >= 1


def test_share_estimate_and_noise_threshold() -> None:
    share = estimate([1.0, 0.0] * 50)
    assert share is not None and share.value == 0.5
    assert share.stderr == pytest.approx(0.0503, abs=1e-3)   # binomial sqrt(pq/n)
    cp = CHECKPOINTS[0]
    assert not Difference(cp, "share", Estimate(0.55, 0.05), Estimate(0.5, 0.05)).beyond_noise(3)
    assert Difference(cp, "share", Estimate(0.9, 0.03), Estimate(0.5, 0.05)).beyond_noise(3)


def test_ratio_estimate_and_empty_ratio() -> None:
    ratio = estimate([(1.0, 2.0), (3.0, 4.0)])
    assert ratio is not None and ratio.value == pytest.approx(4 / 6)
    assert estimate([(0.0, 0.0), (0.0, 0.0)]) is None
    # no spread in either sample: any gap counts, equal values never do
    exact = Estimate(1.0, 0.0)
    assert not Difference(CHECKPOINTS[0], "ratio", exact, exact).beyond_noise(3)
    assert Difference(CHECKPOINTS[0], "ratio", exact, Estimate(0.9, 0.0)).beyond_noise(3)


def test_every_checkpoint_has_components() -> None:
    rom = _vanilla_rom()
    world = parse_rom(rom)
    generate_shapes(world, Rng(6), ShapeOptions())
    values = measure_rom(parse_rom(serialize_to_rom(world, rom)))
    diffs = compare([values, values], [values, values])
    assert {d.checkpoint.spec_id for d in diffs} == {cp.spec_id for cp in CHECKPOINTS}
    assert not any(d.beyond_noise(3) for d in diffs)


def test_refusal_count_check_reads_the_meaning() -> None:
    """FP-TRIF-01: the count eight crosses as the digit or the word; other
    numbers and words that merely contain it do not count."""
    from types import SimpleNamespace
    from zora.measure.checkpoints.features import b10_level9_refusal

    def states_eight(text: str) -> bool:
        return b10_level9_refusal(SimpleNamespace(level9_refusal_text=text))  # type: ignore[arg-type]

    assert states_eight("BRING 8 PIECES") and states_eight("YOU NEED EIGHT\nPIECES.")
    assert not states_eight("BRING 18 PIECES") and not states_eight("EIGHTY")
    assert not states_eight("BRING SEVEN PIECES") and not states_eight("")
