#!/bin/sh
# Pre-commit verification (AGENTS.md "Verification"). Run from the repo root:
#
#   sh scripts/verify.sh          zora/'s import rules, tests, type check, ruff on zora/ and its
#                                 sibling packages, output hashes of 20 seeds
#   sh scripts/verify.sh REV      ... and compare the output (20-seed hashes and the ROM
#                                 matrix) with revision REV: exit 1 if any differs, and a
#                                 non-zero exit if REV is unknown or its output can't be made
#
# scripts/compare_revision.py makes the comparison: it exports REV's committed files into
# temp/verify/base and hashes them with this checkout's scripts/output_hash.py. In a clean
# copy (scripts/clean_copy.py) REV is resolved in the checkout the copy was made from
# (ZORA_SOURCE_REPO in the copy's verify.env), never in the copy's one-commit repository.
#
# Local settings: if verify.env exists at the repo root (git-ignored), its
# VAR=value lines are exported first; for example ZORA_CORPORA=DIR, the folder that
# holds the measurement corpora (zora_measure/corpora.py says where it defaults to). The
# corpus tests read its clean/final and skip without it.
set -e

# One full suite at a time on this checkout (tests/suite_lock.py): several sessions share it,
# and suites run together oversubscribe the machine. If another suite holds the lock, this
# says so and waits; then the whole run holds it, its pytest step included.
if [ -z "$ZORA_SUITE_LOCK_HELD" ]; then
    exec python3 tests/suite_lock.py sh "$0" "$@"
fi

SEEDS=20
OUT=temp/verify

if [ -f verify.env ]; then
    set -a
    . ./verify.env
    set +a
fi

# An unknown REV stops the run now, before the suite, rather than after it
if [ -n "$1" ]; then
    python3 scripts/compare_revision.py "$1" --resolve-only
fi

# Without the MVP baseline corpus (ZORA_CORPORA's clean/final) the corpus tests skip.
# Say so before the run and again at the end, where it is not scrolled away.
CORPUS_WARNING=""
CLEAN_CORPUS=$(python3 -c "from zora_measure.corpora import CLEAN, corpus; print(corpus(CLEAN))")
if [ ! -d "$CLEAN_CORPUS" ]; then
    CORPUS_WARNING="verify: WARNING: $CLEAN_CORPUS is missing, so the corpus tests are SKIPPED (set ZORA_CORPORA=DIR in verify.env; see the comment at the top of scripts/verify.sh)"
    printf '\n*** %s ***\n\n' "$CORPUS_WARNING" >&2
    trap 'printf "\n*** %s ***\n" "$CORPUS_WARNING" >&2' EXIT
fi

# private/ holds optional modules that are never committed (.gitignore).
if [ -n "$(git ls-files private)" ]; then
    echo "verify: files under private/ are tracked; untrack them (git rm --cached)" >&2
    exit 1
fi

# zora/ is generation only: it never imports its siblings zora_export/, zora_measure/
# or zora_web/, and imports itself only relatively (Archipelago copies zora/ alone, under
# another name; docs/packaging.md "Packages").
python3 scripts/check_imports.py

# The release's mention and original-game-byte checks (scripts/make_release.py's own) on the files
# a release would ship: a hit fails here, at commit time, rather than at the release. A released
# checkout has no release/ folder to scan against.
if [ -f release/allowlist.txt ]; then
    python3 scripts/release_scan.py
fi

# pytest-xdist (the "test" extra in pyproject.toml) runs the suite in parallel, one
# worker per core (tests/conftest.py, pytest_xdist_auto_num_workers): the suite lock
# above keeps other full suites off the machine meanwhile. Without it the run falls
# back to serial.
if python3 -c "import xdist" 2>/dev/null; then
    PYTEST_WORKERS="-n auto"
else
    echo "verify: pytest-xdist not installed (pip install -e '.[test]'); running the tests serially" >&2
    PYTEST_WORKERS=""
fi
python3 -m pytest tests -q $PYTEST_WORKERS
# --no-incremental: the incremental cache has reported success on stale code
python3 -m mypy --no-incremental
# Archipelago's ruff settings (pyproject.toml; docs/style-archipelago.md): any finding fails
# The ruff release named in pyproject.toml: another release checks other rules (0.15 left
# ISC004 to preview), so a pass under it proves less
RUFF_WANTED=$(sed -n 's/^# Ruff version: \([0-9.]*\).*/\1/p' pyproject.toml)
RUFF_INSTALLED=$(python3 -m ruff --version | sed 's/^ruff //')
if [ "$RUFF_INSTALLED" != "$RUFF_WANTED" ]; then
    echo "verify: WARNING: ruff $RUFF_INSTALLED is installed, pyproject.toml names $RUFF_WANTED (pip install ruff==$RUFF_WANTED)" >&2
fi
python3 -m ruff check zora zora_export zora_measure zora_web
python3 scripts/output_hash.py --seeds $SEEDS --json $OUT/head.json

if [ -n "$1" ]; then
    echo "== output at $1 vs this checkout"
    python3 scripts/compare_revision.py "$1" --seeds $SEEDS --head-hashes $OUT/head.json
fi
