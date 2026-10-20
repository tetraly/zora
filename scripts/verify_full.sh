#!/bin/sh
# The full verification tier, the batch run's checks (AGENTS.md "Verification"; docs/design/
# test-speed.md 3.2): scripts/batch_run.py runs it on main once or twice a day, in a clean copy of
# one commit (scripts/clean_copy.py), which it then stamps, while sessions keep committing:
#
#   sh scripts/verify_full.sh         every check of the fast tier (scripts/verify.sh) with every
#                                     seed, the slow suite, the release-tree checks
#                                     (scripts/make_release.py --dry-run: the suite without the
#                                     private module, the patch data, the wheel and the site) and
#                                     the output against the last release (listed, not a failure)
#   sh scripts/verify_full.sh REV     ... with the fast tier's comparison strict against REV
#   --all-failures                    run every test and every step rather than stopping at the first
#                                     failure (the batch run: the whole list, to trace each failure)
#
# The static checks (scripts/verify_static.sh: import rules, release scan, mypy, ruff) run first,
# before it queues for the suite lock, and an unknown REV stops it before them: either failure
# ends the run in seconds, without the lock or a test.
#
# When every check passes on a tree that is exactly a commit, scripts/full_tier.py stamps it
# (temp/verify/full-tier/ in the source checkout); scripts/make_release.py requires the stamp.
set -e

# Progress (zora_measure/progress.py): the run is a job that says at least once a minute which step
# it is on, the test count of the pytest run inside it, and how long is left.
if [ -z "$ZORA_JOB_ID" ]; then
    exec python3 scripts/job.py run --name "verify_full.sh (full tier)" -- sh "$0" "$@"
fi

ALL_FAILURES=""
for argument do
    shift
    case "$argument" in
        --all-failures) ALL_FAILURES=1 ;;
        -*) echo "verify_full: unknown option $argument (see the top of scripts/verify_full.sh)" >&2; exit 2 ;;
        *) set -- "$@" "$argument" ;;
    esac
done
if [ -n "$ALL_FAILURES" ]; then MAXFAIL=""; else MAXFAIL="--maxfail=1"; fi
if [ -f verify.env ]; then
    set -a
    . ./verify.env
    set +a
fi

# Before the lock: an unknown REV, then any static failure, ends the run in seconds. The mark
# (this job, this folder) tells scripts/verify.sh inside not to repeat the static checks.
STATIC_MARK="$ZORA_JOB_ID $(pwd -P)"
if [ "$ZORA_VERIFY_STATIC_DONE" != "$STATIC_MARK" ]; then
    python3 scripts/compare_revision.py "${1:-parent}" --resolve-only
    python3 scripts/job.py step "static checks"
    sh scripts/verify_static.sh
    export ZORA_VERIFY_STATIC_DONE="$STATIC_MARK"
fi

# The whole run holds the suite lock once (tests/suite_lock.py); its parts see it held.
if [ -z "$ZORA_SUITE_LOCK_HELD" ]; then
    exec python3 tests/suite_lock.py sh "$0" ${ALL_FAILURES:+--all-failures} "$@"
fi
START=$(date +%s)

# A failed step ends the run, or, with --all-failures, is listed at the end, after every step ran
FAILED_STEPS=""
failed() {
    if [ -z "$ALL_FAILURES" ]; then
        exit 1
    fi
    FAILED_STEPS="$FAILED_STEPS
  $1"
}

echo "== full tier 1/4: the fast suite's checks, with every seed"
python3 scripts/job.py step "1/4: the fast suite's checks, with every seed"
ZORA_VERIFY_TIER=full sh scripts/verify.sh --fast-suite ${ALL_FAILURES:+--all-failures} "$@" \
    || failed "1/4: the fast suite's checks (the tests, the encoder check or the comparison)"

echo "== full tier 2/4: the slow suite"
python3 scripts/job.py step "2/4: the slow suite"
if python3 -c "import xdist" 2>/dev/null; then
    python3 -m pytest tests -q -m slow -n auto $MAXFAIL || failed "2/4: the slow suite"
else
    python3 -m pytest tests -q -m slow $MAXFAIL || failed "2/4: the slow suite"
fi

echo "== full tier 3/4: the release-tree checks"
python3 scripts/job.py step "3/4: the release-tree checks"
# A released checkout has no release/ folder: nothing to build a release from
if [ -f release/allowlist.txt ]; then
    python3 scripts/make_release.py --dry-run || failed "3/4: the release-tree checks"
fi

echo "== full tier 4/4: the output against the last release"
python3 scripts/job.py step "4/4: the output against the last release"
LAST=$(python3 scripts/full_tier.py last-release)
if [ -n "$LAST" ]; then
    set +e
    python3 scripts/compare_revision.py "$LAST" --seeds 20
    STATUS=$?
    set -e
    # Differences since the last release are listed for the changelog, not a failure
    if [ $STATUS -gt 1 ]; then
        exit $STATUS
    fi
fi

if [ -n "$FAILED_STEPS" ]; then
    echo "full tier: FAILED, not stamped. Failed steps:$FAILED_STEPS" >&2
    exit 1
fi
python3 scripts/full_tier.py stamp $(( $(date +%s) - START ))
