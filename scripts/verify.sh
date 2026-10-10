#!/bin/sh
# Pre-commit verification (AGENTS.md "Verification"). Run from the repo root:
#
#   sh scripts/verify.sh          zora/'s import rules, tests, type check, ruff on zora/ and its
#                                 sibling packages, output hashes of 20 seeds
#   sh scripts/verify.sh REV      ... and compare the output with revision REV
#                                 (exit 1 if any seed's ROM differs)
#
# The comparison exports REV's committed files (git archive) into temp/verify/base
# and hashes them with this checkout's scripts/output_hash.py; it works in any git
# checkout of ZORA.
#
# Local settings: if verify.env exists at the repo root (git-ignored), its
# VAR=value lines are exported first; for example ZORA_CORPUS=DIR, the folder of
# finished ROMs the corpus tests read (they skip without it).
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

# Without verify.env (and no ZORA_CORPUS in the environment) the corpus tests skip.
# Say so before the run and again at the end, where it is not scrolled away.
CORPUS_WARNING=""
if [ ! -f verify.env ] && [ -z "$ZORA_CORPUS" ]; then
    CORPUS_WARNING="verify: WARNING: verify.env is missing, so the corpus tests are SKIPPED (set ZORA_CORPUS=DIR in verify.env; see the comment at the top of scripts/verify.sh)"
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
python3 -m ruff check zora zora_export zora_measure zora_web
python3 scripts/output_hash.py --seeds $SEEDS --json $OUT/head.json

if [ -n "$1" ]; then
    rm -rf $OUT/base
    mkdir -p $OUT/base
    trap 'rm -rf $OUT/base; [ -z "$CORPUS_WARNING" ] || printf "\n*** %s ***\n" "$CORPUS_WARNING" >&2' EXIT
    git archive "$1" | tar -x -C $OUT/base
    echo "== output at $1"
    python3 scripts/output_hash.py --seeds $SEEDS --code $OUT/base --json $OUT/base.json
    echo "== $1 vs working tree"
    python3 scripts/output_hash.py --compare $OUT/base.json $OUT/head.json
fi
