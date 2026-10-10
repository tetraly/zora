# The seed document and the spoiler log

Two owner features (2026-10-06), offered only for seeds made with "Encode level data" **off**.
For an encoded seed the page shows neither button, and `zora_web.api.seed_report` refuses with
`EncodedSeedRefused`.

- **View in Visualizer** hands the seed to the owner's Z1R Visualizer
  (https://tetraly.github.io/z1r-visualizer/), in the visualizer's seed format.
- **Download spoiler log** saves a plain-text log, `zora-<version>-seed-<seed>-spoiler.txt`.
  `docs/spoiler-log-sample.txt` is a sample for the owner to review.

## The format

`seed-format.schema.json` here is the visualizer's JSON Schema for format 1.0. It is copied
unchanged from github.com/tetraly/z1r-visualizer (`docs/seed-format.schema.json`; its
`$comment` names the commit). That repo's `docs/seed-format.md` explains each field and the
hand-off. No visualizer code is copied into ZORA.

## ZORA's writer: `zora_export/seed_document.py`

- **What it describes.** The document describes the **finished ROM**. Dungeons, caves, shops,
  prices and texts come from the data layer's parse of the ROM's bytes (`parse_rom` with the
  seed's `GameConfig`), not from the generator's working state. The player settings change
  nothing in it.
- **What the plan adds.** Only what the ROM cannot hold:
  - the seed number and the flag strings;
  - each setting as chosen and as resolved;
  - who says each text.

  The resolved "?" values come from FL-DEP-04's own stream again. That stream is separate from
  the generation's, so reading it draws nothing the generation uses.
- **ZORA's extras.** The format's optional fields: `seed`, `progressiveItems`, `settings`, the
  hints' `speaker` and the shop wares' `sellsOnce`. `sellsOnce` holds the ROM's one-time-ware
  bytes (`code_patches.one_time_wares`). It is set only when fp-prog-01 is in the ROM.
- **One extra the format does not define.** `item.appears` on a room's item says when the item
  appears:
  - `floor`: at once;
  - `foes`: when the room's foes are beaten (trigger 7);
  - `ganon`: when Ganon is beaten (trigger 3 in Ganon's room);
  - `never`: trigger 3 elsewhere. The engine hides the item at load (aldonunez
    `CreateRoomObjects`), and only Ganon's death code brings one out.

  Readers of format 1.x ignore it.
- **The owner's 2.0 flags (ZORA extra `zoraExtras`, present when one is on).** Format 1.0 has no
  fields for them:
  - `mazes`: each randomized maze (Randomize Lost Hills / Dead Woods), its four steps (the maze's
    own words: up/down/right, north/west/south) and the hint shop and hint (1-3) selling its path
    for 1 rupee;
  - `gates`: each overworld gate (Extra Raft / Power Bracelet Blocks, the mazes): its screens and
    what the logic needs to enter them (the raft, the power bracelet, the ladder, or a maze's hint
    shop).

  The potion shop's wares are listed in ware-table order (left, middle, right), so Add L4 Sword's
  middle ware shows with its price.
- **Names.** ZORA's own names, from its enums: room layouts, enemies, caves. Item names are the
  format's fixed list. A bomb-upgrade person ($4F) outside the two levels whose persons take
  the selling path (PS-BOMB-03) is "Bomb Upgrader (Talks Only)": it is a hint person whose
  code the helpful counter set to $0F (PS-HINT-05).
- **Map position.**
  - Column: `((grid column + map start) & $F) - 3`. The map shows the middle eight of the
    level's 16 bitmap columns (SH-MAP-01, `zora/generate/shapes/minimap.py`).
  - Row: the grid row + 1.
- **Level colour.** The level's wall colour (palette group 2), one NES brightness step up. The
  RGB comes from the cynes palette table that `web/zora-web.js` also uses, in
  `zora_export/nes_palette.py` with cynes' MIT licence text.
- **Who says a text.**
  - Each overworld cave's person, and each hint shop's hints.
  - In a dungeon:
    - levels 1-8: selector table A or B by the level's person init (`GameWorld.person_inits`),
      at the person's object type less $4B;
    - level 9: the fixed table C;
    - the hungry goriya always says text 18, and the life-or-money people text 27.
  - A hint shop's offers by their whole selectors (HintCaveTextSelectors0): the parsed
    `HintShopItem.quote_id` keeps only a selector's low six bits, which misreads the generated
    hint style's selectors of $40 and up.

## The spoiler log: `zora_export/spoiler_log.py`

The log is written from the document alone, so the log and the hand-off cannot disagree. Its
sections:

1. a header: version, seed, flag strings, seed code;
2. every setting, chosen and resolved;
3. the major items by place: levels (rooms and cellars), the Armos and coast spots, the caves
   and shops with prices;
4. every cave and shop's wares;
5. the texts with their speakers;
6. the requirements.

Every line is at most 80 columns.

FP-SPOIL-01 (owner rules) applies to both features:
- Making either, or not, changes no ROM byte and no random draw. `tests/test_seed_document.py`
  generates before and after a report and compares.
- What they list matches the finished ROM.
- Nothing in the ROM shows placements.

## Cross-check with the visualizer

`tests/visualizer_crosscheck.py` and the slow test `test_the_visualizer_reads_the_same_seed`
compare the two sides. The test runs the visualizer's `cli.py --seed` on the same ROMs as a
subprocess, and is skipped without `../z1r-visualizer`. It covers 56 seeds: 8 flag
combinations, with the ZORA extras, Progressive Items and Shop Items in the Item Pool.

Everything both sides read from the ROM agrees, apart from two differences on the visualizer's
side, which the test allows:

- **Trigger-3 rooms.** It shows a trigger-3 room's item as a floor item. In Ganon's room the
  Triforce of Power appears only when Ganon is beaten. Elsewhere the item never appears.
- **Long texts.** It reads at most 64 bytes of a text, so a three-line text near the limit
  ends early ("…1ST PURCH" for "…1ST PURCHASE").

Names that each side chooses for itself are not compared. For those, the check is that the two
sides' names map one to one. That covers room layouts, enemies, caves and screens, level
colours and transport staircase numbers.

## Checking the hand-off

`scripts/check_visualizer_handoff.py` is a dev check, not part of pytest. It needs:

- Chrome;
- network access for Pyodide;
- two local servers: ZORA's staged site, and the visualizer's built site served read-only from
  `../z1r-visualizer/build/site`. The script's docstring gives the commands.

It runs headless Chrome with a throwaway profile in `temp/`. It generates a seed on ZORA's
page, clicks "View in Visualizer" and waits for the visualizer's answer. It then reads the
visualizer's tab, which must name ZORA as the producer. It takes about 3 minutes, mostly
Pyodide's start.

The desktop app's built-in browser opens `window.open` targets in the same tab, which drops the
opener, so the hand-off cannot be checked there.
