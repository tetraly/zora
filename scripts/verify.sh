#!/bin/sh
# The fast verification tier, before every commit (AGENTS.md "Verification";
# docs/design/test-speed.md 3.2). Run from the repo root:
#
#   sh scripts/verify.sh          zora/'s import rules, the release scan, the tests (but seeds 2
#                                 and up of seed sweeps, and the slow suite), the encoder check,
#                                 type check, ruff, and the output (20-seed hashes and the ROM
#                                 matrix) against the parent commit. It ends on the comparison's
#                                 verdict: "output identical to <parent>" or "output DIFFERS
#                                 from <parent>" (a feature's change, reported, not a failure)
#   sh scripts/verify.sh REV      ... compared with REV instead, strictly: exit 1 if any output
#                                 differs (a refactor: REV "parent" is the parent itself)
#
# Any run exits non-zero if the comparison can't be made (REV unknown, or its output can't be
# made). The full tier, scripts/verify_full.sh, runs this with ZORA_VERIFY_TIER=full (every
# seed), then the slow suite, the release-tree checks and the comparison with the last release.
#
# scripts/compare_revision.py makes the comparison: it exports REV's committed files into
# temp/verify/base and hashes them with this checkout's scripts/output_hash.py, or reuses their
# hashes from temp/verify/base-cache/ when nothing they depend on changed. In a clean copy
# (scripts/clean_copy.py) REV is resolved in the checkout the copy was made from
# (ZORA_SOURCE_REPO in the copy's verify.env), never in the copy's one-commit repository, and
# the parent is the commit the copy was made from (ZORA_COPY_REVISION).
#
# Local settings: if verify.env exists at the repo root (git-ignored), its
# VAR=value lines are exported first; for example ZORA_CORPORA=DIR, the folder that
# holds the measurement corpora (zora_measure/corpora.py says where it defaults to). The
# corpus tests read its clean/final and skip without it.
set -e

# Progress (zora_measure/progress.py): the run is a job that says at least once a minute where it
# is and how long is left; inside the full tier it is that job's first step.
if [ -z "$ZORA_JOB_ID" ]; then
    exec python3 scripts/job.py run --name "verify.sh (fast tier)" -- sh "$0" "$@"
fi
if [ "$ZORA_VERIFY_TIER" = "full" ]; then STEP_LEVEL=substep; else STEP_LEVEL=step; fi
progress_step() {
    python3 scripts/job.py $STEP_LEVEL "$1"
}

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

# The comparison: with REV given, strict; without, the parent, reported
REV=${1:-parent}
# An unknown REV stops the run now, before the suite, rather than after it
python3 scripts/compare_revision.py "$REV" --resolve-only

# The fast tier leaves seeds 2 and up of seed sweeps to the full tier (tests/conftest.py)
if [ "$ZORA_VERIFY_TIER" = "full" ]; then
    SELECTION="not slow"
else
    SELECTION="not slow and not full_tier"
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
progress_step "zora/'s import rules and the release scan"
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
# The encoder check (scripts/encoder_check.py): the tests that reach the private level encoder
# are recorded, then rerun without it, as in a release tree; each must pass or skip.
progress_step "tests"
ENCODER_RECORD=$OUT/encoder-record
rm -rf "$ENCODER_RECORD"
export ZORA_ENCODER_RECORD="$ENCODER_RECORD"
python3 -m pytest tests -q -m "$SELECTION" $PYTEST_WORKERS
unset ZORA_ENCODER_RECORD
progress_step "the encoder check"
python3 scripts/encoder_check.py "$ENCODER_RECORD"
# --no-incremental: the incremental cache has reported success on stale code
progress_step "type check and ruff"
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
progress_step "the output against $REV"
python3 scripts/output_hash.py --seeds $SEEDS --json $OUT/head.json

echo "== output at $REV vs this checkout"
set +e
python3 scripts/compare_revision.py "$REV" --seeds $SEEDS --head-hashes $OUT/head.json | tee $OUT/compare.txt
COMPARED=$?
set -e
# tee's status is the pipeline's; compare_revision's verdict line says which it was
VERDICT=$(tail -n 1 $OUT/compare.txt)
case "$VERDICT" in
    "compare_revision: output identical to "*) COMPARED=0 ;;
    "compare_revision: output DIFFERS from "*) COMPARED=1 ;;
    *) COMPARED=2 ;;
esac

if [ "$ZORA_VERIFY_TIER" != "full" ]; then
    echo
    echo "verify: fast tier. Not checked here: seeds 2 and up of seed sweeps (tests marked full_tier),"
    echo "verify: the slow suite, the release-tree checks and the output against the last release."
    echo "verify: Before reporting a feature done, before merging and in release runs: sh scripts/verify_full.sh"
fi
if [ $COMPARED -eq 2 ]; then
    echo "verify: FAILED: no comparison was made (above)" >&2
    exit 2
fi
echo "$VERDICT"
# With REV given the comparison is strict; with the parent, a difference is reported only
if [ $COMPARED -eq 1 ] && [ -n "$1" ]; then
    exit 1
fi
