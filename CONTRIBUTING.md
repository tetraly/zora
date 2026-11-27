# Contributing to ZORA

Thanks for wanting to help. ZORA welcomes contributors of every skill level, and most of its code
is written with AI coding assistants, so you are welcome to work with one too. This page is how a
change gets from an idea to a merged pull request without anyone's time being wasted, yours
included. If your assistant reads repository instructions, it will also find `AGENTS.md`, a short
version of this page written for it.

If anything here is unclear, ask in the issue or in the [ZORA Discord](https://discord.gg/zescSjDtme).

## 1. Start with an issue

Open a GitHub issue for what you want to do, or comment on an existing one to claim it, before
writing code. Say what you want to change and how you plan to do it, in a few lines.

Ask in the issue first, and wait for an answer, when the change would:

- change a design decision the project has already made (for example how the Archipelago world
  works, or how a flag behaves);
- change the flag string: a new flag, value or field (an existing string must keep meaning exactly
  the same settings in every later version);
- change generation: what a seed's game contains for a given version, flags and seed;
- change the Archipelago world (its options, items, locations or logic);
- need ROM or RAM space (section 3).

A cosmetic player setting, a page fix, a test or a doc fix usually needs only a short note.

## 2. One pull request per step

- **One PR per agreed step**, up to about 1,000 changed lines when at least half of them are
  tests, or about 500 otherwise (generated files such as `*_data.py` aside). A larger piece of
  work is split into steps in the issue first, and each step is its own PR.
- **No stacked PRs.** Each PR starts from the current `main`, not from another open PR. Open the
  next step once the previous one is merged.
- Keep a PR to its step: no drive-by renames, reformatting or unrelated fixes (open an issue for
  those).

## 3. ROM and RAM space

The game's ROM is nearly full, other features (co-op, randomized music) need room too, and ZORA
wants to stay able to change its mapper later (below). So:

- **Request space in the issue**: which bank, how many bytes, and why there. For RAM, which
  addresses and whether they must survive a save.
- **Claim exactly what the code uses.** A new patch's segment `size` in its `patch.toml` is the
  most it may grow to, so keep it close to the real size. `asm/README.md` ("Adding a patch") shows
  how a patch is placed and how `asm/placements.toml` records it.
- **Follow the "Keep MMC5 possible" rules** below.

### Keep MMC5 possible

ZORA wants to stay open to moving to the MMC5 mapper and/or converting to CHR-ROM graphics in the
future. These rules keep that a straightforward conversion of the ROM we build today:

1. Keep `SwitchBank` at $FFAC and `SetMMC1Control` at $FF98, and keep their results: A = 0, the
   carry as now, X and Y unchanged. Every patch calls them by address.
2. Leave the game's own mapper blocks alone: bank 7 $FF50-$FFBF, $BF50-$BFBF in banks 0-6, and
   bank 7 $FFEB-$FFFF (the block before the vectors, and the vectors).
3. Add no new writes to the pattern tables at run time (PPU $0000-$1FFF). Draw new tiles at build
   time in the pattern data. If a runtime write can't be avoided, keep it in one routine that a
   CHR-ROM build can replace with a bank write.
4. Put no code or non-tile data inside the pattern data (`DemoSpritePatterns`,
   `DemoBackgroundPatterns`, `CommonSpritePatterns`, `CommonBackgroundPatterns`,
   `CommonMiscPatterns`, the level pattern blocks in bank 3), blank tiles included: they become
   CHR-ROM.
5. Choose which pattern blocks a level loads only through the sprite-set pointer tables at the
   start of bank 3, so a CHR-ROM build can follow them.
6. Don't use these code sites without asking in your issue first: bank 4 $86E0, $8F91 and $8FC1;
   bank 5 $8BA1; bank 7 $E621; the pattern loaders' entries (bank 1 $8D47, bank 2 $8012, bank 3
   $8044); bank 2 $ABA5 and $A803. A mapper or CHR-ROM conversion would need to hook them.
7. Don't spend bank 5's last free bytes, or bank 4's, on code that could run in banks 0, 3 or 6
   behind a far call through `SwitchBank`.
8. Ask for new PRG-RAM state ($6000-$7FFF) in the issue first: $7F00-$7F3F is the statistics
   screen's, and $7F40-$7FFF belongs to randomized music and co-op.
9. Don't build MMC3-only layouts. Reach banks 0, 3 and 6 through `SwitchBank` and the shared
   far-call stub (when there is one); that works on MMC1, MMC3 and MMC5.

## 4. Before you open a pull request

### Set up once

- Python 3.11 or newer, then: `python3 -m pip install -e ".[test]" pytest mypy ruff==0.17.0`
- The base ROM: the original US release of *The Legend of Zelda* (PRG0, not Rev 1), named
  `Legend of Zelda, The (USA).nes`, in the repository's top folder. It is never committed. Check it:
  - macOS or Linux: `shasum "Legend of Zelda, The (USA).nes"`
  - Windows (PowerShell): `Get-FileHash -Algorithm SHA1 "Legend of Zelda, The (USA).nes"`

  The SHA-1 must be `dab79c84934f9aa5db4e7dad390e5d0c12443fa2` (MD5
  `337bd6f1a1163df31bf2633665589ab0`). Any other file, a Rev 1 copy or a headerless one, is refused.
- On Windows, run the commands below in Git Bash. The scripts call `python3`: if `python3 --version`
  fails there, copy `python.exe` to `python3.exe` in the folder `where python` shows (an alias
  doesn't reach the scripts). The repository checks every file out with LF line endings
  (`.gitattributes`), which the shell scripts need.

### Run the quick check

```
sh scripts/verify.sh
```

It checks the base ROM first, then runs the static checks (import rules, mypy and ruff), the tests your change most likely affects (a capped selection: it lists any it leaves out), and a
comparison of the game's output with your branch's last commit. Paste
its last lines, the verdict, into your PR. "output identical" means your change didn't change any
game; "output DIFFERS" is expected for a change that should, and the PR says why.

### The checks that most often fail later

The project runs a much larger test run before each release. These are the failures it catches
most often in work that passed the quick check; run the ones that apply to your change:

- **mypy and ruff.** `sh scripts/verify_static.sh` runs them alone (strict mypy; ruff 0.17.0).
- **Tests pinned to one seed's world or to exact ROM bytes.** A change to generation or to the ROM
  makes some seeds differ, and tests that check one seed or one byte range fail.
  `python3 scripts/affected_tests.py PATH ...` lists the slow tests your files most likely affect,
  and `--fast` the fast ones. Run them: `python3 -m pytest -m slow tests/test_NAME.py`.
- **The flag combinations table.** An option that changes output belongs in
  `tests/test_flag_invariants.py`'s `IMPLEMENTED` table, with its non-default values. Check yours:
  `python3 -m pytest -m slow tests/test_flag_invariants.py -k OPTION_NAME`.
- **Frozen flag strings.** Old flag strings must decode to the same settings:
  `python3 -m pytest tests/test_flag_string_compatibility.py`. Never reorder or reuse a field or a
  value; a new setting decodes to its default (Off) from an older string.
- **ROM space claims.** `python3 -m pytest tests/test_rom_space.py` checks that no two patches write
  the same byte and that each patch stays inside its claim.
- **The changelog line.** A change to what the game does needs one line for the changelog, in the
  PR's "Changelog line" section; the project adds it to `docs/CHANGELOG.md` at the next release.

You don't run the full test run yourself: the project owner runs it when merging. (The quick check's
own messages call it "the batch run".)

### The PR itself

The pull request template asks for: what changed, how you tested it (pasted output, including the
quick check's verdict), what you did **not** test, screenshots for any change to the web page, and
the emulator checks for any change to the ROM. "Not tested" is required: saying what you didn't
check is as useful to the reviewer as what you did.

## 5. A few rules the code keeps

- ZORA is a clean-room project: never copy or adapt code, data or ROM bytes from another
  randomizer or ROM hack without a license or permission from its author (say which in the PR).
  Reading another tool's output (a ROM it made) to learn a format is fine; otherwise the code that
  writes ZORA's own version comes from the game's disassembly and your own work.
- Never commit a ROM, or anything cut from one.
- The same version, flags and seed must always make exactly the same ROM, apart from the player's
  cosmetic settings.
- `zora/` uses relative imports only, and only `zora/rom/` reads or writes ROM bytes; the static
  checks and `tests/test_data_boundary.py` enforce it.

## Starter projects

`docs/contributing/` has briefs for well-scoped first projects, written so you can hand one to
your AI assistant: each is split into steps, one PR each.

- [Custom recorder tunes](docs/contributing/starter-recorder-tunes.md): a player setting that
  plays a tune of your choice when Link uses the recorder.
