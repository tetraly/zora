"""Where the tracker load tests get ZoraTracker: the one place to change when the pin moves.

The tests build COMMIT from the ZoraTracker checkout at REPO. The --load/--dump switch they use is in Gob's master
since his merge of pull request 26 (2026-11-07), so COMMIT is that merge commit. To test a newer ZoraTracker, fetch
his remote in the checkout and set COMMIT to the commit wanted (BRANCH is only a reminder of where it came from).
ZORATRACKER_REPO in the environment overrides REPO.
"""
import os
from pathlib import Path

REPO = Path(os.environ.get("ZORATRACKER_REPO", "~/Desktop/GitHub/ZoraTracker")).expanduser()
BRANCH = "master"
COMMIT = "10dc5bad63931dcf3b090a9764d15e327ae3b5b6"

# ZTracker (the original, MIT; read-only): the checkout and commit the data-level check reads its model and
# name tables from.
ZTRACKER_REPO = Path(os.environ.get("ZTRACKER_REPO", "~/Desktop/GitHub/ztracker")).expanduser()
ZTRACKER_COMMIT = "d76f78ae3bad6d89523340f317a282db1120bf73"   # v1.3.1 plus its macOS build change
