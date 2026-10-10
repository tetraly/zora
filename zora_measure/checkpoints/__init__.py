"""The spec's Check lines as measurements: what each Check counts on a
finished ROM, the figure the spec states, and where it states it.

Unlike zora_measure/checks.py (pass/fail invariants per ROM), a checkpoint measures a
figure per ROM and summarizes it over many ROMs, so ZORA's output and a
corpus can be set beside the spec's number. scripts/checkpoints.py runs the
registry. Only finished-ROM figures live here; figures of the shape stage or
gate entry need generation internals (scripts/metrics.py).

To add a checkpoint: write a per-ROM function over a GameWorld in the spec
area's module and append a Checkpoint to registry.CHECKPOINTS with the spec's figure copied verbatim and a
Summary: the text the table prints, and the per-ROM numeric components that
scripts/compare_corpus.py tests for differences larger than sampling noise
(see "comparison" at the end).
"""
