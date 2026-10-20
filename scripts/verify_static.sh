#!/bin/sh
# The static checks of both verify tiers (AGENTS.md "Verification"), run first, before a tier
# queues for the suite lock: a one-line type error fails in seconds, not after a wait for the lock
# and the whole suite. scripts/verify.sh and scripts/verify_full.sh run it; run from the repo root:
#
#   sh scripts/verify_static.sh       files under private/ untracked, zora/'s import rules, the
#                                     release scan, mypy and ruff (about 6 s)
#
# The first failure stops it: exit 1 after a line naming the check, so a tier never queues for
# the lock or runs a test after it.
set -e

fail() {
    echo "verify: FAILED a static check: $1. Nothing else ran: no wait for the suite lock, no tests." >&2
    exit 1
}

# private/ holds optional modules that are never committed (.gitignore).
if [ -n "$(git ls-files private)" ]; then
    echo "verify: files under private/ are tracked; untrack them (git rm --cached)" >&2
    fail "files under private/ are tracked"
fi

# zora/ is generation only: it never imports its siblings zora_export/, zora_measure/
# or zora_web/, and imports itself only relatively (Archipelago copies zora/ alone, under
# another name; docs/packaging.md "Packages").
python3 scripts/check_imports.py || fail "zora/'s import rules (scripts/check_imports.py)"

# The release's mention and original-game-byte checks (scripts/make_release.py's own) on the files
# a release would ship: a hit fails here, at commit time, rather than at the release. A released
# checkout has no release/ folder to scan against.
if [ -f release/allowlist.txt ]; then
    python3 scripts/release_scan.py || fail "the release scan (scripts/release_scan.py)"
fi

# --no-incremental: the incremental cache has reported success on stale code. The files are
# pyproject.toml's list, those that exist: a release tree leaves some of the listed scripts out
# (release/allowlist.txt), and mypy refuses a listed file it can't read.
MYPY_FILES=$(python3 -c "
import tomllib
from pathlib import Path
print(' '.join(name for name in tomllib.loads(Path('pyproject.toml').read_text())['tool']['mypy']['files']
               if Path(name).exists()))")
# shellcheck disable=SC2086 # the paths hold no spaces
python3 -m mypy --no-incremental $MYPY_FILES || fail "the type check (mypy --no-incremental)"

# Archipelago's ruff settings (pyproject.toml; docs/style-archipelago.md): any finding fails
# The ruff release named in pyproject.toml: another release checks other rules (0.15 left
# ISC004 to preview), so a pass under it proves less
RUFF_WANTED=$(sed -n 's/^# Ruff version: \([0-9.]*\).*/\1/p' pyproject.toml)
RUFF_INSTALLED=$(python3 -m ruff --version | sed 's/^ruff //')
if [ "$RUFF_INSTALLED" != "$RUFF_WANTED" ]; then
    echo "verify: WARNING: ruff $RUFF_INSTALLED is installed, pyproject.toml names $RUFF_WANTED (pip install ruff==$RUFF_WANTED)" >&2
fi
python3 -m ruff check zora zora_export zora_measure zora_web || fail "ruff"
echo "verify: static checks passed (private/ untracked, import rules, release scan, mypy, ruff)"
