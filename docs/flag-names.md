# Naming the flag fields

Flag names follow the community's conventions on z1r.wiki.

The owner names the flag fields and their option values from their own
knowledge as a player (owner decision, 2026-10-03). These names are
owner-authored and the web page shows them in place of the spec labels.

**The file:** `docs/flag-names.csv`, one row per field (118), in the page's
order: Encode level data at the top, then the option fields, then the
three-state fields. The columns:

| Column | What it holds |
|---|---|
| `page_section` | where the page shows the field |
| `field_id` | the spec's ID (C01-C27, B01-B91); the page's tooltip shows it too |
| `spec_label` | the spec's name for the field |
| `what_it_does` | one plain sentence from the spec: what the field chooses, or what a player sees with it on and off |
| `kind` | `option`, `on/off/random` for the three-state fields, or `on/off` for Encode level data (never "?", owner ruling 2026-10-06) |
| `values` | an option field's values, in order, separated by ` \| ` |
| `baseline_value` | its value in the MVP baseline (Consternation) |
| `supported` | the values ZORA produces (the support matrix) |
| `owner_name` | **yours**: the field's name on the page |
| `owner_value_names` | **yours**, option fields only: one name per value, in the order of `values`, separated by `\|` |
| `community_name` | the community's name for the field on z1r.wiki, as the wiki shows it |
| `community_source` | the wiki page it comes from |
| `match` | how sure the match is: `high`, `medium`, `low` or `none` |

**The community names (2026-10-03).** The names come from z1r.wiki's flag
pages, read as raw wiki text and matched to each field by what it does.

- Names only, as the wiki shows them. A note in brackets or an HTML comment
  in a heading is left out, and so is the description after an option
  name ("Fun% (all items share the same sprite)" becomes "Fun%").
- The wiki's own spelling is kept, such as "Gannon".
- High matches were also written into the two owner columns, with the
  wiki's option names wherever its list lines up one for one with
  `values`. Medium and lower matches were first left for the owner.
- Medium matches (owner shortcut, 2026-10-04): every medium match's
  `community_name` is copied into `owner_name` under the rulings below.
  No medium field's wiki option list lines up one for one with `values`
  (the item shuffle's list differs; the heart and Triforce ranges and the
  level-9 items have no value names on the wiki), so they keep the spec's
  value names. Fields with no match keep their spec label.
- Encode level data keeps its own label; the wiki's name for that flag is
  not used.
- Owner rulings for `owner_name` (2026-10-03); `community_name` stays as
  the wiki shows it:
  - the widget words "Dropdown" and "Drop Down" are dropped ("Armos
    Item", "Boss HP", "Level 9 Entry");
  - each starting-item switch reads "Start with" and the wiki's item name
    ("Start with Raft", "Start with 8 Bombs");
  - each range pair reads the wiki's name with "(min)" and "(max)" ("White
    Sword Hearts (min)"; likewise the magical sword's hearts and the
    Triforce range);
  - the two level-9 item fields each pick one item placed in level 9, not
    a range: they read "Level 9 Item 1" and "Level 9 Item 2".

An empty `owner_name` keeps the spec label. An empty `owner_value_names`
keeps the spec's value names. So does an empty part of it, as in
`Vanilla | | Community`. Encode level data keeps its own label and help
text, so leave its `owner_name` empty.

**Handing it back.** Open the file in Numbers, Excel or a text editor. Fill
in the two owner columns and save it in place as CSV under the same name.
Excel's "CSV UTF-8" is best, but plain CSV and semicolon-separated files
work too. Then ask for a re-import, which runs:

```bash
python3 scripts/flag_names.py import
```

The import checks the file:

- every field appears once;
- each option field has the right number of value names;
- Encode level data is left unnamed.

It then writes the names to `zora/flags/names.json`, which the page reads,
and only the two owner columns are read back. `python3 scripts/flag_names.py
generate` rewrites the other columns from `zora/flags/` and keeps the
owner's columns. `tests/test_flag_names.py` fails if the CSV and the JSON
disagree, that is, if an edit has not been imported.

**Pass names in the code (2026-10-04).** Each generation pass is named
after its flag's name above, in snake_case, and its result type follows
it. Where the flag's name would make an awkward identifier, the mapping is:

| Flag | Name | Function |
|---|---|---|
| B23 | Change "Leave your..." Rooms | `change_money_or_life_toll` (the quotes and the ellipsis) |
| C09 | "Most" Enemy HP | `change_most_enemy_hp` (the quotes) |
| B11 | Change MMG | `change_money_making_game` (the abbreviation spelled out) |

The others follow their names directly: C06 `shuffle_items`, B15
`shuffle_dungeon_drops`, B28 `shuffle_hungry_goriya`, B29
`shuffle_bomb_upgrade_men`, B22 `add_money_or_life_rooms`, B19
`shuffle_dungeon_text` (the pointer exchange, HT-TEXT-04), C03
`assign_hints_for_hint_type` (the hint assignment, post-shapes-b25.md), B27 `shuffle_dungeon_palettes`, B34
`shuffle_bosses`, B36 `shuffle_monsters_between_levels`, B32
`shuffle_dungeon_monsters`, C10 `change_boss_hp` (C09:
`change_most_enemy_hp`), B42 `shuffle_enemy_groups`, B40
`randomize_boss_groups`, C14 `exchange_rooms` (module
`dungeon_room_shuffle`), C05 `shuffle_caves`, B13 `shuffle_armos`, B01
`recorder_to_new_dungeons`, B08 `shuffle_shop_items`, B09
`extra_candles`, B31
`shuffle_overworld_monsters`, C04 `shuffle_start_screen`, B10
`change_sword_hearts`, B12 `change_bomb_upgrades`, B54 `speed_up_text`.

- B49 Book is an Atlas is a code patch only (`fp-book-01`), so it has no
  generation function.
- Turn-off values (2026-10-04, flags-behavior.md FL-OFF): each flag-switched
  step is called from one place, which tests its field of
  `zora/generate/flag_steps.py` `FlagSteps` (B49: `GameConfig.book_is_an_atlas`).
  B19 off skips only `shuffle_dungeon_text` (HT-TEXT-04); the hint
  assignment, `assign_hints_for_hint_type`, belongs to C03 Hint Type and
  always runs (owner ruling 2026-10-04). B15 switches two
  steps: `shuffle_dungeon_drops` and `second_drop_shuffle` (PS-XCHG-05).
- The ZORA extras (ZORA flag string, docs/zora-extras.md) follow the same
  rule from `zora/generate/extra_options.py` `ExtraOptions`: Randomize
  Magical Sword `randomize_magical_sword` (with its heart check
  `has_magical_sword_hearts` and the cave text `magical_sword_cave_text`)
  and Randomize Letter `randomize_letter`. With the sword on, B10's
  `change_sword_hearts` runs before the acceptance check instead of after
  the pass ships (owner requirement: the check judges the drawn N).
- B33 Shuffle Gannon and Zelda and B35 Shuffle Level 9 Monsters happen
  inside `shuffle_dungeon_monsters`, whose re-deal covers level 9 and moves
  Zelda and Ganon.
- Steps without a flag keep descriptive names: `late_gate`,
  `acceptance_check`, `move_map_near_entrance`, `generate_hint_text`,
  `draw_person_appearances`, `write_fixed_feature_data`, and the steps
  that stage an attempt's results (`build_levels`, `start_post_shapes`,
  `stage_overworld`, `enroll_caves`, `ship`). Every step is one entry of
  `generation_pass.STEPS` (docs/architecture.md).

The result types are `ItemShuffleResult` (with `ItemShuffleOptions`),
`MonsterShuffleResult`, `HintAssignmentResult`, `HintTextResult`,
`DungeonPaletteResult`, `EnemyHpResult`, `GroupShuffleResult` and
`DungeonRoomShuffleResult`.
