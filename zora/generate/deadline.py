"""A caller's time limit on generation (the web page's 15 s, owner decision 2026-10-28). Generation
checks it between attempts and between late-gate attempts, and stops with GenerationStopped once it
has passed. Stopping only ends the run: a seed that finishes in time is the same ROM with or without
a limit, so generation stays deterministic (AGENTS.md "Output and versions"). Without stop_after
nothing is checked; Archipelago and the scripts never set one."""
from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass


class GenerationStopped(RuntimeError):
    """The caller's time limit passed before a seed was accepted."""


@dataclass
class _Limit:
    """The time.monotonic() value generation stops at; None when no caller set one."""
    deadline: float | None = None


_LIMIT = _Limit()


@contextmanager
def stop_after(seconds: float) -> Iterator[None]:
    """Generation inside the block stops once SECONDS have passed (GenerationStopped)."""
    previous = _LIMIT.deadline
    _LIMIT.deadline = time.monotonic() + seconds
    try:
        yield
    finally:
        _LIMIT.deadline = previous


def check_deadline() -> None:
    """Raise GenerationStopped when the caller's time limit has passed."""
    if _LIMIT.deadline is not None and time.monotonic() > _LIMIT.deadline:
        raise GenerationStopped("generation stopped: the time limit passed before a seed was accepted")
