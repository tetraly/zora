"""ZORA against a corpus: each component's estimate, its standard error and the
differences beyond sampling noise."""

import math
import statistics
from dataclasses import dataclass
from typing import Any

from zora.measure.checkpoints.registry import CHECKPOINTS
from zora.measure.checkpoints.summaries import Checkpoint, Component


def summarize(per_rom_values: list[list[Any]]) -> list[str]:
    """Every checkpoint's summary over the ROMs' values."""
    return [cp.summary.text(cp.summary.column([values[i] for values in per_rom_values]))
            for i, cp in enumerate(CHECKPOINTS)]




# --- comparison --------------------------------------------------------------------
#
# Each component's estimate over a sample of ROMs and its standard error under
# a normal approximation: a mean of per-ROM numbers (for 0/1 shares this is the
# binomial interval), or a ratio of sums whose error comes from the delta
# method. ROMs are the independent units in both cases.

@dataclass(frozen=True)
class Estimate:
    value: float
    stderr: float


@dataclass(frozen=True)
class Difference:
    checkpoint: Checkpoint
    component: str
    zora: Estimate
    corpus: Estimate

    @property
    def gap(self) -> float:
        return self.zora.value - self.corpus.value

    @property
    def stderr(self) -> float:
        return math.hypot(self.zora.stderr, self.corpus.stderr)

    def beyond_noise(self, z: float) -> bool:
        """The gap lies outside the z-score interval around zero. With no
        spread in either sample, any gap counts."""
        if self.stderr == 0:
            return self.gap != 0
        return abs(self.gap) > z * self.stderr


def estimate(components: list[Component]) -> Estimate | None:
    """None when a ratio has no cases in the sample."""
    n = len(components)
    if all(isinstance(c, tuple) for c in components):
        hits = [c[0] for c in components if isinstance(c, tuple)]
        cases = [c[1] for c in components if isinstance(c, tuple)]
        total_cases = sum(cases)
        if total_cases == 0:
            return None
        ratio = sum(hits) / total_cases
        residuals = sum((h - ratio * k) ** 2 for h, k in zip(hits, cases, strict=True))
        spread = math.sqrt(n / (n - 1) * residuals) / total_cases if n > 1 else 0.0
        return Estimate(ratio, spread)
    values = [float(c) for c in components if not isinstance(c, tuple)]
    spread = statistics.stdev(values) / math.sqrt(n) if n > 1 else 0.0
    return Estimate(statistics.mean(values), spread)


def compare(zora_values: list[list[Any]], corpus_values: list[list[Any]]) -> list[Difference]:
    """Every checkpoint component estimated on both samples (per-ROM value
    lists as measure_rom returns them)."""
    out = []
    for i, cp in enumerate(CHECKPOINTS):
        zora_parts = [cp.summary.components(value)
                      for value in cp.summary.column([values[i] for values in zora_values])]
        corpus_parts = [cp.summary.components(value)
                        for value in cp.summary.column([values[i] for values in corpus_values])]
        for name in zora_parts[0]:
            zora = estimate([parts[name] for parts in zora_parts])
            corpus = estimate([parts[name] for parts in corpus_parts])
            if zora is not None and corpus is not None:
                out.append(Difference(cp, name, zora, corpus))
    return out
