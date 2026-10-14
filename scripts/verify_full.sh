#!/bin/sh
# The full verification tier (AGENTS.md "Verification"; docs/design/test-speed.md 3.2): before
# reporting a feature done, before merging, and in every release run. Run from the repo root,
# best in a clean copy of the commit (scripts/clean_copy.py), which it then stamps:
#
#   sh scripts/verify_full.sh         every check of the fast tier (scripts/verify.sh) with every
#                                     seed, the slow suite, the release-tree checks
#                                     (scripts/make_release.py --dry-run: the suite without the
#                                     private module, the patch data, the wheel and the site) and
#                                     the output against the last release (listed, not a failure)
#   sh scripts/verify_full.sh REV     ... with the fast tier's comparison strict against REV
#
# When every check passes on a tree that is exactly a commit, scripts/full_tier.py stamps it
# (temp/verify/full-tier/ in the source checkout); scripts/make_release.py requires the stamp.
set -e

# Progress (zora_measure/progress.py): the run is a job that says at least once a minute which step
# it is on, the test count of the pytest run inside it, and how long is left.
if [ -z "$ZORA_JOB_ID" ]; then
    exec python3 scripts/job.py run --name "verify_full.sh (full tier)" -- sh "$0" "$@"
fi

# The whole run holds the suite lock once (tests/suite_lock.py); its parts see it held.
if [ -z "$ZORA_SUITE_LOCK_HELD" ]; then
    exec python3 tests/suite_lock.py sh "$0" "$@"
fi
if [ -f verify.env ]; then
    set -a
    . ./verify.env
    set +a
fi
START=$(date +%s)

echo "== full tier 1/4: the fast tier's checks, with every seed"
python3 scripts/job.py step "1/4: the fast tier's checks, with every seed"
ZORA_VERIFY_TIER=full sh scripts/verify.sh "$@"

echo "== full tier 2/4: the slow suite"
python3 scripts/job.py step "2/4: the slow suite"
if python3 -c "import xdist" 2>/dev/null; then
    python3 -m pytest tests -q -m slow -n auto
else
    python3 -m pytest tests -q -m slow
fi

echo "== full tier 3/4: the release-tree checks"
python3 scripts/job.py step "3/4: the release-tree checks"
# A released checkout has no release/ folder: nothing to build a release from
if [ -f release/allowlist.txt ]; then
    python3 scripts/make_release.py --dry-run
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

python3 scripts/full_tier.py stamp $(( $(date +%s) - START ))
