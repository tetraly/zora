# The flags spec: ZORA's flag strings for outside tools

ZORA describes its two flag strings in one machine-readable file, so a tracker, a bot or a racing tool
can read a seed's flags without copying ZORA's decoder. The file is generated from ZORA's own flag code
(`zora/flags/`) by `scripts/flags_api.py`, never written by hand, and a test decodes a corpus of real flag
strings with the file alone and checks the result against ZORA (`tests/test_flags_api.py`).

- `docs/flags-api/zora-flags.json`: the spec.
- `docs/flags-api/zora-flags.schema.json`: its JSON Schema (draft 2020-12).

## Where to get it

- **On the site, from 2.0.1:** each release writes its copy at a versioned address that never changes, and
  one that follows the newest release:
  - `https://zora.gg/flags/<version>.json`, for example `https://zora.gg/flags/2.0.1.json`;
  - `https://zora.gg/flags/latest.json`;
  - `https://zora.gg/flags/zora-flags.schema.json`.

  The test channel writes the next version's spec only as `https://zora.gg/test/flags/latest.json`,
  so `latest.json` is always a released version.
- **With each GitHub release, from 2.0.1:** `zora-flags-<version>.json`, attached beside `zora.apworld`.
- **In the repository:** the two files above, always matching the flag code beside them. The repository's
  copy is a work copy: its `zora_version` is the last release it was written for, and it may hold changes
  made since. A published copy (the site's and the GitHub release's) carries its real version.

A tool can pin itself to the version its players use, or read `latest.json` and rely on the stability
promise below. A seed's tracker file from ZORA (Spoiler Log Detail Level None or above) names its version
in `ZoraVersion` (ZORA's release version, never the ZORA flag string's prefix) and its ZORA flag string in
`ZoraFlags`.

## What it holds

| Property | What it is |
|---|---|
| `spec_version` | The spec's own version, `MAJOR.MINOR` (see "Stability"). |
| `zora_version` | The ZORA release the file describes. A published copy carries its release's version; the repository's work copy, the last release it was written for. |
| `alphabet` | The 63 digits both strings are written in, in value order (`0` is 0, `!` is 62). |
| `alphabet_aliases` | Characters read as a digit but never written: `_` reads as `!` (see "`!` is canonical"). |
| `page_default` | The flag strings the flag page starts with. |
| `z1r` | The Z1R flag string: its rules and its 121 fields, C01-C27 and B01-B94. |
| `zora` | The ZORA flag string: its format, rules and every field ever defined, retired ones included. |
| `combined_controls` | The page's settings that are stored as two fields (Item Shuffle, Spoiler Log Detail Level, Add L4 Sword). |
| `tracker_hints` | What a player can know at the start from the flags alone: pinned items and start items. |
| `file_name` | How the flag page names a seed's files, so a tool can read the version, both flag strings and the seed from a file's name. |

Each field has:

- `key`: `C01` to `C27` and `B01` to `B94` in the Z1R string, a lowercase name in the ZORA string
  (`item_counter`). Keys never change.
- `position` and `radix`: its place in the string and how many digit values it takes.
- `kind`: `option`, `three_state` (Off / On / Random) or `switch` (Off / On).
- `added_in_version` (ZORA fields): the ZORA string version that introduced it.
- `name` and `values`: the names the flag page shows, `values[i]` naming value `i`.
- `random_values`: each value that means "decided per seed", with the values it can resolve to.
- `default`: the value the flag page starts with. For a ZORA field it is also the value a string of an
  older version decodes to.
- `beta_values`: the values that are beta settings (less tested), the other fields at the page's starting
  values. `combined_controls` marks beta per page value.
- `page_control` (when present): the combined control the page shows this field in. `hidden` (ZORA fields)
  marks a field shown only there. `retired` marks a field that is read and ignored. `no_effect` marks a Z1R
  field ZORA decodes but never uses.

## Decoding, step by step

Both strings are one whole number written in the alphabet, most significant digit first. The fields
are read from the least significant end: each field's value is the number modulo its radix, then the
number is divided by the radix.

**The Z1R string** (`z1r.rules`):

1. Refuse an empty string or any character outside `alphabet`, reading each `alphabet_aliases` character
   as its digit (`_` as `!`).
2. Turn it into a number: `n = n * 63 + digit` for each character, left to right.
3. For each field in `position` order: `value = n % radix`, then `n = n // radix`. An option value at or
   above `len(values)` reads as the last value.
4. Ignore whatever is left of `n`.

**The ZORA string** (`zora.rules`):

1. The empty string means every field at its `default`.
2. Otherwise it must match `zora.pattern`, `<version>.<payload>`. Refuse a version above
   `current_version`: the string is newer than the spec, so fetch a newer spec.
3. Turn the payload into a number as above (refusing characters outside the alphabet, aliases read as
   their digits).
4. For each field in `position` order whose `added_in_version` is at most the string's version:
   `value = n % radix`, `n = n // radix`. Fields added later keep their `default`.
5. Refuse the string if anything is left of `n`: a mistyped string never turns into other flags.
6. Ignore the `retired` fields' values.

**`!` is canonical.** ZORA reads `_` as `!` in both strings, in any mix, so flags copied from a file name
(where the page writes `!` as `_`) paste as they are. It always writes `!`: the flag page shows and copies
`!`, shared links carry it, and seeds store it. A tool should read the alias and write `!`. The original Z1R
program accepts only `!`, so give it strings with `!`.

A worked example: the ZORA string `4.T9Jvg` (the All Swords No Boards preset) is version 4. Its payload
holds the 20 fields with `added_in_version` 4 or lower. Reading them gives
`progressive_items = 1`, `add_l4_sword = 1`, `l4_sword_in_level_2 = 1` and
`level_9_entrance_sword = 1`, every other field 0. `combined_controls` names the second and third together:
Add L4 Sword: Level 2.

### Tracker hints

`tracker_hints` uses conditions: a condition such as `{"C06": [1, 2, 3]}` matches when every field it
names holds one of the listed values (Z1R keys and ZORA keys share one namespace). A list of conditions
matches when any one does.

- **Pins** (Armos Item C11, Coast Item C12, White Sword Item C13, Level 9 Item 1 and 2, C26 and C27): when
  `applies_when` matches, a pin value with `status: item` names the item at that place. When
  `unknown_when` matches, the seed decides whether it is there. Otherwise the pins do nothing. `not_pinned`
  and `unknown` values (Non-Heart: any item but a Heart Container) name no item.
- **Start items:** a start-item field at On gives its item when the Max Start Items limit (C17) keeps every
  chosen item; a field at Random, or a limit that may drop items, leaves it unknown.
- **Modifiers**, applied in their listed order: Swap Swords and Rings trades two pairs of items, Pegasus
  Boots renames the boomerangs, Wood Sword Only and Swordless make the White Sword a bomb upgrade, and
  Progressive Items makes each item of an upgrade line found in the world give the next one of that line.
  Each has its own `applies_when` and `unknown_when`, and acts only on what its `applies_to` names
  (`locations`, `start_items`).
- **Progressive Items doesn't change start items:** a start item is the item itself (a start Magical Sword
  gives the Magical Sword), as the ROM's starting table holds it. Swap Swords and Rings never swaps a start
  item either; Pegasus Boots names the start boomerangs as the boots.

**Item names are canonical:** they are ZORA's own names, the seed format's (`docs/seed-format/`), as in the Z1R
Visualizer, the spoiler log and ZORA's tracker files. A tool should map them to its own items, never the
other way round. Each upgrade line in `progressive_items` lists its items lowest first.
Nothing in the hints depends on the seed: where a seed's draw decides, the hint says unknown.

**Swords.** Swordlish: Random draws one of five sword states per seed (Normal, Wood Sword Only, No Wood
Sword, Swordless, or Swordlish), so Swap Swords and Rings and the bomb upgrade are unknown under it.
Swordlish: On needs Swords: Normal and only puts a triforce-piece price on the Wood Sword, so the swords
are known: the swap acts and the White Sword is a sword. Start items are given whatever the sword state.

**The starter tracker file.** A seed made with Spoiler Log Detail Level None gets, from the page's "Download
tracker file", a ZoraTracker save built from these hints alone (`zora_export/tracker_hints.py`, the code that
writes them here): each pinned place's item, the start items, both with the modifiers applied, the
bomb upgrade when it applies, and Pegasus Boots as ZoraTracker's `BootsReplaceBoomerangs` (Off 0, On 1,
Random 2; the full file writes the seed's own 0 or 1). It also holds the seed, the Z1R flag string (`Flags`), and two fields the
trackers ignore, `ZoraVersion` and `ZoraFlags`. The same flags give the same file for every seed, apart
from `Seed`.

## Reading a file's name

The flag page names each seed's files after what made them, so a tool (ZoraTracker first) can take the
version, both flag strings and the seed from a file the player drops on it. `file_name` describes the
format; it is generated from the page's own naming code (`web/zora-web.js`, `seedFileStem`).

```
zora-<version>-<Z1R flag string>-<ZORA flag string>-<seed>[-music].<extension>
zora-2.0.1-oIbnPfPb01Hll3D29Bc2_etrojQOSjJQZUULH-18.1DzpD8sDGgcF-3563927730.nes
```

- **The parts, in order:** `zora`, then the version, the Z1R flag string, the ZORA flag string and the seed,
  joined by `-`, then `-music` when the seed has randomized music (Music: Random, a player setting in
  neither flag string).
- **The version** is the one the page shows, spaces as `-` and parentheses dropped: `2.0.1` on zora.gg. On
  the test channel the build's short commit follows it and `-test` ends it: `2.0.1-a1b2c3d-test`. It may
  hold `-`; the flag strings never do, so a name also reads from the right.
- **`!` is written `_`** in a name: a shell and a URL treat `!` specially, so an upload could rename it.
  `_` is the alphabet's alias for `!`, so each flag part is a valid flag string as it stands: decode it as it
  is, and show it with `!`.
- **An empty ZORA string** (every ZORA setting off) leaves `--` between the Z1R string and the seed.
- **The extensions** (`extensions`): `.nes` for the ROM, `.spoiler.txt` for the spoiler log and
  `.tracker.json` for the tracker file.
- **A batch** (several seeds at once) comes as a `.zip` named for the first seed's stem, then `-` and the last
  seed, then any `-music`: `zora-2.0.1-<flags>-<ZORA flags>-100-109.zip`. Inside it, and in a batch saved to a
  folder, each seed's files have the names above.

`file_name.pattern` matches every seed file's name and `file_name.batch_zip.pattern` every batch's; `groups`
names their capture groups in order. Both work as written in Python's `re` and JavaScript's `RegExp`:

```
^zora-([.0-9A-Z_a-z-]+?)-([0-9A-Z_a-z]+)-((?:[1-9][0-9]*\.[0-9A-Z_a-z]+)?)-([0-9]+)(-music)?(\.nes|\.spoiler\.txt|\.tracker\.json)$
^zora-([.0-9A-Z_a-z-]+?)-([0-9A-Z_a-z]+)-((?:[1-9][0-9]*\.[0-9A-Z_a-z]+)?)-([0-9]+)-([0-9]+)(-music)?\.zip$
```

What a tool should tolerate (`tolerate`):

- **A browser's duplicate number.** Saving the same name twice gives `name (1).nes` (Chrome, Edge) or
  `name(1).nes` (Firefox). Remove it (`tolerate.duplicate_suffix.pattern`) before matching.
- **A renamed file.** A name that does not match is not the page's: read nothing from it and ask the player
  to paste the flag strings instead.
- **Names from before 2.0.1:** `zora-seed-<seed>.nes` (perhaps with `-encoded` or `-music`) and
  `zora-seeds-<first>-<last>.zip`. They hold the seed only and match neither pattern.
- **Archipelago's files** (`AP_<multiworld seed>_P<player>_<player name>.apzora`, and the `.nes` made from it)
  hold no ZORA flags and match neither pattern.

## Presets: `presets.json`

`https://zora.gg/presets.json` lists the presets a race bot can roll: every preset on the flag page that
has a ZORA flag string, each with a shortcut. TTPBot, the RaceTime.gg bot, reads it every five minutes and
uses none of it if any of the checks below fails. The format is the Z1R Council registry's, with a `zora`
key added:

```json
{"schemaVersion": 1, "revision": 1, "updatedAt": "2026-11-17T14:00:39Z",
 "flagsets": [{"name": "All Swords No Boards", "description": null, "shortcuts": ["asnb"],
               "strings": [{"flags": "8hq4BeR1JXo7yjOOHjbxryVQW!UJ3A", "zora": "4.T9Jvg", "isLatest": true}]}]}
```

| Property | What it is |
|---|---|
| `schemaVersion` | The integer `1`. |
| `revision` | An integer from 1 to 2^53-1, raised by one whenever the presets change. The bot ignores a file whose revision it has already read. |
| `updatedAt` | When the revision was raised (ISO 8601, UTC, to the second). |
| `flagsets` | One per preset, in the page's menu order: `name` (at most 80 characters), `description` (always `null`), `shortcuts` (the preset's key) and `strings` (its one string, `isLatest` true). |

Each string has `flags`, the Z1R string (`[A-Za-z0-9!]{1,200}`, always `!`, never `_`), and `zora`, the
ZORA string (`[1-9][0-9]*\.[0-9A-Za-z!]{1,200}`). Two presets may share a Z1R string with different ZORA
strings (Zora The Explorer weeks 4 and 5); no pair of strings is in two flagsets.

The bot compares names and shortcuts lowercased with everything but `a-z` and `0-9` removed. Each must leave
something, no form may belong to two flagsets, and no shortcut may read as one of the bot's commands
(`flags`, `race`, `cancel`, `summary`, `help` and the rest of its registry contract's list).

The test channel publishes the next release's file as `https://zora.gg/test/presets.json`.

## Stability

The spec follows the flag strings' own promise (from beta 6 on): a flag string keeps meaning the same
settings in every later ZORA version.

- **Keys never change meaning.** A field's key, position, radix and value numbers are fixed once released.
- **Fields are only added.** A new ZORA field goes in a new ZORA string version, at the end, off by
  default, so every older string decodes as before. A removed setting stays as a `retired` field, so
  positions never move.
- **Names may change.** `name` and `values` are the page's current wording: show them, but never match on
  them. Beta marks change as settings graduate.
- **`spec_version`:** the minor number grows when the spec gains a property, which a tool should ignore if
  it does not know it (the schema allows this). The major number grows only for a change a tool written for
  the old spec would misread.

## For ZORA developers

- Run `python3 scripts/flags_api.py` after changing anything under `zora/flags/` (a field, a name, a beta
  mark), the generation code the hints read, or the page's file names (`web/zora-web.js`, from
  `FILE_NAME_STAND_INS` to `batchZipName`; the generator reads them there and stops if it cannot). `tests/test_flags_api.py` fails until the files are current.
  `python3 scripts/flags_api.py --check` checks without writing.
- The test and `--check` compare everything but `zora_version`, so a version bump never needs the spec
  regenerated. `python3 scripts/flags_api.py --published FOLDER` writes the release's copy,
  `zora-flags-<version>.json` with `zora_version` set to the checkout's version, and the schema.
- The tracker hints' rules live in `zora_export/tracker_hints.py`, shared by the spec and the starter tracker
  file, so the two never disagree.

### Presets

- The presets live in one ordered list, `PRESET_LIST` in `zora/flags/presets.py`: each entry's `key` (its
  shortcut), `name` (what the page's menu shows), `flags` and `zora` (empty for none). The page's menu
  (`form.presets`) and `presets.json` are both made from it; `hidden` keeps an entry off the menu (Random%).
  Give every entry a key; the ones with a ZORA string are the ones `presets.json` lists.
- `python3 scripts/flags_api.py` also writes `docs/flags-api/presets.json`. Its revision is the committed
  counter `docs/flags-api/presets-revision.json` (the revision, when it was raised, and a SHA-256 of the
  flagsets): a run whose presets differ from the counter's raises the revision by one. `--check` and
  `tests/test_presets_json.py` fail until that has happened, so a change can't ship with the old revision,
  and they check the file against every rule above (`validate_presets`). Two branches that each raise it
  conflict in the counter file when merged; run the generator again after resolving it.
- `tests/test_presets_json.py` also runs the validator over TTPBot's own test vectors:
  `tests/fixtures/flagsets-contract.json` (the Z1R registry's contract, copied unchanged from TTPBot's main
  branch) and `tests/fixtures/zora-presets-contract.json` (its ZORA category's), each valid file passing and
  each invalid one failing.

### Publishing (from 2.0.1)

- `release/allowlist.txt` ships `docs/flags-api/`, `docs/flags-api.md` and `scripts/flags_api.py`, so the
  public repository carries the spec and its test runs there.
- `scripts/make_release.py` checks the spec in the release tree (`flags_api.py --check`) and attaches
  `zora-flags-<version>.json` to the GitHub release.
- `scripts/publish_site.sh` (through `scripts/gh_pages_commit.sh`) writes `flags/<version>.json` (never
  replaced once there), `flags/latest.json` (that version's file) and `flags/zora-flags.schema.json` to the
  site. The test channel writes `test/flags/latest.json` only.
- Every site publish (`scripts/publish_site.sh`, both channels) writes `docs/flags-api/presets.json` too:
  the regular channel as `presets.json`, the test channel as `test/presets.json`. It is written only when its
  revision is higher than the copy already there (`scripts/flags_api.py --presets-against`), so a publish
  from an older commit never takes the bot back; the same revision with other presets is refused.
- **A new preset needs no release.** Add it to `PRESET_LIST`, run `python3 scripts/flags_api.py`, commit
  the three files on main, then publish `presets.json` alone from main's checkout:

  ```bash
  sh scripts/publish_site.sh --presets
  ```

  It refuses uncommitted presets files or a `presets.json` that `--check` finds out of date, commits only
  `presets.json` to gh-pages (every other file unchanged), and prints the push command,
  `git -C ../zora push origin gh-pages`.
