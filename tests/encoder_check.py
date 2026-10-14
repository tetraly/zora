"""The encoder check's pytest side (docs/design/test-speed.md 3.2 item 3; scripts/encoder_check.py).

A test that turns on Encode level data needs the private encoder, which a release tree does not
have: unless it skips without it, it passes here and fails in the release tree (74e4500). Guards
take several forms (a skipif mark, a branch on level_encoding.is_available(), cases made only
when it is available), so this checks behaviour rather than text:

- ZORA_ENCODER_RECORD=DIR: each test that reaches the encoder, through its one gateway
  level_encoding.require_available(), is written to DIR (one file per process, a line per test:
  the rootdir and the test's id). verify.sh sets it for its pytest run.
- ZORA_HIDE_LEVEL_ENCODING=1: the encoder is hidden, as in a release tree, before any test module
  is collected. scripts/encoder_check.py reruns the recorded tests so, and each must pass or skip.

tests/conftest.py loads this plugin; a run outside tests/ loads it with `-p tests.encoder_check`.
"""
import os
from pathlib import Path
from types import ModuleType

import pytest

from zora.rom import level_encoding

RECORD_ENV = "ZORA_ENCODER_RECORD"
HIDE_ENV = "ZORA_HIDE_LEVEL_ENCODING"
FIELD_SEPARATOR = "\t"

_running: list[pytest.Item] = []        # the test running in this process, while it runs
_reached: set[str] = set()              # its ids already written


def pytest_configure(config: pytest.Config) -> None:
    if os.environ.get(HIDE_ENV):
        level_encoding._ENCODER = None  # what a release tree has; is_available() reads it at call time
        return
    folder = os.environ.get(RECORD_ENV)
    if folder and level_encoding.is_available():
        worker = getattr(config, "workerinput", {}).get("workerid", "main")
        _record_into(Path(folder) / f"{worker}-{os.getpid()}.txt")


def _record_into(path: Path) -> None:
    """Wrap the encoder's gateway: every module calls it as level_encoding.require_available()."""
    path.parent.mkdir(parents=True, exist_ok=True)
    gateway = level_encoding.require_available

    def require_available() -> ModuleType:
        if _running and _running[-1].nodeid not in _reached:
            item = _running[-1]
            _reached.add(item.nodeid)
            with path.open("a", encoding="utf-8") as record:
                record.write(f"{item.config.rootpath}{FIELD_SEPARATOR}{item.nodeid}\n")
        return gateway()
    level_encoding.require_available = require_available


@pytest.hookimpl(wrapper=True)
def pytest_runtest_protocol(item: pytest.Item) -> object:
    """Setup, call and teardown: a fixture may reach the encoder for its test."""
    _running.append(item)
    try:
        return (yield)
    finally:
        _running.pop()


def read_records(folder: Path) -> dict[str, list[str]]:
    """The recorded tests, by rootdir, each id once, in a stable order."""
    by_root: dict[str, set[str]] = {}
    for path in sorted(folder.glob("*.txt")) if folder.is_dir() else []:
        for line in path.read_text(encoding="utf-8").splitlines():
            root, _, nodeid = line.partition(FIELD_SEPARATOR)
            by_root.setdefault(root, set()).add(nodeid)
    return {root: sorted(ids) for root, ids in sorted(by_root.items())}
