"""scripts/release_scan.py: make_release.py's mention and original-game-byte checks at commit time
(scripts/verify.sh runs it before the suite). A planted mention or a planted run of PRG0 bytes in a
file the allowlist releases fails the scan; the same in a file it leaves out does not. The checkout
scanned is a throwaway git repository in tmp_path with its own allowlist.
"""
import importlib.util
import os
import re
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

from zora.rom.base_rom import BASE_ROM_PATH, PRG1_ROM_PATH
from zora.version import ZORA_VERSION, player_version

REPO = Path(__file__).resolve().parent.parent
SCAN = REPO / "scripts" / "release_scan.py"
# A run of the ROM file's bytes (offset as the release check reports it) that is not filler; the
# release check found it written in a released file once
PLANTED_RUN_OFFSET, PLANTED_RUN_LENGTH = 0x1EF76, 11
PRG1_ONLY_OFFSET = 0x1A2D3
# Joined at run time: this file is released too, and the scan must not find the mention in it
PRIVATE_REPO = "-".join(("zora", "private"))
PLANTED_MENTION = f"built beside {PRIVATE_REPO}"

pytestmark = [pytest.mark.skipif(not BASE_ROM_PATH.exists(), reason="no base ROM"),
              # a release leaves out the scan and make_release.py (release/allowlist.txt)
              pytest.mark.skipif(not (SCAN.exists() and (REPO / "scripts" / "make_release.py").exists()),
                                 reason="no release scripts here")]


def _git(root: Path, *args: str) -> None:
    environment = {name: value for name, value in os.environ.items() if not name.startswith("GIT_")}
    subprocess.run(["git", "-C", str(root), "-c", "user.name=test", "-c", "user.email=test@example.invalid",
                    "-c", "commit.gpgsign=false", *args], check=True, capture_output=True, env=environment)


@pytest.fixture
def checkout(tmp_path: Path) -> Path:
    """A clean checkout: a released README and notes/, and a left-out internal/ folder."""
    (tmp_path / "release").mkdir()
    (tmp_path / "release" / "allowlist.txt").write_text("README.md\nnotes/\n")
    (tmp_path / "README.md").write_text("# A game\n")
    (tmp_path / "notes").mkdir()
    (tmp_path / "notes" / "plain.md").write_text("Nothing to see.\n")
    _git(tmp_path, "init", "--quiet")
    _git(tmp_path, "add", "--all")
    _git(tmp_path, "commit", "--quiet", "--no-verify", "-m", "clean")
    return tmp_path


def _scan(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(SCAN), "--root", str(root)], capture_output=True, text=True,
                          check=False)


def _planted_bytes() -> str:
    run = BASE_ROM_PATH.read_bytes()[PLANTED_RUN_OFFSET:PLANTED_RUN_OFFSET + PLANTED_RUN_LENGTH]
    return f'TABLE = bytes.fromhex("{run.hex()}")\n'


def test_a_clean_checkout_passes(checkout: Path) -> None:
    done = _scan(checkout)
    assert done.returncode == 0, done.stdout + done.stderr


def test_a_planted_mention_fails(checkout: Path) -> None:
    (checkout / "notes" / "new.md").write_text(f"This was {PLANTED_MENTION}.\n")     # new, not yet added
    done = _scan(checkout)
    assert done.returncode == 1
    assert re.search(rf"notes/new\.md:1: the private repo: .*{PRIVATE_REPO}", done.stdout)


def test_a_planted_byte_run_fails(checkout: Path) -> None:
    (checkout / "notes" / "data.py").write_text(_planted_bytes())
    done = _scan(checkout)
    assert done.returncode == 1
    assert f"notes/data.py:1: {PLANTED_RUN_LENGTH} bytes = PRG0" in done.stdout


@pytest.mark.skipif(not PRG1_ROM_PATH.exists(), reason="no PRG1 ROM")
def test_a_planted_run_of_prg1_only_bytes_fails(checkout: Path) -> None:
    """PRG1's game-over warning records (its transfer buffers before the moved story screen),
    which PRG0 does not have."""
    run = PRG1_ROM_PATH.read_bytes()[PRG1_ONLY_OFFSET:PRG1_ONLY_OFFSET + PLANTED_RUN_LENGTH]
    assert BASE_ROM_PATH.read_bytes().find(run) < 0
    (checkout / "notes" / "data.py").write_text(f'TABLE = bytes.fromhex("{run.hex()}")\n')
    done = _scan(checkout)
    assert done.returncode == 1
    assert f"notes/data.py:1: {PLANTED_RUN_LENGTH} bytes = PRG1" in done.stdout


def test_files_a_release_leaves_out_are_not_scanned(checkout: Path) -> None:
    (checkout / "internal").mkdir()
    (checkout / "internal" / "notes.md").write_text(f"This was {PLANTED_MENTION}.\n")
    (checkout / "internal" / "data.py").write_text(_planted_bytes())
    done = _scan(checkout)
    assert done.returncode == 0, done.stdout + done.stderr


def test_verify_scans_before_the_suite() -> None:
    """A hit fails verify (set -e) before the long test run, not after it."""
    verify = (REPO / "scripts" / "verify.sh").read_text().splitlines()
    scan = next(n for n, line in enumerate(verify) if line.strip() == "python3 scripts/release_scan.py")
    assert verify[scan - 1].strip() == "if [ -f release/allowlist.txt ]; then"
    suite = next(n for n, line in enumerate(verify) if line.strip().startswith("python3 -m pytest"))
    assert scan < suite


def _make_release() -> ModuleType:
    spec = importlib.util.spec_from_file_location("make_release", REPO / "scripts" / "make_release.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["make_release"] = module            # its dataclasses look their module up
    spec.loader.exec_module(module)
    return module


def _changelog(entry: str) -> str:
    """The working changelog's shape: its own header (which may explain "Unreleased"), this version's
    entry, an older one."""
    return (f"# ZORA changelog\n\nLines go under an Unreleased heading until the release.\n\n"
            f"## {player_version(ZORA_VERSION)} (2026-10-11)\n\n{entry}\n\n## 0.1 (2020-01-01)\n\n- Old.\n")


def test_the_released_changelog_never_says_unreleased() -> None:
    """Owner requirement: not even the public header's empty heading."""
    release = _make_release()
    shipped = release.released_changelog(_changelog("- A change."), ZORA_VERSION, "2026-10-11")
    assert release.check_unreleased(shipped).passed, shipped
    assert release.check_unreleased("## 2.0\n\n## Unreleased\n").hits == ["docs/CHANGELOG.md:3: ## Unreleased"]


@pytest.mark.parametrize(("entry", "passes"), [("- A change.", True), ("- A change, still unreleased.", False)])
def test_the_scan_refuses_a_shipped_unreleased(checkout: Path, entry: str, passes: bool) -> None:
    (checkout / "release" / "allowlist.txt").write_text("README.md\nnotes/\ndocs/CHANGELOG.md\n")
    (checkout / "docs").mkdir()
    (checkout / "docs" / "CHANGELOG.md").write_text(_changelog(entry))
    done = _scan(checkout)
    assert (done.returncode == 0) == passes, done.stdout + done.stderr
    assert ("[FAIL] docs/CHANGELOG.md as released never says Unreleased" in done.stdout) != passes
