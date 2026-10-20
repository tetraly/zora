#!/bin/sh
# Verification before a commit (AGENTS.md "Verification"; owner decision, 2026-10-16: commit after
# quick checks, test in batches, trace failures afterwards). Run from the repo root:
#
#   sh scripts/verify.sh          THE QUICK CHECK, before every commit: no suite lock, at most 2
#                                 workers, normally 3-5 minutes, never queued behind anyone. The
#                                 static checks (scripts/verify_static.sh: zora/'s import rules, the
#                                 release scan, mypy, ruff), then a small selection of fast tests
#                                 (scripts/affected_tests.py --quick: the test files changed or
#                                 directly importing or naming a changed file, capped at about a
#                                 minute and a half of recorded test time), then the output (20-seed
#                                 hashes and the ROM matrix) against the parent commit, with the
#                                 hash cache. It ends on the comparison's verdict: "output identical
#                                 to <parent>" or "output DIFFERS from <parent>" (a feature's
#                                 change, reported, not a failure). The full suite runs in the
#                                 batch run (scripts/batch_run.py), not here.
#   sh scripts/verify.sh REV      ... compared with REV instead, strictly: exit 1 if any output
#                                 differs (a refactor: REV "parent" is the parent itself)
#   --fast-suite                  the old fast tier instead: every fast test (but seeds 2 and up of
#                                 seed sweeps) under the suite lock at one worker per core, the
#                                 encoder check, and the comparison at every core. The batch run
#                                 runs it (scripts/verify_full.sh); a session needs it only when
#                                 the owner asks.
#   --all-failures                run every selected test rather than stopping at the first failure
#
# A static failure stops the run before any test. Any run exits non-zero if the comparison can't
# be made (REV unknown, or its output can't be made); an unknown REV stops it before anything else.
# A quick check that passes on a tree that is exactly a commit (nothing uncommitted, or a clean
# copy without --add) records that tree (scripts/full_tier.py quick-stamp), which the release
# gate's relaxation needs (docs/releasing.md).
#
# The tests a change selects are the working tree's changes against HEAD; in a clean copy
# (scripts/clean_copy.py) its --add paths. In a checkout others are changing too, check your own
# work in a clean copy: `python3 scripts/clean_copy.py build temp/NAME-copy --add PATH ...`, then
# `python3 scripts/clean_copy.py run temp/NAME-copy sh scripts/verify.sh`.
#
# scripts/compare_revision.py makes the comparison: it exports REV's committed files into
# temp/verify/base and hashes them with this checkout's scripts/output_hash.py, or reuses their
# hashes from temp/verify/base-cache/ when nothing they depend on changed (a quick check stores
# its own hashes there for its working tree, so after committing exactly what it checked the next
# one finds its parent's). In a clean copy REV is resolved in the checkout the copy was made from
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
    case " $* " in
        *" --fast-suite "*) JOB_NAME="verify.sh (fast tier)" ;;
        *) JOB_NAME="verify.sh (quick check)" ;;
    esac
    exec python3 scripts/job.py run --name "$JOB_NAME" -- sh "$0" "$@"
fi
if [ "$ZORA_VERIFY_TIER" = "full" ]; then STEP_LEVEL=substep; else STEP_LEVEL=step; fi
progress_step() {
    python3 scripts/job.py $STEP_LEVEL "$1"
}

# The options, wherever they stand; what is left is REV
FAST_SUITE=""
ALL_FAILURES=""
for argument do
    shift
    case "$argument" in
        --fast-suite) FAST_SUITE=1 ;;
        --all-failures) ALL_FAILURES=1 ;;
        --precheck) echo "verify: --precheck is gone: the quick check, plain sh scripts/verify.sh, replaced it" >&2; exit 2 ;;
        -*) echo "verify: unknown option $argument (see the top of scripts/verify.sh)" >&2; exit 2 ;;
        *) set -- "$@" "$argument" ;;
    esac
done
if [ -n "$ALL_FAILURES" ]; then MAXFAIL=""; else MAXFAIL="--maxfail=1"; fi

SEEDS=20
OUT=temp/verify
mkdir -p $OUT

if [ -f verify.env ]; then
    set -a
    . ./verify.env
    set +a
fi

# Before the lock: an unknown REV, then any static failure, stops the run in seconds, without
# queuing behind another session's suite. The full tier ran the static checks before its own
# lock; this job and folder are marked so its inner run doesn't repeat them.
STATIC_MARK="$ZORA_JOB_ID $(pwd -P)"
if [ -z "$ZORA_SUITE_LOCK_HELD" ] || [ "$ZORA_VERIFY_STATIC_DONE" != "$STATIC_MARK" ]; then
    python3 scripts/compare_revision.py "${1:-parent}" --resolve-only
    if [ "$ZORA_VERIFY_STATIC_DONE" != "$STATIC_MARK" ]; then
        progress_step "static checks"
        sh scripts/verify_static.sh
        export ZORA_VERIFY_STATIC_DONE="$STATIC_MARK"
    fi
fi

# pytest-xdist (the "test" extra in pyproject.toml) runs the suite in parallel
if python3 -c "import xdist" 2>/dev/null; then HAVE_XDIST=1; else HAVE_XDIST=""; fi

# The comparison: with REV given, strict; without, the parent, reported
REV=${1:-parent}

# compare_revision's verdict, its last line: COMPARED 0 identical, 1 differs, 2 no comparison
compare_output() {
    set +e
    # ZORA_VERIFY_MATRIX_JOBS: only the first N matrix ROMs (tests/test_verify_order.py shortens it)
    python3 scripts/compare_revision.py "$REV" --seeds $SEEDS ${ZORA_VERIFY_MATRIX_JOBS:+--matrix-jobs "$ZORA_VERIFY_MATRIX_JOBS"} \
        "$@" | tee $OUT/compare.txt
    set -e
    VERDICT=$(tail -n 1 $OUT/compare.txt)
    case "$VERDICT" in
        "compare_revision: output identical to "*) COMPARED=0 ;;
        "compare_revision: output DIFFERS from "*) COMPARED=1 ;;
        *) COMPARED=2 ;;
    esac
}

# The end of both checks: the verdict, strict with REV given
finish() {
    if [ $COMPARED -eq 2 ]; then
        echo "verify: FAILED: no comparison was made (above)" >&2
        exit 2
    fi
    echo "$VERDICT"
    if [ $COMPARED -eq 1 ] && [ -n "$1" ]; then
        exit 1
    fi
}

if [ -z "$FAST_SUITE" ] && [ "$ZORA_VERIFY_TIER" != "full" ]; then
    # The quick check: no suite lock, at most 2 workers (owner rule: beside a held lock, test runs
    # use at most 2; tests/conftest.py takes no lock for these), so it never queues
    progress_step "the selected tests"
    SELECTION=$OUT/quick-selection.txt
    python3 scripts/affected_tests.py --quick
    python3 scripts/affected_tests.py --quick --ids > $SELECTION
    COUNT=$(grep -c . $SELECTION || true)
    if [ "$COUNT" -gt 0 ]; then
        if [ -n "$HAVE_XDIST" ]; then WORKERS="-n 2"; else WORKERS=""; fi
        # shellcheck disable=SC2046 # one test path a line, without spaces
        python3 -m pytest -q -m "not slow and not full_tier" $WORKERS $MAXFAIL $(cat $SELECTION) || {
            echo "verify: FAILED in the tests above" >&2
            exit 1
        }
    fi
    progress_step "the output against $REV"
    echo "== output at $REV vs this checkout"
    compare_output --workers 2 --no-lock
    echo
    echo "verify: quick check: the static checks, the fast tests of $COUNT selected file(s) and the output."
    echo "verify: THE FULL SUITE RUNS IN THE BATCH RUN (scripts/batch_run.py), not here: every other test,"
    echo "verify: the slow suite, the encoder check, the release-tree checks and every seed."
    if [ $COMPARED -ne 2 ] && { [ $COMPARED -eq 0 ] || [ -z "$1" ]; }; then
        python3 scripts/full_tier.py quick-stamp
    fi
    finish "$1"
    exit 0
fi

# One full suite at a time on this checkout (tests/suite_lock.py): several sessions share it,
# and suites run together oversubscribe the machine. If another suite holds the lock, this
# says so and waits; then the whole run holds it, its pytest step included.
if [ -z "$ZORA_SUITE_LOCK_HELD" ]; then
    exec python3 tests/suite_lock.py sh "$0" --fast-suite ${ALL_FAILURES:+--all-failures} "$@"
fi

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

# One worker per core (tests/conftest.py, pytest_xdist_auto_num_workers): the suite lock above
# keeps other full suites off the machine meanwhile. Without xdist the run falls back to serial.
if [ -n "$HAVE_XDIST" ]; then
    PYTEST_WORKERS="-n auto"
else
    echo "verify: pytest-xdist not installed (pip install -e '.[test]'); running the tests serially" >&2
    PYTEST_WORKERS=""
fi
# The encoder check (scripts/encoder_check.py): the tests that reach the private level encoder
# are recorded, then rerun without it, as in a release tree; each must pass or skip.
# The run stops at the first failing test (--maxfail=1) unless --all-failures asks for them all.
progress_step "tests"
ENCODER_RECORD=$OUT/encoder-record
rm -rf "$ENCODER_RECORD"
export ZORA_ENCODER_RECORD="$ENCODER_RECORD"
python3 -m pytest tests -q -m "$SELECTION" $PYTEST_WORKERS $MAXFAIL || {
    if [ -n "$MAXFAIL" ]; then
        echo "verify: FAILED in the tests: stopped at the first failure (above); --all-failures lists them all" >&2
    else
        echo "verify: FAILED in the tests (above)" >&2
    fi
    exit 1
}
unset ZORA_ENCODER_RECORD
progress_step "the encoder check"
python3 scripts/encoder_check.py "$ENCODER_RECORD"
progress_step "the output against $REV"
python3 scripts/output_hash.py --seeds $SEEDS --json $OUT/head.json
echo "== output at $REV vs this checkout"
compare_output --head-hashes $OUT/head.json

if [ "$ZORA_VERIFY_TIER" != "full" ]; then
    echo
    echo "verify: fast suite. Not checked here: seeds 2 and up of seed sweeps (tests marked full_tier),"
    echo "verify: the slow suite, the release-tree checks and the output against the last release:"
    echo "verify: the batch run (scripts/batch_run.py) runs them."
fi
finish "$1"
