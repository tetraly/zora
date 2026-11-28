# Working on ZORA (for AI coding assistants)

You are helping a contributor change ZORA, a randomizer for *The Legend of Zelda* (NES). Read
`CONTRIBUTING.md` first; this file is the short version, and where they differ, CONTRIBUTING.md wins.

## Before writing code

- Work only on a step agreed in a GitHub issue. If the step isn't agreed yet, help the contributor
  write the issue instead. Ask in the issue, and wait, before anything that changes a recorded
  design decision, the flag string, generation (what a seed contains), the Archipelago world, or
  that needs ROM or RAM space.
- One step is one pull request: up to about 1,000 changed lines when at least half are tests, or
  about 500 otherwise (generated `*_data.py` files aside), started from the current `main`, never
  stacked on another open PR. Stop at the end of the
  step and report; don't start the next one.

## While working

- Scratch files go in `temp/` (git-ignored). Never commit a ROM or anything cut from one.
- Clean room: never copy or adapt code, data or ROM bytes from another randomizer or ROM hack
  without a license or permission from its author.
  Reading a ROM another tool made, to learn a format, is fine. New 6502 code is written from the
  game's disassembly (`asm/README.md`).
- Same version, flags and seed give exactly the same ROM, apart from cosmetic player settings. A
  change that alters output must be intended, and the PR says so.
- A flag string keeps meaning the same settings in every later version: never reorder or reuse a
  field or a value; a new setting decodes to its default (Off) from an older string.
- `zora/` uses relative imports only, and only `zora/rom/` reads or writes ROM bytes.
- ROM or RAM space: use only what the issue granted, claim exactly what the code uses, and keep
  the "Keep MMC5 possible" rules in CONTRIBUTING.md section 3.
- Match the surrounding code: names in game terms, no unexplained numbers, comments that say why.

## Before the pull request

- Run `sh scripts/verify.sh` and paste its last lines (the verdict) into the PR. Then run the checks
  in CONTRIBUTING.md section 4 that apply to the change (mypy and ruff, the affected slow tests, the
  `IMPLEMENTED` table, frozen flag strings, ROM space claims).
- Fill in `.github/pull_request_template.md` honestly. "Not tested" lists what you did not run or
  check; never present a check you didn't run as passed, and paste output rather than describe it.
- A change to ROM bytes needs an emulator check by the contributor; a change to the web page needs
  screenshots. Say so if they are missing.
- The project owner runs the full test run when merging; you don't need it.
