"""Rotated seed sweeps (owner decision, 2026-10-16: make the batch run tractable). A slow test that
sweeps many seeds per case checks SEEDS_PER_SWEEP of them per run, and each batch run takes the next
block of its range, so coverage accumulates across runs; the assertions are unchanged.

    ZORA_SWEEP_BLOCK=N      block N (modulo the range's block count; scripts/batch_run.py sets it,
                            one more each run, and records it in its log)
    ZORA_SWEEP_BLOCK=all    the whole range, as before the rotation
    (unset)                 block 0

The rotation stays inside each sweep's original range (seeds 0-99, say), seeds that all passed when
the rotation began, so a failure in the batch run is a regression a commit made, which
scripts/batch_run.py trace can bisect, not an old fault on a never-tried seed. A test id names its
seeds ("seeds 40-49"); to reproduce a failure, set the block the run's log names.
"""
import os

SEEDS_PER_SWEEP = 20
BLOCK_SETTING = "ZORA_SWEEP_BLOCK"
WHOLE_RANGE = "all"
CHUNK_SEEDS = 10        # seeds per test, so no one test holds a worker for minutes (test-speed.md 3.3)


def sweep_block() -> str:
    return os.environ.get(BLOCK_SETTING, "0").strip() or "0"


def sweep_seeds(seeds: range) -> range:
    """This run's block of SEEDS: SEEDS_PER_SWEEP of them, or all with ZORA_SWEEP_BLOCK=all."""
    block = sweep_block()
    if block == WHOLE_RANGE or len(seeds) <= SEEDS_PER_SWEEP:
        return seeds
    blocks = -(-len(seeds) // SEEDS_PER_SWEEP)
    start = int(block) % blocks * SEEDS_PER_SWEEP
    return seeds[start:start + SEEDS_PER_SWEEP]


def chunks(seeds: range, size: int = CHUNK_SEEDS) -> list[range]:
    """SEEDS in runs of SIZE, one test each."""
    return [seeds[start:start + size] for start in range(0, len(seeds), size)]


def chunk_id(chunk: range) -> str:
    return f"seeds {chunk[0]}-{chunk[-1]}"
