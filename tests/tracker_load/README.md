# Tracker load tests

Check that the trackers load ZORA's tracker files (`zora_export/tracker_file.py`) and hold what the seed document says.
Opt-in: without `ZORA_TRACKER_LOAD=1` every test here skips, so they never run in the quick check or the fast tier.
Research and design: `docs/reports/tracker-load-tests.md`.

## Run

```
ZORA_TRACKER_LOAD=1 python3 -m pytest tests/tracker_load
```

About a minute with a warm cache (about two with a cold one: the first run builds ZoraTracker). One test (a third use of a stairway number, which makes the tracker sound its system alert beep) skips unless `ZORA_TRACKER_LOAD_LOUD=1`, so a normal run is silent. Run it serially (no `-n`): every ZoraTracker run uses one program folder.

Needs: the .NET 10 SDK (`dotnet`), the base ROM (as for the other seed tests), a ZoraTracker checkout that holds the pinned commit, and a ZTracker checkout that holds its pinned commit. A test skips, naming what is missing, when one is not there.

## What runs

| File | What |
|---|---|
| `test_zoratracker_load.py` | Builds the pinned ZoraTracker (its `--load=<file> --dump=<out>` switch, `docs/load-dump.md` in that repo), generates seeds at Basic, Medium and Full with Z1R flags only and with ZORA flags (`samples.py`, seeds 1 and 2), loads each file in the real tracker (headless: no window, no focus change; about 4 s each), and compares the tracker's own re-save with the file (`compare.kept`: nothing refused, dropped or turned into "unmarked") and with the seed document (`compare.facts`: rooms, every edge, stairway pairs used exactly twice, entrance arrow, item cellars, each level's item boxes, level markers). Four tests load files made wrong on purpose, and a fifth one with a wrong edge, to show the comparison sees problems |
| `test_ztracker_load.py` | The original ZTracker's model and save classes, run on .NET 10 (`ztracker_probe/`), applying the file's overworld tiles and item boxes as its loader does; its name tables are read from its source text. Ids 15 and up are expected drops. ZTracker's window and dungeon import do not run on a Mac: use `MANUAL-CHECKLIST.md` |

## Where things live

- `pin.py`: the one place that names ZoraTracker (repo path, branch, commit) and ZTracker (repo path, commit).
- `artifacts/tracker-load-cache/` (ignored by git): the exported sources of the pinned commits and their builds. Nothing of either tracker is committed to this repo. Delete the folder to force a rebuild.
- `python3 -m tests.tracker_load.samples OUTDIR` writes the sample files (tracker save, text log, info) for hand testing.

## Moving the pin

`pin.py` names Gob's merge commit of the `--load`/`--dump` switch (pull request 26 in his ZoraTracker repository). To test a newer ZoraTracker: fetch his remote in the checkout (`git fetch gob`), then change `COMMIT` in `pin.py` to the commit wanted (and `REPO` if the checkout moved; `BRANCH` is only a note). That is all: the harness exports whatever commit `COMMIT` names and builds it. A newer ZoraTracker can also change what the tracker re-saves; a new difference then shows in `compare.kept`.

To move ZTracker's pin, change `ZTRACKER_COMMIT`.

## When a test fails

A difference between what the tracker holds and the seed document is a finding, not noise: the message names the level, cell or box. Check the writer (`zora_export/tracker_file.py`) first, then the format report.
