"""Archipelago's interface to ZORA (Archipelago Phases 4a and 4c; docs/archipelago.md "Interface").

The one module the Archipelago world calls; it never reaches further into ZORA. It wraps what
Phases 1-3 built: BUILD makes a whole ZORA seed and lists the places its items sit in, with
Archipelago's access rules (logic.py); FINISH writes Archipelago's assignment into it and makes
the ROM. Items are named by the seed format's names (model/item_names.py), places by their fixed
names (places.all_place_names), another player's item by FOREIGN.

Imports only from zora/, relatively (scripts/check_imports.py), so it works copied in alone as
worlds.zora.zora, perhaps from a zip. ZORA-mode output and the page are untouched.
"""
from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, replace
from dataclasses import field as dataclass_field
from importlib.resources import files
from importlib.resources.abc import Traversable
from types import MappingProxyType
from typing import Any

from .flags import form as flag_form
from .flags import zora_flags, zora_form
from .flags.codec import decode, encode
from .flags.dependencies import apply_dependencies, check_dependencies
from .flags.fields import (
    ENCODE_LEVEL_DATA,
    ITEM_SHUFFLE_SCOPE,
    PRINT_QUEST_INFO,
    THREE_STATE_LABELS,
    ItemShuffleScope,
    OptionField,
    PinnedItem,
    Settings,
    ThreeState,
    WoodenSwordState,
)
from .flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
from .flags.zora_flags import SWORDLISH_HIGHEST_FIELD, SWORDLISH_LOWEST_FIELD, SWORDLISH_PIECES, Swordlish
from .generate.finish import (
    FOREIGN,
    FOREIGN_ITEMS,
    AssignmentRefused,
    AssignmentUnbeatable,
    Foreign,
    ItemClass,
    hinted_foreign_places,
)
from .generate.logic import LogicModel, logic_model, triforce_event
from .generate.pipeline import Built, FlagsRefused, GenerationPlan, extra_options, plan
from .generate.pipeline import build as build_seed
from .generate.pipeline import finish as finish_seed
from .generate.places import Place, PlaceKind, own_item, read_item, triforce_spots
from .model.enums import Item
from .model.game_world import GameWorld
from .model.item_names import ITEM_NAMES, ITEMS_BY_NAME
from .model.level_items import ALL_LEVEL_ITEM_NAMES, LEVEL_9, LevelItemKind, level_item_names
from .rom import inventory, slot_identity
from .rom.base_rom import NoPlayerRom, player_rom, remember_base_rom
from .rom.code_patches import SHOPS_BY_NUMBER
from .rom.graphics_theme import GraphicsTheme, themed_player_rom
from .rom.link_art import link_sprite_set_object, offered_sprite_sets
from .rom.link_sprite import LINK_FIXED_COLORS
from .rom.mirror_overworld import mirror_screen
from .rom.player_settings import BLACKER_THAN_BLACK as REFUSED_COLOR
from .rom.player_settings import (
    BOSS_SOUND_WORD_CHARACTERS,
    BOSS_SOUND_WORD_LENGTH,
    BOSS_SOUND_WORDS,
    LEVEL_WORD_CHARACTERS,
    LEVEL_WORD_CHOICES,
    LEVEL_WORD_DASH_MAX_LENGTH,
    LEVEL_WORD_MAX_LENGTH,
    PAGE_BOSS_SOUND_WORD,
    PAGE_CHOICES,
    PAGE_HEART_SLOT,
    PAGE_LEVEL_WORD,
    PAGE_LINK_COLORS,
    PAGE_LINK_SPRITE,
    PAGE_LINK_SPRITE_SET,
    PAGE_TUNIC_SLOTS,
    PALETTE_SIZE,
    RANDOM_BOSS_SOUND_WORD,
    RANDOM_COLOR,
    RANDOM_LEVEL_WORD,
    RETIRED_PAGE_SETTINGS,
    RETIRED_SETTINGS,
    LinkSprite,
    PlayerSettingError,
    PlayerSettings,
    player_settings_from_page,
)
from .rom.revision import identify_rom
from .version import PLAYER_NAME, ZORA_VERSION

__all__ = [
    "ARRIVAL_SOUNDS",
    "CHECKS_STATE",
    "DEFAULT_FLAGS",
    "DEFAULT_ZORA_FLAGS",
    "FOREIGN",
    "GOAL_STATE",
    "HUD_READS",
    "HUD_ROW",
    "HUD_WIDTH",
    "MAX_READ_LENGTH",
    "MULTIWORLD_SETTINGS",
    "NOT_RECEIVABLE",
    "NO_MEMORY",
    "PAGE_ITEM_ARRIVAL_SOUND",
    "READ_RANGES",
    "RECEIVABLE_ITEMS",
    "RECEIVED_COUNT",
    "RECEIVE_STATE",
    "STATE_ADDRESSES",
    "BuildResult",
    "ClientMemory",
    "ClientNotReady",
    "ClientTables",
    "ClientTablesRefused",
    "Decision",
    "Foreign",
    "ItemClass",
    "NotReceivable",
    "OptionSpec",
    "OptionsConflict",
    "PlaceInfo",
    "PlayerSettingSpec",
    "RamCheck",
    "ReceivedItem",
    "RecipeNotReproduced",
    "RecipeRefused",
    "RomIdentity",
    "ServerView",
    "SlotNameRefused",
    "TextRule",
    "UnknownItem",
    "arrival_sound",
    "beta_in_use",
    "build",
    "build_from_strings",
    "check_player_settings",
    "checks_readable",
    "client_ready",
    "client_step",
    "client_tables",
    "client_tables_from_json",
    "client_tables_of",
    "client_tables_to_json",
    "finish",
    "flag_strings",
    "give_rules",
    "goal_reached",
    "hud_guard_sets",
    "hud_plans",
    "hud_record",
    "hud_writes",
    "may_receive",
    "multiworld_setting",
    "never_offered_fields",
    "never_offered_refusal",
    "option_corrections",
    "option_fields",
    "option_keys",
    "option_value_keys",
    "page_flag_strings",
    "page_player_settings",
    "pickup_checks",
    "player_setting_fields",
    "player_setting_problem",
    "receivable",
    "receive",
    "recipe",
    "recipe_give_rules",
    "rom_from_recipe",
    "rom_identity",
    "source_hash",
    "tile_buffer_end",
]


# --- options (spec "Design" 1) -------------------------------------------------------------------

# Owner decision 1: Archipelago's defaults are the page's default preset (form.metadata's
# defaultFlags: CP-5, the MVP baseline with level encoding off; every ZORA flag off).
DEFAULT_FLAGS = MVP_BASELINE_LEVEL_ENCODING_OFF
DEFAULT_ZORA_FLAGS = ""
# Encode level data (B82) is never offered and always off: its encoder is private, and an
# encoded seed is refused at plan time anyway (owner decision 2).
FORCED_OFF = ENCODE_LEVEL_DATA.id
# Item Shuffle (C06) is never offered and always Full (owner ruling, 2026-10-10): Archipelago
# places the items itself, so ZORA's item-shuffle scope has nothing to decide.
FIXED_OPTIONS = {ITEM_SHUFFLE_SCOPE.id: ItemShuffleScope.FULL}
# ZORA flags never offered and always off, keyed by name, each with the reason the page and the
# export give (owner ruling, 2026-10-17). Shuffle Wood Sword puts the wooden sword in the pool, and
# Archipelago's logic assumes it is held from the start, so bombs come from enemies (owner decision
# 1, docs/archipelago.md "Leniencies"; tests/test_logic_model.py pins it).
ZORA_FORCED_OFF = {
    "shuffle_wood_sword": "Always off in Archipelago: its logic assumes the wooden sword from the start, "
                          "so bombs come from enemies.",
    "disable_custom_music": "Not needed in Archipelago: its games have no randomized music, only Music On "
                            "or Off.",
    # Item Shuffle: Random (No Vanilla) narrows Item Shuffle, which Archipelago never offers (FIXED_OPTIONS)
    "item_shuffle_no_vanilla": "Not offered in Archipelago: it places every item itself, so Item Shuffle is "
                               "always Full.",
    # (Universal Drops v2.0 waits for a logic scan: a beta value in Archipelago since 2026-11-21, HELD_BACK.)
    # Detailed Spoiler Log (owner ruling 9, 2026-11-06): Archipelago writes its own spoiler
    "detailed_spoiler_log": "Not offered in Archipelago: it writes its own spoiler.",
    # (Item Counter, held until 2026-11-21 for want of its table in an Archipelago game's ROM, is a beta value:
    # HELD_BACK.)
}
# The ZORA_FORCED_OFF flags held for now, for a technical reason, rather than off for good: the page shows them,
# locked at off, with the reason. Every other NOT_OFFERED field is PERMANENTLY_OFF. None since 2026-11-21 (Item
# Counter, the last, became a beta value).
NOT_OFFERED_YET: frozenset[str] = frozenset()
# Z1R flags a released world offered and Archipelago now keeps off, each with its reason, kept as hidden options
# so a player's older YAML still loads: any value is accepted and ignored. Print Quest Info (B51; owner ruling 9,
# 2026-11-06): Archipelago writes its own spoiler, and B51 on would change ZORA's seed.
Z1R_FORCED_OFF = {
    PRINT_QUEST_INFO.id: "Always off in Archipelago: it writes its own spoiler, so this option is ignored.",
}
NOT_OFFERED = frozenset({FORCED_OFF, *FIXED_OPTIONS, *ZORA_FORCED_OFF, *Z1R_FORCED_OFF})
# Off (or Full) in Archipelago for good (owner, 2026-11-21): the page's Multiworld mode does not show them at all,
# and a YAML that names one still loads (each is a hidden option of the world, never_offered_fields).
PERMANENTLY_OFF = NOT_OFFERED - NOT_OFFERED_YET
# ZORA flags a released world offered and ZORA has since retired (zora_flags.RETIRED_FIELDS), each with
# its label, its value keys as that world named them (value, key, label) and the hidden option's reason. A
# YAML may still name one with any of those values: it is accepted and ignored, so a player's file from
# that release still loads. Gatekeeper Bosses: retired 2026-10-29 (docs/reports/gatekeeper-lessons.md).
RETIRED_ZORA_FLAGS: dict[str, tuple[str, tuple[tuple[int, str, str], ...], str]] = {
    "gatekeeper_bosses": ("Gatekeeper Bosses",
                          ((0, "off", "Off"), (1, "anywhere", "Anywhere"), (2, "late", "Late"), (3, "early", "Early")),
                          "Retired; a gate-based dungeon style is planned."),
}
# Archipelago games' own settings a released world offered and ZORA has since retired, in
# RETIRED_ZORA_FLAGS' form; the world keeps each as a hidden option the same way. "Other players' items
# look like" (2.0.1): retired by docs/design/archipelago-items.md piece 5, the logo by class for all.
RETIRED_MULTIWORLD_SETTINGS: dict[str, tuple[str, tuple[tuple[int, str, str], ...], str]] = {
    "foreign_item_look": ("Other players' items look like",
                          ((0, "rupee", "A rupee"), (1, "logo", "The Archipelago logo")),
                          "Retired; another player's item always shows the Archipelago logo, colored by its class."),
}
# Values ZORA generates that have not passed the logic scan for Archipelago (owner ruling, 2026-10-10). Until
# 2026-11-21 they were held back, a held toggle offering only Off; since then (owner) each is offered as a
# beta value (OptionSpec.beta): the page offers it only while Enable Beta Flags is on, with a warning, the
# exported YAML carries the warning, and the world accepts it (its own "random" never draws one). A value
# kept out for another reason is in NOT_OFFERED_VALUES. C01 = 1, 3, 4, C04 = 2, 3, B81, B03,
# Helpful hints (C03 = 1), Dungeon Quest 1st Quest (C02 = 0), the nine start items' on and Random
# (FP-START-02 to -05) and Allow Important Items in 9 (B25) passed (tests/archipelago_cases.py).
# Dungeon Quest 2nd Quest (C02 = 1) passed on 2026-10-11, once ZORA's late gate walked item
# cellars as late-gate.md says: 119 of 1,000 seeds had put an item cellar, which the game never
# reaches, under the Vertical Chute push room ($4E); now none do (docs/archipelago.md "Interface").
# Shuffle Dungeon Start Room (B26, PS-START) on and Random passed on 2026-10-11 (100 of 100 seeds
# at each, with the baseline's dungeons and with 2nd Quest's), once its row-7 fix landed (4aa8fc5).
# Remove Most Open Stairs (B30, PS-OSTAIR) on and Random passed on 2026-10-12 (100 of 100 seeds at
# each), and Book to Understand NPCs (B48, HT-BOOK) on and Random the same day (100 of 100 at
# each), and Dungeon Quest Mixed + Shapes (C02 = 4, SH-SRC-01 to SH-SRC-06) the same day (100 of 100,
# alone and with B26 on). Shuffle Bomb Upgraders Off (B29 = 0, FL-OFF-04), Oops All Enemies'
# Wizzrobes, Keese and Bouncers and Oops All Bosses' Dodongos (ZORA extras, keyed by their names)
# passed on 2026-10-13 (100 of 100 seeds at each; beta 5). Shuffle Wood Sword Cave Off (B02 = 0,
# OW-CAVE-12) and Cave Shuffle's other values (C05 = 0, 1, 2 and Random, OW-CAVE-09 to OW-CAVE-11)
# passed on 2026-10-15 (100 of 100 seeds at each; beta 6). Cave Shuffle Vanilla, Dungeons Only and
# Random (C05 = 0, 1, 4) were held back again the same day: with Randomize Dead Woods on, the Dead
# Woods Hint event went unreached, which Archipelago, making every event a location, refuses. They
# passed once the hint shops swap screens (3f35c57): 100 of 100 seeds each, with random settings for
# every other offered option. Dungeon Quest Mixed Quest, Random No Shapes and Random (C02 = 2, 5, 6;
# SH-SRC-09, SH-SRC-10) and Allow Universal Drops In Shapes (B91, SH-ROOM-16) on and Random passed on
# 2026-10-16 (100 of 100 seeds each, every event reached, with random settings for every other
# option, the other new values included). Item Shuffle's values (C06) are never held here: Item
# Shuffle is never offered and always Full (FIXED_OPTIONS). A value ZORA newly generates waits here
# for its scan, which checks every event. The ZORA 1.0 flags (version 6; docs/zora-extras.md section
# 13) are keyed by their names; Shuffle Wood Sword is never offered at all (ZORA_FORCED_OFF). Shop Items in the Item
# Pool's on, with ZORA 1.0's bait, passed on 2026-10-17 (100 of 100 seeds, every event reached, with
# random settings for every other option) and is offered (owner ruling, 2026-10-17).
# The 2026-10-18 scan of everything still held (owner request): each value with random settings for
# every other offered option, 100 seeds, every event reached, then the released values together (400
# seeds, each drawn at least 14 times). Released: the fourteen other start items, on and Random, but
# the wooden sword's; Set Ganon HP to 0 and OHKO (B41, B53) and Do Not Sort Shapes (B86), on and
# Random; Pegasus Boots and Highlight No-Drop Rooms, on and Random; "Most" Enemy HP and Boss HP's walk
# of up to 4, all zero and Random (C09, C10 = 2, 3, 4); the sword-heart ranges (C20 = 2, C21 = 1 and 2,
# C22 = 1 to 4, C23 = 1 to 4); the start pieces and the piece-count range (C18 = 1 to 9, C24 and C25 =
# 1 to 8); Starting Hearts (C16); every pin (C11, C13, C26, C27); Swords: Wood Sword Only (C07 = 1).
# Start Wood Sword and Permanent Sword Beam (B68, B52), on and Random, Starting Hearts 7, 9 and 15 (C16
# = 6, 8, 14) and Armos Item: Recorder (C11 = 10) waited for acceptance E10 (c155f9e): in one seed each
# (of 100) Ganon's room was behind level 9's last-boss shutters, which open with the Triforce of Power,
# his drop, so its rule was FALSE; with E10 each passed 100 of 100 seeds. Magical Sword Hearts (min) 13
# and 14 (C22 = 3, 4) waited for 7aa37c0's refusal of a cap below the minimum (the range was empty: 3
# and 5 seeds of 100 stopped), Level 9 Item 1 and 2 at Book and White Sword (C26, C27 = 1, 15) for
# 79216a2's refusal of the combinations that loop (E1 rejected every attempt in 5 to 12 seeds of 100);
# each passed 100 of 100 seeds at 79216a2. Those fifteen values then passed 400 of 400 seeds together
# with everything offered (each drawn at least 16 times). Allow Triforces in Stairways, On and Random,
# redesigned (2026-10-18) to work with Item Shuffle Full, its Triforces taking their spots before
# Archipelago's fill (BuildResult.triforces; 1e1e9f6, the world side ab24e8b), passed 100 of 100 seeds
# each at af98afa (64 of 160 Triforces in stairways over 20 On seeds), then 400 of 400 with everything
# offered (On drawn 136 times).
# Expanded Dungeon Locations, on and Random (the world needs nothing more: each dungeon's entrance
# rule comes from the spot it was dealt, and locations are named by what they are), released in 2fd34b5,
# was held again in 1e585a8 when the batch run on bbe10f0 found Expanded Brackets on the 2nd Quest
# overworld, seed 30, unbeatable by the logic; acceptance E11 (64109a8) fixed it. Rescanned at 64109a8:
# 100 of 100 seeds each, then 400 of 400 with everything offered, and the six seeds E11 changed (2nd
# Quest overworld: Brackets 30, 566, 252 and 603, Expanded + everything else 904 and 918) reach every
# place, event and the goal through build_from_strings.
# Add Bridges to the River and Add Lost Woods Shortcut (B87, B88), on and Random (beta 7, e8c9db7),
# waited for the logic rework that reaches the river's west side by them (6a3c660). Scanned there:
# 100 of 100 seeds at each value, Randomize Dead Woods (which forces the shortcut on, 23e1b62) On and
# Random 100 of 100 each, then 400 of 400 with everything offered (each value drawn at least 118 times).
# The 2026-10-22 scan of the beta 8 values (owner request), at b275933: each value with random settings
# for every other offered option, 100 seeds, every place, event and the goal reached, then the
# released values together (400 seeds at 3aa7cac, each value drawn at least 23 times). Released: Level
# 9 Entry's values but 8 triforces (C08 = 1 to 12; FP-TRIF-02 to FP-TRIF-06); the Uphill Battle set's
# off values and "?" (Force Ganon Fight, Add 2nd Quest Rooms, Shuffle Dungeon Monsters, Shuffle Ganon
# and Zelda, Shuffle Level 9 Monsters: B18, B20, B32, B33, B35); Dungeon Room Shuffle Vanilla and Random
# (C14 = 0, 3); Recorder to Unbeaten Dungeons, Make Important Items Drops, Add 2nd Quest Doors and Add
# 2nd Quest Monsters (B07, B39, B21, B37), on and Random. Pegasus Boots, offered since 2026-10-18,
# passed again at fa90ec1 (100 of 100 seeds On and Random).
# Swords: No Wood Sword, Swordless and Random (C07 = 2, 3, 4) are kept out, not held: NOT_OFFERED_VALUES.
HELD_BACK: dict[str, frozenset[int]] = {
    # The beta 9 export's item pins change where items may lie, which the logic reads. The 2026-10-27 scan
    # (100 seeds per value, random settings for every other offered option, every place, event and the goal
    # reached; a control of 200 seeds with the pins at the Red Candle and the Silver Arrow, already offered:
    # 199 ok, one 180 s timeout) released Coast Item: Non-Heart (C12 = 16: 98 ok, 2 generation failures, 0
    # unreachable), Level 9 Item 1 and 2 at the Bow (C26, C27 = 3: 97 ok, 2 timeouts, 1 failure, 0 unreachable)
    # and Replace Book Fire with Explosion On and Random (B47, now the blast alone: 98 of 100 ok each way, 0
    # unreachable). Level 9's places at the Wand (C26, C27 = 14) left 1 of 100 seeds with no way to Ganon's drop
    # (seed 100967: a Mixed + Shapes level 9 whose gate room the walk read at the fixed second-quest cell); that
    # walk was fixed (ac9b19e) and the rescan of 2026-10-27 released the Wand (98 ok, 2 generation failures by E1,
    # 0 unreachable). These stay held: the Ladder, the Raft, the Recorder and the Power Bracelet (C26, C27 = 5, 9,
    # 10, 8): generation failed after 2000 attempts, the acceptance check E1 rejecting every attempt, in 17, 9, 6
    # and 10 of 100 seeds (the control: none). It needs the gate item to be unreachable without itself: the Ladder
    # with Dungeon Quest 1st Quest and Dungeon Room Shuffle Vanilla (6 of 8 seeds), the Raft with Cave Shuffle
    # Vanilla; the Recorder and the Power Bracelet probably the same, with their own entrances.
    **dict.fromkeys(("C26", "C27"), frozenset({PinnedItem.LADDER, PinnedItem.POWER_BRACELET, PinnedItem.RAFT,
                                               PinnedItem.RECORDER})),
    # Gatekeeper Bosses (offered from 2026-10-28) is retired since 2026-10-29: RETIRED_ZORA_FLAGS.
    # The 2026-10-28 export's settings that change the logic wait for their scan, on and Random: Add Extra
    # Bosses (B79) puts Digdoggers and Gohmas in ordinary rooms, which the walk blocks until the recorder
    # or the bow is held (VA-REJ-17). (Shuffle Minor Dungeon Drops, B17, on and Random, is offered since
    # 2026-11-21: its bombs, five rupees and keys are locations, docs/design/archipelago-items.md piece 3;
    # the rescan at 8980bc09 built 100 of 100 seeds each way, 0 unreachable, after fixes 8f2e2257, 07d7050b
    # and e3c364d4.)
    "B79": frozenset({ThreeState.ON, ThreeState.POSSIBLE}),
    # (Bomb Upgrades in the Item Pool, docs/design/archipelago-items.md piece 8, is offered since 2026-11-21: the
    # scan at 13d63422 built 200 of 200 seeds with it on and 200 of 200 off, every other offered option random, 0
    # unreachable; each seller's room held its item, and a Raft moved there built but where the Raft guards the
    # seller's own level. It found a hint that names a Bomb Upgrade crashing, fixed with the scan.)
    # (Remove Maps, All Maps and All Compasses, B92 to B94, on and Random, are offered since 2026-10-28: the
    # scan on 7e9603c built 600 of 600 seeds with 0 unreachable places.)
    # (Mirror Overworld, B06, on and Random, is offered since 2026-10-28: pickup_checks takes the mirrored
    # screen on a mirrored seed, checked in the emulator, and the scan built 200 of 200 seeds with 0
    # unreachable places; docs/archipelago.md "Interface", Options.)
    # (Harder Bosses and Harder Ganon, ZORA version 14, from Z1M1, every level, and Item Counter, On and Random, are
    # offered since 2026-11-26: the scan at d668c4d5, temp/ap_group1_scan.py, built and finished 100 of 100 seeds at
    # each value with random settings for every other offered option, the other two Off, 0 unreachable, then 399 of
    # 400 with all three drawn too (each value drawn at least 92 times). The one seed that timed out fails ZORA's
    # generation, E1 rejecting all 2000 attempts, and its settings fail 1 of 16 seed numbers with the three as
    # drawn and 1 of 16 with Harder Bosses and Harder Ganon Off: not theirs.)
    # Offense and Defense Item Pacing (version 15, from Z1M1) are offered since 2026-10-28, every value. Archipelago's
    # logic model did not name the sword and ring counts, so the places of paced levels got rules nothing satisfied
    # (19 of 20 seeds per value unreachable); APClaude's patch to logic.py names them, and delta-debugging the slow
    # seeds found two causes, fixed: the blue ring joined the pool untracked with Shop Items in the Item Pool
    # (5ef6830), and Level 9 Item 1 or 2 at the Red Ring with Defense Earlier or at the White Sword with any Offense
    # value can never be satisfied, so the options refuse them. The rescans (100 seeds per value, random settings
    # for every other offered option): 0 unreachable places, 100 of 100 built for each of the six values, the
    # slowest seed 25 s.
    # Recorder Warping (version 15) is offered since 2026-10-28 (100 of 100 seeds built, 0 unreachable; its
    # raft-screen drop-off was checked in the emulator).
    # BogieSmalls' additions (version 16; docs/zora-extras.md section 23) are held (owner, 2026-10-29):
    # Swap Swords and Rings moves the swords and rings the logic reads. (Swordlish is kept out:
    # NOT_OFFERED_VALUES.)
    "swap_swords_and_rings": frozenset({ThreeState.ON, ThreeState.POSSIBLE}),
    # Universal Drops v2.0 (owner ruling 8, 2026-11-05; ZORA_FORCED_OFF until 2026-11-21): waits for a logic
    # scan with it on.
    "universal_drops_v2": frozenset({ThreeState.ON, ThreeState.POSSIBLE}),
    # (Item Counter, ZORA version 22, not offered until 2026-11-21: an Archipelago game's ROM gets its table too,
    # pipeline.finish, counting every location but Shuffle Minor Dungeon Drops' (B17) minor places, as ZORA mode
    # does, another player's item among them. Offered since its scan of 2026-11-26, above.)
    # Compass Chime (version 18; docs/zora-extras.md section 25) is offered, On and Random, since 2026-11-02
    # (owner): its emulator check with randomized music passed (4ceaf48, both lozft builds), and the scan
    # (temp/ap_chime_scan.py, 15 seeds On and 15 Random) built 30 of 30 with 0 unreachable, the chime's
    # player in each finished ROM exactly when the seed resolved it on. It changes no item, door or room.
}
# Values ZORA generates that Archipelago never offers, not even as beta values, each for a reason other than a
# missing scan (owner, 2026-11-21: only the HELD_BACK values became beta values).
NOT_OFFERED_VALUES: dict[str, frozenset[int]] = {
    # Swords: No Wood Sword, Swordless and Random (C07 = 2, 3, 4): Archipelago's player has a sword and bombs from
    # the start (owner decision 1), and these take the sword away.
    "C07": frozenset({WoodenSwordState.NO_WOODEN_SWORD, WoodenSwordState.SWORDLESS, WoodenSwordState.RANDOM}),
    # Swordlish (version 16) gates the wooden sword Archipelago's player starts with (owner decision 1); its range
    # stays at its defaults with it (the page's controls count from 0: piece count less one).
    "swordlish": frozenset({Swordlish.ON, Swordlish.RANDOM}),
    SWORDLISH_LOWEST_FIELD: frozenset(range(1, len(SWORDLISH_PIECES))),
    SWORDLISH_HIGHEST_FIELD: frozenset(range(len(SWORDLISH_PIECES) - 1)),
}
assert not set(HELD_BACK) & set(NOT_OFFERED_VALUES), "a field both held for its scan and kept out"
# Owner rule (2026-11-23): in Archipelago the magical-sword cave never asks for more than 12 hearts, whatever Randomize
# Magical Sword says, as a single-player seed with it on must already (zora_flags.sword_hearts_conflict). With it off
# the cave is still a logic event Archipelago must reach, and 13 or 14 could ask more hearts than the seed gives (7 of
# 600 solo scan seeds stopped generation). These values are not offered; a value that names one (an older YAML, the
# page's default preset's 14) is read as the value given here, 12, with a note (OptionSpec.clamped,
# sword_hearts_notes), never refused.
MAX_MAGICAL_SWORD_HEARTS = zora_flags.RANDOMIZED_MAGICAL_SWORD_MAX_HEARTS
SWORD_HEARTS_CLAMPED: dict[str, dict[int, int]] = {
    "C22": {3: 2, 4: 2},                                # Magical Sword Hearts (min): 13 and 14 read as 12
    "C23": {0: 2, 1: 2},                                # Magical Sword Hearts (max): 14 and 13 read as 12
    "magical_sword_hearts_highest": {4: 3, 5: 3},       # At most 13 / 14 hearts read as At most 12 hearts
}
assert not set(SWORD_HEARTS_CLAMPED) & (set(HELD_BACK) | set(NOT_OFFERED_VALUES)), "a clamped field held or kept out"
# The warning for a beta value in Archipelago (owner, 2026-11-21): the page's Multiworld mode shows it, the
# exported YAML starts with it and the world logs it, after the settings it names. In the style of
# zora/flags/form.py's BETA_* texts.
MULTIWORLD_BETA_TITLE = "Beta settings in a multiworld"
MULTIWORLD_BETA_WARNING = ("These settings have not passed ZORA's logic scan for multiworld, so they could make "
                           "generation fail or make the multiworld unbeatable. That would affect the other "
                           "players' games, not just yours.")
CHOICE, THREE_STATE, SWITCH = "choice", "three_state", "switch"
# A switch's two values; every on/off/random value is labeled as on the page (zora/flags/fields.py).
SWITCH_STATES = (ThreeState.OFF, ThreeState.ON)


@dataclass(frozen=True)
class OptionSpec:
    """One ZORA flag field as an Archipelago option: its key (its name in a player's YAML,
    stable from beta 3 on: option_key), its id (a Z1R field's, "C01" or "B08", or a ZORA flag's
    name), name and description; its kind ("choice"; "three_state": off, on, or random per
    seed; "switch": off or on); the values it offers, each with a label (only values ZORA
    generates: the support matrix's, "?" only where it allows one); and the default.
    value_keys pairs each offered value with its key (its name in a player's YAML, stable from
    beta 3 on: value_key), in the order of choices; the labels may change, the keys never.
    beta: the offered values that have not passed the logic scan (HELD_BACK), offered as beta values; never
    the default. clamped: each value not offered that is read as an offered one (SWORD_HEARTS_CLAMPED), with its
    key and label, so a YAML or flag string naming it still generates."""
    key: str
    id: str
    name: str
    description: str
    kind: str
    choices: tuple[tuple[int, str], ...]
    default: int
    value_keys: tuple[tuple[int, str], ...] = ()
    beta: tuple[int, ...] = ()
    clamped: tuple[tuple[int, int, str, str], ...] = ()     # (value, read as, its key, its label)

    @property
    def values(self) -> tuple[int, ...]:
        return tuple(value for value, _label in self.choices)

    @property
    def scanned_values(self) -> tuple[int, ...]:
        """The offered values that passed the logic scan: every value but the beta ones."""
        return tuple(value for value in self.values if value not in self.beta)

    def value_of_key(self, key: str) -> int | None:
        """The offered value this key names (a clamped value's key: the value it is read as), or None."""
        found = next((value for value, value_key in self.value_keys if value_key == key), None)
        return found if found is not None else next((read for _v, read, old, _l in self.clamped if old == key), None)

    def read_as(self, value: int) -> int:
        """The value Archipelago uses for `value`: itself, or the offered value a clamped one is read as."""
        return next((read for clamped, read, _key, _label in self.clamped if clamped == value), value)


class OptionsConflict(ValueError):
    """Option values ZORA refuses together (a dependency rule), named for the player."""

    def __init__(self, reasons: list[str]) -> None:
        super().__init__("ZORA cannot generate these options: " + "; ".join(reasons))
        self.reasons = reasons

    def __reduce__(self) -> tuple[type[OptionsConflict], tuple[list[str]]]:
        # Rebuilt from its reasons, not its message: a pickled copy (a process pool's) otherwise
        # passes the message string as the reasons and joins it letter by letter
        return type(self), (self.reasons,)


# Words a key spells differently from the community's flag names (owner, before beta 3 froze the
# keys): force_ganon_fight, shuffle_ganon_and_zelda, set_ganon_hp_to_0.
KEY_SPELLINGS = {"gannon": "ganon"}
# Fields the owner renamed on the page after beta 3 froze the keys (owner decision, 2026-10-12:
# neutral wording): each keeps its beta-3 key, so a player's YAML still works.
KEPT_KEYS = {"B29": "shuffle_bomb_upgrade_men", "B48": "book_to_understand_old_men",
             "B89": "change_hidden_ow_tiles"}            # Show Hidden OW Tiles since 2026-11-17


def key_of(name: str) -> str:
    """An option key from a name: its words in lowercase, joined by underscores ("Level 9 Entry":
    level_9_entry; '"Most" Enemy HP': most_enemy_hp)."""
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def option_key(field: flag_form.FieldDef) -> str:
    """A Z1R field's option key: its community name (docs/spec/flag-names-reference.csv, as
    zora/flags/names.json holds it; the spec label where it has none) by key_of, never its code.
    Stable from beta 3 on: tests/test_archipelago_option_keys.py pins every key, so renaming a
    flag on the page never renames an option. A key spells a word as the game does
    (KEY_SPELLINGS: the community's "Gannon" is Ganon in a key); the page's labels keep the
    community's wording. A field the owner renamed since keeps its old key (KEPT_KEYS)."""
    if field.id in KEPT_KEYS:
        return KEPT_KEYS[field.id]
    name = str(flag_form.owner_names().get(field.id, {}).get("name") or flag_form.spec_field_label(field))
    return "_".join(KEY_SPELLINGS.get(word, word) for word in key_of(name).split("_"))


# --- value keys (stable from beta 3 on) ---------------------------------------------------------------

# Archipelago reserves a choice named "random" for "Archipelago picks one", so ZORA's own Random
# (resolved per seed from the seed, FL-DEP-04) is random_per_seed in every key.
RANDOM_PER_SEED = "random_per_seed"
THREE_STATE_KEYS = {ThreeState.OFF: "off", ThreeState.ON: "on", ThreeState.POSSIBLE: RANDOM_PER_SEED}
# A key spells out what a label abbreviates; ordinals become words, so no key starts with a digit.
VALUE_SPELLINGS = (("+/-", " plus minus "), ("+", " plus "), ("%", " percent "))
VALUE_WORDS = {"1st": "first", "2nd": "second", "random": RANDOM_PER_SEED}
# A label that is only a number gets its option's unit first ("3" in Starting Hearts: hearts_3).
VALUE_UNITS = {"C16": "hearts", "C17": "items", "C18": "pieces", "C20": "hearts", "C21": "hearts",
               "C22": "hearts", "C23": "hearts", "C24": "triforces", "C25": "triforces"}
DEFAULT_VALUE_UNIT = "value"              # a new field's number labels, until it is given a unit
# Keys the rule below would spell unevenly (Level 9 Entry's "1 triforce", Starting Hearts' range).
VALUE_KEY_OVERRIDES = {("C08", 7): "triforces_1", ("C16", 16): "hearts_1_to_5"}
# ZORA flags' values the rule would key unclearly: Swordlish's Random picks among five sword states, Swordlish one
# of them, and random_per_seed alone would read as Swords' Random (owner, 2026-10-30; never shipped, held).
ZORA_VALUE_KEY_OVERRIDES = {("swordlish", int(Swordlish.RANDOM)): "random_with_swordlish"}


def value_key(label: str, unit: str | None = None) -> str:
    """A value's key from its label: its words by key_of, abbreviations spelled out, ordinals as
    words, Random as random_per_seed, and a leading number moved last behind its unit or noun
    ("Mixed Quest - 1st": mixed_quest_first; "+/- 2": plus_minus_2; "8 triforces": triforces_8;
    "0 HP": hp_0; "3" with unit hearts: hearts_3, without one value_3)."""
    text = label
    for written, spelled in VALUE_SPELLINGS:
        text = text.replace(written, spelled)
    words = [VALUE_WORDS.get(word, word) for word in key_of(text).split("_")]
    if words[0].isdigit():
        if len(words) == 1:
            words = [unit or DEFAULT_VALUE_UNIT, *words]
        else:
            words = [*words[1:], words[0]]
    return "_".join(words)


def _z1r_value_keys(field: flag_form.FieldDef) -> dict[int, str]:
    """Every value of a Z1R field (offered or not) and its key."""
    if not isinstance(field, OptionField):
        return {int(state): key for state, key in THREE_STATE_KEYS.items()}
    return {index: VALUE_KEY_OVERRIDES.get((field.id, index))
            or value_key(flag_form.value_label(field, index), VALUE_UNITS.get(field.id))
            for index in range(field.count)}


def _zora_value_keys(field: Mapping[str, Any]) -> dict[int, str]:
    """Every value of a ZORA flag and its key."""
    if field["kind"] == "option":
        return {value["value"]: (ZORA_VALUE_KEY_OVERRIDES.get((field["name"], value["value"]))
                                 or value_key(value["label"]))
                for value in sorted(field["values"], key=lambda value: value["value"])}     # in value order
    states = THREE_STATE_KEYS if field["kind"] == zora_form.THREE_STATE_KIND else dict.fromkeys(SWITCH_STATES)
    return {int(state): THREE_STATE_KEYS[state] for state in states}


def option_value_keys() -> dict[str, dict[int, str]]:
    """Each offered option's id and the key of every one of its values, offered or not (a value
    released later keeps the key it has now): docs/archipelago.md "Value keys"."""
    keys = {field.id: _z1r_value_keys(field) for field in flag_form.ALL_FIELDS if field.id not in NOT_OFFERED}
    keys |= {field["name"]: _zora_value_keys(field) for field in zora_form.FIELDS if field["name"] not in NOT_OFFERED}
    for option, values in keys.items():
        assert len(set(values.values())) == len(values), f"two values of {option} share a key"
    return keys


def _beta_values(field_id: str, choices: tuple[tuple[int, str], ...], default: int) -> tuple[int, ...]:
    """The offered values of a field that wait for their logic scan (HELD_BACK): its beta values."""
    beta = tuple(value for value, _label in choices if value in HELD_BACK.get(field_id, frozenset()))
    assert default not in beta, f"{field_id}'s default waits for its logic scan"
    return beta


def _z1r_spec(field: flag_form.FieldDef, defaults: Settings) -> OptionSpec:
    is_option = isinstance(field, OptionField)
    clamps = SWORD_HEARTS_CLAMPED.get(field.id, {})
    kept_out = NOT_OFFERED_VALUES.get(field.id, frozenset()) | set(clamps)
    choices = tuple((int(value), flag_form.value_label(field, value)) for value in flag_form.supported_values(field)
                    if value not in kept_out)
    preset = defaults.options if is_option else defaults.toggles
    default = int(preset[field.id]) if field.id in preset else choices[0][0]     # a field newer than the preset
    default = clamps.get(default, default)
    keys = _z1r_value_keys(field)
    clamped = tuple((value, read, keys[value], flag_form.value_label(field, value)) for value, read in clamps.items())
    return OptionSpec(option_key(field), field.id, flag_form.field_label(field), field.setting,
                      CHOICE if is_option else THREE_STATE, choices, default,
                      tuple((value, keys[value]) for value, _label in choices),
                      _beta_values(field.id, choices, default), clamped)


# Triforce Shuffle and Map & Compass Shuffle (ZORA version 23, docs/design/archipelago-items.md pieces 6 and 7) are
# offered at every value; Archipelago's default is Anywhere (owner, 2026-11-25), a single-player seed's Off. Anywhere
# is 2.0.2's test release's On, whose scan (section 8) built 100 of 100 seeds each alone and together, 0 unreachable.
# The page's form names them ("multiworldDefault"), and sets them when switched to Multiworld mode.
ARCHIPELAGO_ZORA_DEFAULTS = {field["name"]: int(field["multiworldDefault"]) for field in zora_form.FIELDS
                             if "multiworldDefault" in field}
# Options renamed after a release offered them (owner, 2026-11-25): 2.0.2's test release's two switches became
# Triforce Shuffle and Map & Compass Shuffle. A YAML that names an old key still loads, read as the new option with a
# note: on (or true) is Anywhere, off (or false) is Off.
RENAMED_OPTIONS = {"add_triforces_to_pool": zora_flags.TRIFORCE_SHUFFLE_FIELD,
                   "add_maps_compasses_to_pool": zora_flags.MAP_COMPASS_SHUFFLE_FIELD}
RENAMED_OPTION_VALUES = {**dict.fromkeys(("on", "true"), int(zora_flags.LevelItemShuffle.ANYWHERE)),
                         **dict.fromkeys(("off", "false"), int(zora_flags.LevelItemShuffle.OFF))}


def renamed_option(old_key: str, given: object) -> tuple[str, int | None, str]:
    """A renamed option's value (RENAMED_OPTIONS): the new key, the value it is read as (None for a value the old
    option never had) and the note for the player."""
    new_key = RENAMED_OPTIONS[old_key]
    word = str(given).strip().lower()
    value = RENAMED_OPTION_VALUES.get(word)
    spec = next(spec for spec in option_fields() if spec.key == new_key)
    if value is None:
        return new_key, None, (f"{old_key} was renamed {new_key}, and {given!r} is not one of its old values (on, "
                               f"off); {spec.name} keeps its default")
    label = dict(spec.choices)[value]
    return new_key, value, f"{old_key} was renamed {new_key}: {word} is read as {spec.name}: {label}"


def _zora_spec(field: Mapping[str, Any], defaults: zora_flags.ZoraFlags) -> OptionSpec:
    name = field["name"]
    clamps = SWORD_HEARTS_CLAMPED.get(name, {})
    kept_out = NOT_OFFERED_VALUES.get(name, frozenset()) | set(clamps)
    if field["kind"] == "option":
        kind, choices = CHOICE, tuple((value["value"], value["label"]) for value in field["values"]
                                      if value["value"] not in kept_out)
    elif field["kind"] == zora_form.THREE_STATE_KIND:
        kind, choices = THREE_STATE, tuple((int(state), label) for state, label in THREE_STATE_LABELS.items()
                                           if state not in kept_out)
    else:
        kind, choices = SWITCH, tuple((int(state), THREE_STATE_LABELS[state]) for state in SWITCH_STATES
                                      if state not in kept_out)
    default = zora_form.control_value(defaults, name) if hasattr(defaults, name) else choices[0][0]
    default = ARCHIPELAGO_ZORA_DEFAULTS.get(name, clamps.get(default, default))
    keys = _zora_value_keys(field)
    labels = {value["value"]: value["label"] for value in field.get("values", ())}
    clamped = tuple((value, read, keys[value], labels[value]) for value, read in clamps.items())
    return OptionSpec(name, name, field["label"], field["help"], kind, choices, default,     # key: its name
                      tuple((value, keys[value]) for value, _label in choices), _beta_values(name, choices, default),
                      clamped)


def option_fields() -> list[OptionSpec]:
    """Every ZORA flag field Archipelago offers, from zora/flags (the page's fields, labels,
    support matrix and ZORA Extras tab), so a new field appears here by itself: the Z1R fields
    but B82 and C06, without the NOT_OFFERED_VALUES and with the HELD_BACK values as beta values, then
    the ZORA flags but Shuffle Wood Sword (NOT_OFFERED)."""
    defaults = decode(DEFAULT_FLAGS)
    zora_defaults = zora_flags.decode(DEFAULT_ZORA_FLAGS)
    specs = [_z1r_spec(field, defaults) for field in flag_form.ALL_FIELDS if field.id not in NOT_OFFERED]
    specs += [_zora_spec(field, zora_defaults) for field in zora_form.FIELDS if field["name"] not in NOT_OFFERED]
    keys = [spec.key for spec in specs]
    assert len(set(keys)) == len(keys), "two options share a key"
    return specs


def option_keys() -> dict[str, str]:
    """Each offered option's id and its key (C16: starting_hearts)."""
    return {spec.id: spec.key for spec in option_fields()}


def never_offered_fields() -> list[OptionSpec]:
    """The ZORA flags Archipelago never offers (ZORA_FORCED_OFF) and the retired ones a released world
    offered (RETIRED_ZORA_FLAGS), each with every value and its reason as the description. The world
    keeps each as a hidden option, so a YAML that names one gets never_offered_refusal's verdict
    rather than Archipelago's "not a valid option name" warning."""
    zora_defaults = zora_flags.decode(DEFAULT_ZORA_FLAGS)
    forced_off = [replace(_zora_spec(field, zora_defaults), description=ZORA_FORCED_OFF[field["name"]])
                  for field in zora_form.FIELDS if field["name"] in ZORA_FORCED_OFF]
    retired = [OptionSpec(key, key, label, reason, CHOICE, tuple((value, name) for value, _key, name in values),
                          values[0][0], tuple((value, value_key) for value, value_key, _name in values))
               for key, (label, values, reason) in (RETIRED_ZORA_FLAGS | RETIRED_MULTIWORLD_SETTINGS).items()]
    z1r_defaults = decode(DEFAULT_FLAGS)
    z1r_forced_off = [replace(_z1r_spec(flag_form.FIELDS_BY_ID[field_id], z1r_defaults), description=reason)
                      for field_id, reason in Z1R_FORCED_OFF.items()]
    return forced_off + retired + z1r_forced_off


def _z1r_forced_off_keys() -> frozenset[str]:
    """Z1R_FORCED_OFF's fields by option key and by id."""
    return frozenset(key for field_id in Z1R_FORCED_OFF
                     for key in (field_id, option_key(flag_form.FIELDS_BY_ID[field_id])))


def _is_off(given: object) -> bool:
    """A YAML value meaning off: the key, its number, or a YAML 1.1 false (an unquoted off)."""
    if isinstance(given, str):
        return given.strip().lower() in (THREE_STATE_KEYS[ThreeState.OFF], "false")
    return given is False or (type(given) is int and given == ThreeState.OFF)


def never_offered_refusal(key: str, given: object) -> str | None:
    """Why a YAML's value for a ZORA flag Archipelago never offers (ZORA_FORCED_OFF) is refused, or
    None for off, which ZORA uses anyway, and for any value of a retired flag (RETIRED_ZORA_FLAGS) or a Z1R
    flag kept off (Z1R_FORCED_OFF), which is ignored."""
    if _is_off(given) or key in RETIRED_ZORA_FLAGS | RETIRED_MULTIWORLD_SETTINGS or key in _z1r_forced_off_keys():
        return None
    label = next(field["label"] for field in zora_form.FIELDS if field["name"] == key)
    return (f"{label} ({key}): {given!r} is not offered. {ZORA_FORCED_OFF[key]} "
            f"Remove {key} from the YAML (or set it to off).")


def _chosen(values: Mapping[str, object]) -> dict[str, int]:
    """Every option's value by id: the given ones (each option by its key or its id, each value
    by its number or its value key, one value the option offers), the rest the defaults."""
    fields = option_fields()
    specs = {spec.id: spec for spec in fields} | {spec.key: spec for spec in fields}
    values = {name: given for name, given in values.items() if name not in _z1r_forced_off_keys()}   # ignored
    unknown = sorted(set(values) - set(specs))
    if unknown:
        never = [f"{key} is never offered: {ZORA_FORCED_OFF[key]}" for key in unknown if key in ZORA_FORCED_OFF]
        others = [key for key in unknown if key not in ZORA_FORCED_OFF]
        raise OptionsConflict(never + ([f"unknown options {others}"] if others else []))
    twice = sorted(spec.key for spec in fields if spec.key != spec.id and spec.key in values and spec.id in values)
    if twice:
        raise OptionsConflict([f"options given by key and by id: {twice}"])
    chosen = {spec.id: spec.default for spec in fields}
    for name, given in values.items():
        spec = specs[name]
        value = spec.value_of_key(given) if isinstance(given, str) else given
        if isinstance(value, int):
            value = spec.read_as(value)             # a clamped value: the one Archipelago uses (SWORD_HEARTS_CLAMPED)
        if not isinstance(value, int) or value not in spec.values:
            names = spec.key if spec.key == spec.id else f"{spec.key}, {spec.id}"
            offered = [f"{number} ({key})" for number, key in spec.value_keys]
            raise OptionsConflict([f"{spec.name} ({names}): {given!r} is not one of {offered}"])
        chosen[spec.id] = int(value)
    return chosen


def _settings(chosen: Mapping[str, int]) -> Settings:
    toggles = {field.id: ThreeState(chosen[field.id]) for field in flag_form.ALL_FIELDS
               if not isinstance(field, OptionField) and field.id != FORCED_OFF and field.id not in Z1R_FORCED_OFF}
    options = {field.id: chosen[field.id] for field in flag_form.ALL_FIELDS
               if isinstance(field, OptionField) and field.id not in FIXED_OPTIONS}
    return decode(DEFAULT_FLAGS).updated(options={**options, **FIXED_OPTIONS},
                                         toggles={**toggles, FORCED_OFF: ThreeState.OFF,
                                                  **dict.fromkeys(Z1R_FORCED_OFF, ThreeState.OFF)})


def beta_in_use(values: Mapping[str, object]) -> list[str]:
    """The beta values among these options (OptionSpec.beta: not through the logic scan), each as
    "Name: Label", in option_fields' order. OptionsConflict as flag_strings would raise it for a value
    that is not offered."""
    chosen = _chosen(values)
    return [f"{spec.name}: {dict(spec.choices)[chosen[spec.id]]}" for spec in option_fields()
            if chosen[spec.id] in spec.beta]


def option_corrections(values: Mapping[str, object]) -> list[str]:
    """What ZORA changes in these options, as the page shows it, never refused: FL-DEP-02 rule 4
    turns B28 and B29 off with second-quest, mixed or mixed-with-shapes dungeons."""
    asked = _settings(_chosen(values))
    adjusted = apply_dependencies(asked)
    return [f"FL-DEP-02 rule 4 turns {field_id} off" for field_id in sorted(adjusted.toggles)
            if adjusted.toggle(field_id) != asked.toggle(field_id)]


def _flags_of(chosen: Mapping[str, int]) -> tuple[Settings, zora_flags.ZoraFlags]:
    """Every option's value by id as ZORA's settings and ZORA flags: the fields Archipelago never offers at the
    one value it uses."""
    return _settings(chosen), zora_flags.decode(zora_form.zora_flags_from_values(
        # a ZORA flag never offered (ZORA_FORCED_OFF) is off
        {field["name"]: chosen.get(field["name"], int(ThreeState.OFF)) for field in zora_form.FIELDS}))


def page_flag_strings(chosen: Mapping[str, int]) -> tuple[str, str]:
    """Option values by id (offered values; a missing one at its default) as the page's two flag strings,
    unchecked: the page shows any conflict itself. For loading a player's YAML into the page."""
    fields = option_fields()
    by_id = {spec.id: spec for spec in fields}
    assert all(field_id in by_id and value in by_id[field_id].values for field_id, value in chosen.items())
    settings, zora = _flags_of({spec.id: spec.default for spec in fields} | dict(chosen))
    return encode(settings), zora_flags.encode(zora)


def flag_strings(values: Mapping[str, object]) -> tuple[str, str]:
    """Archipelago's option values (OptionSpec key or id -> value, by number or value key; a missing
    option takes its default)
    as ZORA's (flag string, ZORA flag string). Every dependency rule is checked here, so a
    refusal never comes later from inside generation: OptionsConflict names each conflict (the
    pin and prerequisite rules, Add L4 Sword without Progressive Items, Extra Power Bracelet
    Blocks with B04, the magical sword's heart cap). B23 is kept as given whatever B22 is (FL-DEP-06)."""
    chosen = _chosen(values)
    settings, zora = _flags_of(chosen)
    reasons = [f"{refusal.rule}: {refusal.message}" for refusal in check_dependencies(settings)]
    reasons += zora_flags.validate(zora, apply_dependencies(settings))
    if reasons:
        raise OptionsConflict(reasons)
    strings = encode(settings), zora_flags.encode(zora)
    try:
        plan(strings[0], 0, strings[1])
    except FlagsRefused as refused:          # the last guard: any rule not named above
        raise OptionsConflict(list(refused.reasons)) from refused
    return strings


# --- player settings (P3) ----------------------------------------------------------------------------

COLOR, WORD = "color", "word"
# The page's labels (web/zora-web.js PLAYER_CHOICES, PLAYER_COLORS and the two word rows, its
# Cosmetic tab); tests/test_archipelago_player_settings.py reads the page and checks it says the same.
# Keys, values, defaults and rules come from zora/rom/player_settings.py, which finish() reads.
PLAYER_SETTING_LABELS = {
    "selectButton": "Select button", "lowHealthBeep": "Low-health beep", "deathWarp": "Death-warp",
    "reduceFlashing": "Reduce flashing", "cropGuide": "Crop guide", "music": "Music", "graphicsTheme": "Graphics theme",
    "greenTunic": "Green tunic", "blueRingTunic": "Blue ring", "redRingTunic": "Red ring", PAGE_HEART_SLOT: "Hearts",
    PAGE_LEVEL_WORD: "Level name", PAGE_BOSS_SOUND_WORD: "Boss-sound label",
    PAGE_LINK_SPRITE: "Playable character", PAGE_LINK_COLORS[0]: "Playable character's color 2",
    PAGE_LINK_COLORS[1]: "Playable character's color 3",
}
# The playable character's choice (the page's Link sprite row, web/zora-web.js linkSpriteRow): PRG0's
# Link, one of ZORA's built-in sets by its id (the page's "built-in:" choices; a file the player loads
# is the page's alone), or Random (the seed number picks).
LINK_SPRITE_ORIGINAL = LinkSprite.LINK.value
LINK_SPRITE_ORIGINAL_LABEL = "Link (original)"
# Built-in sets beta 11 offered and ZORA has since removed (2026-11-02): the original Link
RETIRED_LINK_SPRITE_KEYS = ("merchant", "old_man", "old_woman", "zelda")
PLAYER_CHOICE_LABELS = {
    "selectButton": {"off": "Off", "swap": "Swap only", "toggle": "Toggle"},
    "lowHealthBeep": {"removed": "Removed", "kept": "Kept", "half-speed": "Half speed",
                      "quarter-speed": "Quarter speed", "random": "Random"},
    "deathWarp": {"p2-up-a": "Controller 2 Up+A", "p1-up-a": "Controller 1 Up+A",
                  "p1-up-select": "Controller 1 Up+Select"},
    "reduceFlashing": {"off": "Off", "on": "On"},
    "cropGuide": {"on": "On", "off": "Off"},
    "music": {"on": "On", "off": "Off"},
    "graphicsTheme": {"off": "Off", "halloween": "Halloween"},
}
RANDOM_WORD_LABEL = "Random"
# The Archipelago games' own settings (owner decisions 2026-10-18; the beta 5 fixes spec items 4
# and 5), shown only in the page's Multiworld mode: by page key, the label, the default and the
# (value, label) choices. Item arrival: the sound the client plays when it gives a received item. (The
# foreign item's look, foreignItemLook, is retired: RETIRED_PAGE_SETTINGS, RETIRED_MULTIWORLD_SETTINGS.)
PAGE_ITEM_ARRIVAL_SOUND = "itemArrivalSound"
ARRIVAL_SOUNDS = {"item-appears": inventory.ITEM_APPEARS_SOUND, "item-taken": inventory.ITEM_TAKEN_SOUND,
                  "none": 0}
MULTIWORLD_SETTINGS: dict[str, tuple[str, str, tuple[tuple[str, str], ...]]] = {
    PAGE_ITEM_ARRIVAL_SOUND: ("Sound when an item arrives", "item-appears",
                              (("item-appears", "Item appears"), ("item-taken", "Item taken"), ("none", "None"))),
}
# Every NES palette value but $0D (FP-SET-02, FP-SET-03; player_settings.check_palette_value), and
# Random (RANDOM_COLOR, one past the palette).
ALLOWED_COLORS = (*(value for value in range(PALETTE_SIZE) if value != REFUSED_COLOR), RANDOM_COLOR)
NO_RANDOM_COLORS = ALLOWED_COLORS[:-1]
# A Random choice's value key in a player's YAML, by kind. Never "random": Archipelago reads that word as
# its own (any one of the option's values, drawn when the multiworld is generated).
RANDOM_COLOR_KEY = "random_color"
RANDOM_CHOICE_KEY = "random_choice"
RANDOM_CHOICE = "random"                  # a choice's Random as the page has it (lowHealthBeep)


@dataclass(frozen=True)
class TextRule:
    """A word setting's rule. What the player types loses its outer spaces and becomes capitals;
    the word is then `min_length` to `max_length` of `characters` (the game's font), or `random`
    (the boss-sound label's or the level name's Random). The level name's label keeps its dash for a word of at most
    `dash_max_length` characters ("CASTLE-1"; "DUNGEON1")."""
    min_length: int
    max_length: int
    characters: str
    random: str | None = None
    dash_max_length: int | None = None


@dataclass(frozen=True)
class PlayerSettingSpec:
    """One player setting as data: its key (as a recipe's playerSettings holds it; finish() also
    takes it), label and kind: "choice" (one of `choices`, (value, label) pairs), "color" (one of
    `colors`, NES palette values) or "word" (one of `choices`, or any word `rule` allows); and
    its default. yaml_key is its name in a player's YAML and value_keys pairs each listed value
    with its YAML name (a choice's in underscore words, a color's as hex, a listed word's in
    lowercase, the boss-sound label's Random as random_word), both stable from beta 3 on;
    finish() and recipe() take either form (page_player_settings)."""
    key: str
    label: str
    kind: str
    default: str | int
    choices: tuple[tuple[str, str], ...] = ()
    colors: tuple[int, ...] = ()
    rule: TextRule | None = None
    yaml_key: str = ""
    value_keys: tuple[tuple[str | int, str], ...] = ()
    # Shown only in the page's Multiworld mode: an Archipelago game's setting, which ZORA's own
    # generation never reads (MULTIWORLD_SETTINGS).
    multiworld_only: bool = False
    # Value keys a released world offered and ZORA has since removed: a YAML may still give one, and
    # it reads as the default (no longer listed, so Archipelago's random never picks one)
    retired_keys: tuple[str, ...] = ()


LEVEL_WORD_RULE = TextRule(1, LEVEL_WORD_MAX_LENGTH, LEVEL_WORD_CHARACTERS, dash_max_length=LEVEL_WORD_DASH_MAX_LENGTH)
BOSS_SOUND_WORD_RULE = TextRule(BOSS_SOUND_WORD_LENGTH, BOSS_SOUND_WORD_LENGTH, BOSS_SOUND_WORD_CHARACTERS,
                                random=RANDOM_BOSS_SOUND_WORD)


# Each player setting's YAML key, by its page key (stable from beta 3 on).
PLAYER_SETTING_KEYS = {
    "selectButton": "select_button", "lowHealthBeep": "low_health_beep", "deathWarp": "death_warp",
    "reduceFlashing": "reduce_flashing", "cropGuide": "crop_guide", "music": "music", "graphicsTheme": "graphics_theme",
    "greenTunic": "green_tunic", "blueRingTunic": "blue_ring_tunic", "redRingTunic": "red_ring_tunic",
    PAGE_HEART_SLOT: "hearts", PAGE_LEVEL_WORD: "level_word", PAGE_BOSS_SOUND_WORD: "boss_sound_word",
    PAGE_LINK_SPRITE: "playable_character", PAGE_LINK_COLORS[0]: "playable_character_color_2",
    PAGE_LINK_COLORS[1]: "playable_character_color_3",
    PAGE_ITEM_ARRIVAL_SOUND: "item_arrival_sound",
}
RANDOM_WORD_KEY = "random_word"           # the boss-sound label's RANDOM, which the recipe keeps


def color_key(color: int) -> str:
    """A color's value key: its NES palette value in hex ("0x29"), or Random's "random"."""
    return RANDOM_COLOR_KEY if color == RANDOM_COLOR else f"0x{color:02X}"


def _player_value_keys(kind: str, key: str, values: Iterable[str | int]) -> tuple[tuple[str | int, str], ...]:
    if kind == COLOR:
        return tuple((value, color_key(int(value))) for value in values)
    if kind == WORD:
        randoms = {PAGE_BOSS_SOUND_WORD: RANDOM_BOSS_SOUND_WORD, PAGE_LEVEL_WORD: RANDOM_LEVEL_WORD}
        return tuple((value, RANDOM_WORD_KEY if value == randoms.get(key) else str(value).lower()) for value in values)
    return tuple((value, RANDOM_CHOICE_KEY if value == RANDOM_CHOICE else str(value).replace("-", "_"))
                 for value in values)


def player_setting_fields() -> list[PlayerSettingSpec]:
    """Every player setting, in the page's order (P3): the choices, the tunic and heart colors,
    the level name and the boss-sound label, then the Archipelago games' own (MULTIWORLD_SETTINGS,
    multiworld_only: the page shows them only in its Multiworld mode). A player's YAML gives each by its key; a recipe's
    playerSettings holds them as given, and finish() and rom_from_recipe accept exactly these."""
    defaults = PlayerSettings()
    assert set(PLAYER_CHOICE_LABELS) == set(PAGE_CHOICES), "a page choice without labels"
    specs = []
    for key, (field, values) in PAGE_CHOICES.items():
        default = next(value for value, setting in values.items() if setting == getattr(defaults, field))
        specs.append(PlayerSettingSpec(key, PLAYER_SETTING_LABELS[key], CHOICE, default,
                                       tuple((value, PLAYER_CHOICE_LABELS[key][value]) for value in values)))
    sprites = ((LINK_SPRITE_ORIGINAL, LINK_SPRITE_ORIGINAL_LABEL),
               *((set_id, link_sprite_set_object(sprite_set)["name"])
                 for set_id, sprite_set in offered_sprite_sets().items()),
               (RANDOM_CHOICE, RANDOM_WORD_LABEL))
    specs.append(PlayerSettingSpec(PAGE_LINK_SPRITE, PLAYER_SETTING_LABELS[PAGE_LINK_SPRITE], CHOICE,
                                   defaults.link_sprite.value, sprites, retired_keys=RETIRED_LINK_SPRITE_KEYS))
    slots = (*zip(PAGE_TUNIC_SLOTS, defaults.tunic_colors, strict=True),)
    specs += [PlayerSettingSpec(key, PLAYER_SETTING_LABELS[key], COLOR, default, colors=ALLOWED_COLORS)
              for key, default in slots]
    # The character's colors 2 and 3 (sets drawn in other colors): no Random, as on the page
    specs += [PlayerSettingSpec(key, PLAYER_SETTING_LABELS[key], COLOR, default, colors=NO_RANDOM_COLORS)
              for key, default in zip(PAGE_LINK_COLORS, LINK_FIXED_COLORS, strict=True)]
    specs.append(PlayerSettingSpec(PAGE_HEART_SLOT, PLAYER_SETTING_LABELS[PAGE_HEART_SLOT], COLOR,
                                   defaults.heart_color, colors=ALLOWED_COLORS))
    level_words = (*((word, word) for word in LEVEL_WORD_CHOICES), (RANDOM_LEVEL_WORD, RANDOM_WORD_LABEL))
    specs.append(PlayerSettingSpec(PAGE_LEVEL_WORD, PLAYER_SETTING_LABELS[PAGE_LEVEL_WORD], WORD, defaults.level_word,
                                   level_words, rule=LEVEL_WORD_RULE))
    boss_words = ((defaults.boss_sound_word, defaults.boss_sound_word), (RANDOM_BOSS_SOUND_WORD, RANDOM_WORD_LABEL),
                  *((word, word) for word in BOSS_SOUND_WORDS))
    specs.append(PlayerSettingSpec(PAGE_BOSS_SOUND_WORD, PLAYER_SETTING_LABELS[PAGE_BOSS_SOUND_WORD], WORD,
                                   defaults.boss_sound_word, boss_words, rule=BOSS_SOUND_WORD_RULE))
    specs += [PlayerSettingSpec(key, label, CHOICE, default, choices, multiworld_only=True)
              for key, (label, default, choices) in MULTIWORLD_SETTINGS.items()]
    return [replace(spec, yaml_key=PLAYER_SETTING_KEYS[spec.key], value_keys=_player_value_keys(
        spec.kind, spec.key, spec.colors if spec.kind == COLOR else (value for value, _label in spec.choices)))
        for spec in specs]


def page_player_settings(values: Mapping[str, Any]) -> dict[str, Any]:
    """Player settings as the page names them (a recipe's playerSettings, as finish() reads them),
    from a player's YAML or a recipe: each setting by its page key (selectButton) or its YAML key
    (select_button), each value as the page has it (p1-up-a, 41, RANDOM) or by its value key
    (p1_up_a, "0x29", random_word). Page forms pass through unchanged, so a recipe written before
    the keys reads as it did; anything else is left for player_settings_from_page to judge. A
    retired setting (the statistics screen, always on since 2026-10-17), by either key, is dropped."""
    specs = {spec.key: spec for spec in player_setting_fields()}
    by_yaml = {spec.yaml_key: spec for spec in specs.values() if spec.yaml_key != spec.key}
    both = sorted(spec.yaml_key for spec in by_yaml.values() if spec.yaml_key in values and spec.key in values)
    if both:
        raise PlayerSettingError(f"player settings given by YAML key and by page key: {both}")
    page: dict[str, Any] = {}
    for name, value in values.items():
        if name in RETIRED_SETTINGS | RETIRED_PAGE_SETTINGS:
            continue
        spec = by_yaml.get(name) or specs.get(name)
        if spec is None:
            page[name] = value
            continue
        page[spec.key] = _page_value(spec, value)
    chosen = page.get(PAGE_LINK_SPRITE)
    built_in = offered_sprite_sets().get(chosen) if isinstance(chosen, str) else None
    if built_in is not None:      # a built-in set by its id, as the page sends one: the set itself
        page[PAGE_LINK_SPRITE] = LinkSprite.SET.value
        page[PAGE_LINK_SPRITE_SET] = link_sprite_set_object(built_in)
    return page


def multiworld_setting(values: Mapping[str, Any], key: str) -> str:
    """One of MULTIWORLD_SETTINGS' values from player settings in any form finish() takes (by page
    or YAML key, the page's value or its value key), its default when left out; PlayerSettingError
    for a value it does not list. player_settings_from_page never reads these keys."""
    _label, default, choices = MULTIWORLD_SETTINGS[key]
    value = page_player_settings(values).get(key, default)
    if value not in dict(choices):
        raise PlayerSettingError(f"{key}: unknown choice {value!r}")
    return str(value)


def _page_value(spec: PlayerSettingSpec, value: Any) -> Any:
    """A value by its value key as the page has it; any other value unchanged. A word is typed
    freely (any case), so only random_word is a key there. A retired value, by its key or the page's
    spelling (old-man), reads as the default."""
    if not isinstance(value, str):
        return value
    if value.replace("-", "_") in spec.retired_keys:
        return spec.default
    listed = {key: page_value for page_value, key in spec.value_keys}
    if spec.kind == COLOR:
        return {key.lower(): color for key, color in listed.items()}.get(value.lower(), value)
    if spec.kind == WORD:
        return listed[value] if value == RANDOM_WORD_KEY and value in listed else value
    return listed.get(value, value)


# --- build and finish (spec "Design" 2 and 3) ------------------------------------------------------

class UnknownItem(ValueError):
    """An item name that is not the seed format's name of an item."""


class NotReceivable(ValueError):
    """An item name that is never an Archipelago item (receivable() is False), given to receive()."""


@dataclass(frozen=True)
class PlaceInfo:
    """One place Archipelago may put an item in: its fixed name, its kind ("room", "cellar",
    "cave", "shop ware", "potion shop"), the items it must never hold (by name), the heart
    containers its cave asks for before handing over its item (the sword caves; R2), and whether
    it is a minor place (Place.minor: Shuffle Minor Dungeon Drops' bombs, five rupees or key, a
    filler spot that the Item Counter never counts), and whether it is a compass spot (Place.compass_spot: in
    per-level mode the room or item cellar a level's compass marks, which takes no world's filler)."""
    name: str
    kind: str
    forbids: tuple[str, ...]
    hearts: int | None
    minor: bool = False
    compass_spot: bool = False


@dataclass(frozen=True)
class BuildResult:
    """BUILD's answer for Archipelago's generation: the places, the access rules, the items this
    seed adds to the pool (by name, one per place), `state`, opaque, for finish(), and each
    Triforce's spot as (event, place name), levels 1-8 in order (places.triforce_spots; agreed with
    the Archipelago world, 2026-10-18): a name of all_place_names, never one of `places`, where
    the event's rule finds it (with Allow Triforces in Stairways, a cellar's Stairway name)."""
    places: tuple[PlaceInfo, ...]
    logic: LogicModel
    pool: tuple[str, ...]
    state: Built
    triforces: tuple[tuple[str, str], ...] = ()


def place_info(place: Place, names: Mapping[Item, str] = ITEM_NAMES) -> PlaceInfo:
    hearts = next((required.hearts for required in place.requires), None)
    return PlaceInfo(place.name, place.kind.value, tuple(sorted(names[item] for item in place.forbids)), hearts,
                     place.minor, place.compass_spot)


def seed_item_names(world: GameWorld) -> dict[Item, str]:
    """Each item's name in this seed: the seed format's, and a level's own piece, map and compass named by
    the number the status bar shows for it ("Level 3 Map"; docs/design/archipelago-items.md piece 6)."""
    return {**ITEM_NAMES, **level_item_names({level.level_num: level.rom_level_num for level in world.levels})}


def checked_rom(rom: bytes) -> bytes:
    """The player's ROM, refused unless it is a release ZORA knows (PRG0 or PRG1, with or without
    modified graphics; revision.identify_rom raises RomNotRecognized), and remembered for the
    client's reads of the game's own tables (base_rom). Generation reads only the ROM it is
    passed, so each player bakes from their own."""
    identify_rom(rom)
    remember_base_rom(rom)
    return rom


def build(values: Mapping[str, object], seed: int, rom: bytes,
          player_settings: Mapping[str, Any] | None = None) -> BuildResult:
    """BUILD from Archipelago's option values (flag_strings) and ZORA's seed number, which the
    Archipelago world draws from its own random generator, with the player's ROM (PRG0 or PRG1).
    `player_settings` (as finish() takes them): read here for the Graphics theme only, whose tiles go
    in before generation (graphics_theme.themed_player_rom); finish() must then be given the same."""
    return build_from_strings(*flag_strings(values), seed, rom, player_settings)


def graphics_theme_of(player_settings: Mapping[str, Any] | None) -> GraphicsTheme:
    """The Graphics theme player settings name (as finish() takes them); Off without any."""
    if not player_settings:
        return GraphicsTheme.OFF
    return player_settings_from_page(page_player_settings(player_settings)).graphics_theme


def without_minor_deal(chosen: GenerationPlan) -> GenerationPlan:
    """Shuffle Minor Dungeon Drops in Archipelago (2026-11-23): the filler spots trade filler with the multiworld and
    Archipelago does the shuffling, so ZORA's own B17 deal is skipped. Every Bomb, 5 Rupees and Key stays where the
    dungeon build put it, those rooms and cellars are the minor places (Place.minor, still listed: B17 stays on for
    the places and the pool), and no cave, shop ware or other overworld place holds one, so the world's filler items
    and filler spots match one for one. A single-player seed (ZORA mode) never comes here and still deals them."""
    return replace(chosen, alternatives=replace(chosen.alternatives, minor_drops_dealt=False))


def build_from_strings(flag_string: str, zora_flag_string: str, seed: int, rom: bytes,
                       player_settings: Mapping[str, Any] | None = None) -> BuildResult:
    """BUILD from ZORA's two flag strings and seed number, with the player's ROM, themed when the
    player settings name a Graphics theme (build)."""
    base = themed_player_rom(checked_rom(rom), graphics_theme_of(player_settings))
    built = build_seed(without_minor_deal(plan(flag_string, seed, zora_flag_string)), base)
    extras = extra_options(built.plan)
    names = seed_item_names(built.world)
    # With Add Triforces to the Item Pool the pieces are places and items, never events
    spots = () if extras.add_triforces_to_pool else triforce_spots(built.world)
    return BuildResult(places=tuple(place_info(place, names) for place in built.places), logic=logic_model(built),
                       pool=tuple(names[own_item(place, read_item(built.world, place), extras)]
                                  for place in built.places),
                       state=built, triforces=tuple((triforce_event(level), name) for level, name in spots))


def item_named(name: str, world: GameWorld | None = None) -> Item:
    """The item a name stands for; a level's piece, map or compass ("Level 3 Map") only with the seed's
    world, whose shown level numbers say which level it is."""
    if world is not None:
        by_name = {item_name: item for item, item_name in seed_item_names(world).items()}
        if name in by_name:
            return by_name[name]
    if name not in ITEMS_BY_NAME:
        raise UnknownItem(f"{name!r} is not an item name of the seed format")
    return ITEMS_BY_NAME[name]


# Owner rulings (beta 3): rupees, regular hearts, fairies, maps, compasses, regular Triforce
# pieces and the clock are never Archipelago items, and the Triforce of Power is the goal event,
# not an item. All but the clock are the items the game's TakeItem does not give through the
# inventory (the "complex" slots, RupeesToAdd and the refills: inventory.give refuses them); the
# clock it does give (InvClock), but it is a pickup's passing effect, not something to send.
# 5 Rupees is one since Shuffle Minor Dungeon Drops (B17) made its rooms places
# (docs/design/archipelago-items.md piece 3): given into RupeesToAdd, as the game's Take5Rupees does.
# Another player's item as this player's ROM holds it (finish.FOREIGN_ITEMS): never given to this player.
FOREIGN_ITEM_NAMES = frozenset(ITEM_NAMES[item] for item in FOREIGN_ITEMS.values())
NOT_RECEIVABLE = frozenset({"Rupee", "Heart", "Fairy", "Map", "Compass", "Triforce",
                            "Triforce of Power", "Clock", *FOREIGN_ITEM_NAMES})
# A level's own piece, map and compass, named by the number the status bar shows (Add Triforces / Maps/Compasses
# to the Item Pool; docs/design/archipelago-items.md piece 6): Archipelago items, given by their level's bit
RECEIVABLE_ITEMS = frozenset(name for name in ITEMS_BY_NAME if name not in NOT_RECEIVABLE) | set(ALL_LEVEL_ITEM_NAMES)


def receivable(name: str) -> bool:
    """Whether `name` is an Archipelago item: the one list the world builds its item table from
    and receive() gives. False for any name that is not the seed format's."""
    return name in RECEIVABLE_ITEMS


def assigned_items(assignment: Mapping[str, str | Foreign],
                   world: GameWorld | None = None) -> dict[str, Item | Foreign]:
    """Archipelago's assignment by name as FINISH takes it: item names become items (a level's own
    piece, map or compass by the seed's `world`), FOREIGN (another player's item) stays."""
    return {place: value if isinstance(value, Foreign) else item_named(value, world)
            for place, value in assignment.items()}


def received_items(received: Iterable[str], world: GameWorld | None = None) -> list[Item]:
    return [item_named(name, world) for name in received]


def finish(result: BuildResult, assignment: Mapping[str, str | Foreign], received: Iterable[str] = (),
           player_settings: Mapping[str, Any] | None = None, ap_name: bytes | None = None,
           foreign_owners: Mapping[str, tuple[str, str]] | None = None) -> bytes:
    """FINISH: the ROM with Archipelago's items in their places. `received`: this player's items
    that other worlds hold, which the sanity check grants (R4). `player_settings`: the page's
    names (selectButton, greenTunic, ...) or the YAML keys (page_player_settings). `ap_name`: the
    slot name the client logs in with (1 to 23 bytes, no zero byte; rom_identity reads it back),
    written into the ROM, so each slot's seed code differs. Raises AssignmentRefused (a place's
    rule broken), AssignmentUnbeatable (the sanity check) or SlotNameRefused, never a ROM that
    ZORA's walk rejects."""
    record = b"" if ap_name is None else slot_identity.slot_identity_record(ap_name, FORMAT_VERSION_NUMBERS)
    settings = player_settings or {}
    return finish_seed(result.state, result.state.base_rom, assigned_items(assignment, result.state.world),
                       player_settings_from_page(page_player_settings(settings)),
                       received=received_items(received, result.state.world), check=True, slot_identity=record,
                       foreign_owners=dict(foreign_owners or {}))


# --- the slot identity (Phase 4c) ------------------------------------------------------------------

RomIdentity = slot_identity.SlotIdentity
SlotNameRefused = slot_identity.SlotNameRefused


def rom_identity(rom: bytes) -> RomIdentity | None:
    """The slot identity a finished .nes file holds (the recipe format version that wrote it and
    the slot name), or None for a ROM without one (ZORA mode, or no ap_name given)."""
    return slot_identity.read_slot_identity(rom)


# --- the recipe (spec "Design" 4) -----------------------------------------------------------------

RECIPE_FORMAT = "zora-ap-recipe"
# 1.1 (Phase 4c): apName; 1.2: foreignItemLook in playerSettings; 1.3: another player's item's class
RECIPE_FORMAT_VERSION = "1.3"
FORMAT_VERSION_NUMBERS = (1, 3)           # the same, as the slot identity's two bytes
FOREIGN_JSON = {"foreign": True}          # owner decision 4: no player or item names; 1.3 adds "class"
HASH_PREFIX = "sha256:"


def _package_files(folder: Traversable, prefix: str = "") -> Iterator[tuple[str, Traversable]]:
    """Every file of the package below `folder`, by its path inside the package, in a fixed
    order; caches and hidden files (a folder's .DS_Store) are not part of it."""
    for entry in sorted(folder.iterdir(), key=lambda entry: entry.name):
        if entry.name.startswith(".") or entry.name == "__pycache__" or entry.name.endswith(".pyc"):
            continue
        path = f"{prefix}{entry.name}"
        if entry.is_dir():
            yield from _package_files(entry, f"{path}/")
        else:
            yield path, entry


def source_hash() -> str:
    """sha256 over this copy of the zora package: each file's path inside it and its bytes, in
    path order, read through importlib.resources, so a folder and a zip (the .apworld) give the
    same hash. A recipe is rebuilt only by a copy with the same hash: output may change between
    builds without a version bump (zora/version.py), so the hash, not the version, is the pin."""
    digest = hashlib.sha256()
    for path, entry in _package_files(files(__package__)):
        data = entry.read_bytes()
        for part in (path.encode(), len(data).to_bytes(8, "big"), data):
            digest.update(part)
    return HASH_PREFIX + digest.hexdigest()


def foreign_json(value: Foreign) -> dict[str, Any]:
    """Another player's item in the recipe: {"foreign": true, "class": ...} (format 1.3)."""
    return {**FOREIGN_JSON, "class": value.item_class.value}


def _assignment_json(assignment: Mapping[str, str | Foreign]) -> dict[str, Any]:
    return {place: foreign_json(value) if isinstance(value, Foreign) else value for place, value in assignment.items()}


def recipe(result: BuildResult, assignment: Mapping[str, str | Foreign], received: Iterable[str] = (),
           player_settings: Mapping[str, Any] | None = None, ap_name: bytes | None = None,
           foreign_owners: Mapping[str, tuple[str, str]] | None = None) -> dict[str, Any]:
    """The recipe a player's machine rebuilds this ROM from with its own ROM (PRG0 or PRG1)
    (rom_from_recipe): plain JSON data, no ROM bytes. The producer and seed blocks are the seed
    document's (docs/seed-format/), with this copy's source hash; items by the seed format's
    names; another player's item as {"foreign": true, "class": ...}; the slot name as hex (apName, null
    without one). Unknown names and slot names the ROM cannot hold are refused here, at
    generation, never on the player's machine."""
    assigned_items(assignment, result.state.world)
    received_items(received, result.state.world)
    if ap_name is not None:
        slot_identity.slot_identity_record(ap_name, FORMAT_VERSION_NUMBERS)
    chosen = result.state.plan
    hinted = hinted_foreign_places(result.state.places, assignment, dict(foreign_owners or {}))
    return {
        "format": RECIPE_FORMAT,
        "formatVersion": RECIPE_FORMAT_VERSION,
        "producer": {"name": PLAYER_NAME, "version": ZORA_VERSION, "sourceHash": source_hash()},
        "seed": {"number": str(chosen.seed), "flags": chosen.flag_string, "zoraFlags": chosen.zora_flag_string},
        "playerSettings": page_player_settings(player_settings or {}),
        "assignment": _assignment_json(assignment),
        # optional (approved by Tetra, the project owner, 2026-11-18, at Gob's request; this departs from
        # docs/archipelago.md decision 4, "no player or item names"): the owner and item name of each other
        # player's place a hint can name (finish.hinted_foreign_places), for the hint text only; a recipe
        # without it rebuilds the generic hint wording
        "foreignOwners": {place: list(owned) for place, owned in (foreign_owners or {}).items()
                          if place in hinted},
        "received": list(received),
        "apName": None if ap_name is None else ap_name.hex(),
        # optional (piece 8): the seed's bomb upgrade count, drawn mid-generation, so recipe_give_rules needs it
        "bombUpgradeCount": result.state.world.overworld.bomb_upgrade.count,
    }


class RecipeRefused(ValueError):
    """A recipe this copy of ZORA does not rebuild: another format, or another ZORA (version or
    source hash), named with this copy's."""


class RecipeNotReproduced(RuntimeError):
    """The rebuilt seed failed the sanity check generation passed: a determinism bug (the same
    copy of ZORA, recipe and ROM must give the same seed), never the player's fault."""


def _recipe_value(value: Any) -> str | Foreign:
    """A recipe's assigned value: an item name, or another player's item with its class."""
    if isinstance(value, str):
        return value
    if not isinstance(value, Mapping):
        raise RecipeRefused(f"not an assigned item: {value!r}")
    if value.get("foreign") is not True or set(value) != {"foreign", "class"}:
        raise RecipeRefused(f"not an assigned item: {value!r}")
    try:
        return Foreign(ItemClass(value["class"]))
    except ValueError:
        raise RecipeRefused(f"not an item class: {value['class']!r}") from None


def _recipe_assignment(data: Mapping[str, Any]) -> dict[str, str | Foreign]:
    return {place: _recipe_value(value) for place, value in data.items()}


def check_recipe(data: Mapping[str, Any]) -> None:
    """RecipeRefused unless this copy of ZORA made the recipe's kind of seed."""
    if (data.get("format"), data.get("formatVersion")) != (RECIPE_FORMAT, RECIPE_FORMAT_VERSION):
        raise RecipeRefused(f"not a {RECIPE_FORMAT} {RECIPE_FORMAT_VERSION} recipe: "
                            f"{data.get('format')!r} {data.get('formatVersion')!r}")
    producer = data.get("producer", {})
    made_by = (producer.get("version"), producer.get("sourceHash"))
    running = (ZORA_VERSION, source_hash())
    if made_by != running:
        raise RecipeRefused(f"this recipe was made by ZORA {made_by[0]} ({made_by[1]}), but this is "
                            f"ZORA {running[0]} ({running[1]}): rebuild it with the .apworld that generated it")


def rom_from_recipe(data: Mapping[str, Any], rom: bytes) -> bytes:
    """The ROM a recipe names, made from the player's own ROM (PRG0 or PRG1): BUILD and FINISH as at
    generation, with the same sanity check (RecipeNotReproduced if it now fails)."""
    check_recipe(data)
    seed = data["seed"]
    result = build_from_strings(seed["flags"], seed["zoraFlags"], int(seed["number"]), rom, data["playerSettings"])
    try:
        ap_name = None if data["apName"] is None else bytes.fromhex(data["apName"])
        return finish(result, _recipe_assignment(data["assignment"]), data["received"], data["playerSettings"],
                      ap_name, foreign_owners={place: tuple(owned) for place, owned
                                               in data.get("foreignOwners", {}).items()})
    except (AssignmentRefused, AssignmentUnbeatable) as failure:
        raise RecipeNotReproduced(f"the rebuilt seed fails where generation passed ({failure}): a determinism "
                                  f"bug in ZORA {ZORA_VERSION}; please report it with the recipe") from failure



# --- the client's tables (spec "Design" 5) ----------------------------------------------------------

@dataclass(frozen=True)
class RamCheck:
    """A place's item is taken once `ram[address] & mask` is nonzero."""
    address: int
    mask: int

    def is_set(self, ram: Mapping[int, int]) -> bool:
        return bool(ram[self.address] & self.mask)


def pickup_check(place: Place, mirrored: bool = False) -> RamCheck:
    """Where the game records that the place's item was taken: a room's or cellar's item bit in
    its level's room flags, a cave's (and the Armos and coast items') in its overworld screen's,
    and a ware place's ShopBoughtFlags bit (External mode sells every ware place once). On a
    `mirrored` seed (Mirror Overworld, B06) the game is played on the flipped overworld, so a
    screen's flags are those of its mirrored screen (OW-MIR-02: s XOR $0F), while the place,
    read from the built world, names the screen before the flip (pipeline.written_world)."""
    if place.kind in (PlaceKind.ROOM, PlaceKind.CELLAR):
        assert place.level is not None and place.room_num is not None
        return RamCheck(inventory.room_flags(place.level) + place.room_num, inventory.ITEM_TAKEN)
    if place.is_shop:
        assert place.destination is not None and place.position is not None
        return RamCheck(inventory.SHOP_BOUGHT_FLAGS + place.position, 1 << SHOPS_BY_NUMBER.index(place.destination))
    screen = place.screens[0] if place.screens else inventory.COAST_SCREEN
    if mirrored:
        screen = mirror_screen(screen)
    return RamCheck(inventory.room_flags(0) + screen, inventory.ITEM_TAKEN)


def pickup_checks(result: BuildResult) -> dict[str, RamCheck]:
    """Each place's RamCheck, by place name: the client reports a place collected when its check
    is set (only during normal play: docs/archipelago.md "Interface", when to read and write)."""
    mirrored = result.state.plan.config.mirror_overworld
    return {place.name: pickup_check(place, mirrored) for place in result.state.places}


def _give_rules(chosen: GenerationPlan) -> inventory.GiveRules:
    return inventory.GiveRules(progressive_items=chosen.zora.progressive_items,
                               l4_sword=chosen.zora_resolved.is_on("add_l4_sword"),
                               four_potions=chosen.zora_resolved.is_on("four_potion_inventory"),
                               pegasus_boots=chosen.zora_resolved.is_on("pegasus_boots"))


def give_rules(result: BuildResult) -> inventory.GiveRules:
    """The flags that change how this seed gives an item (receive), as resolved for it, and its bomb upgrade's
    count."""
    return replace(_give_rules(result.state.plan), bomb_upgrade_count=result.state.world.overworld.bomb_upgrade.count)


def recipe_give_rules(data: Mapping[str, Any]) -> inventory.GiveRules:
    """give_rules for a recipe's seed: its flags resolve as at generation, and no ROM is needed."""
    seed = data["seed"]
    return replace(_give_rules(plan(seed["flags"], int(seed["number"]), seed["zoraFlags"])),
                   bomb_upgrade_count=int(data.get("bombUpgradeCount", inventory.VANILLA_BOMB_UPGRADE_COUNT)))


NO_RULES = inventory.GiveRules()


class ClientNotReady(NoPlayerRom):
    """receive() called in a process that has no player ROM: client_ready(rom) comes first."""


def client_ready(rom: bytes) -> None:
    """Make this process ready to receive items: `rom` is the player's ROM (the one
    Archipelago's settings name, not the finished .nes), refused as by build (RomNotRecognized)
    and remembered, since receive reads the game's own item tables from it. A client calls it
    once, before its first receive(), whenever it starts on its own or restarts mid-game; a
    process that built or finished a seed (build, rom_from_recipe) has remembered it already."""
    checked_rom(rom)


# A level's own piece, map or compass as the client gives it (docs/design/archipelago-items.md piece 6): the
# level's bit in its inventory byte, levels 1-8 one bit each (bit n-1), level 9's map and compass bytes of
# their own (bit 0)
LEVEL_ITEM_NAME = re.compile(r"Level ([1-9]) (Triforce|Map|Compass)")
LEVEL_ITEM_SLOTS = {LevelItemKind.COMPASS: 0x10, LevelItemKind.MAP: 0x11, LevelItemKind.TRIFORCE: 0x1A}
LEVEL_9_ITEM_SLOTS = {LevelItemKind.COMPASS: 0x12, LevelItemKind.MAP: 0x13}
LEVEL_9_BIT = 0x01


def give_level_item(name: str, ram: Mapping[int, int], level_numbers: Mapping[int, int]) -> dict[int, int]:
    """The RAM write that gives "Level N Map" (and the like): N is the number the status bar shows, which
    `level_numbers` (data level -> shown, ClientTables.level_numbers) turns back into the data level whose
    bit it is; without them N is the data level."""
    found = LEVEL_ITEM_NAME.fullmatch(name)
    assert found is not None, name
    shown, kind = int(found[1]), LevelItemKind(found[2])
    level = next((data for data, number in level_numbers.items() if number == shown), shown)
    if level == LEVEL_9:
        address, mask = inventory.ITEMS + LEVEL_9_ITEM_SLOTS[kind], LEVEL_9_BIT
    else:
        address, mask = inventory.ITEMS + LEVEL_ITEM_SLOTS[kind], 1 << (level - 1)
    return {address: ram[address] | mask}


def receive(item: str, ram: Mapping[int, int], rules: inventory.GiveRules = NO_RULES,
            level_numbers: Mapping[int, int] | None = None) -> dict[int, int]:
    """The RAM writes that give a received item as the game gives a picked-up one (address ->
    value; `ram` holds at least the inventory and RupeesToAdd, $0657-$067D): a line item at its
    next level with Progressive Items (Add L4 Sword: a sword at level 3 gives 4), else the higher
    of the two grades; a heart container one more container and one more heart; an amount added
    within its cap; five rupees added to RupeesToAdd. Another player's item is never received.
    Call it only during normal play, and only after client_ready(rom) (or a build in this
    process): ClientNotReady otherwise. UnknownItem for a name that is no item, NotReceivable for
    one that is never an Archipelago item."""
    if item in ALL_LEVEL_ITEM_NAMES:
        return give_level_item(item, ram, level_numbers or {})
    given = item_named(item)
    if not receivable(item):
        raise NotReceivable(f"{item!r} is never an Archipelago item")
    if given == Item.BOMB_UPGRADE:
        return inventory.give_bomb_upgrade(ram, rules.bomb_upgrade_count)
    try:
        return inventory.give(given, ram, rules)
    except NoPlayerRom as missing:
        raise ClientNotReady("receive() needs the player's ROM: call "
                             "archipelago.client_ready(rom) once before the first receive()") from missing


def may_receive(ram: Mapping[int, int]) -> bool:
    """Whether the client may write a received item now: in normal play or in a cellar (since 2026-11-23), never
    during a transition, a cave, the item screen, a pause, an item being lifted or text (`ram` holds
    inventory.RECEIVE_STATE's addresses). Pickup checks may be read at any time in play."""
    return inventory.may_receive(ram)



# --- the received count and the goal (Phase 4c) ------------------------------------------------------

RECEIVE_STATE = inventory.RECEIVE_STATE
# The saved count of items the client has given (Items+$24, saved with the file, 0 in a new file):
# when may_receive, give item number `count` with receive and write count + 1 in the same writes.
RECEIVED_COUNT = inventory.RECEIVED_COUNT
GOAL_STATE = inventory.GOAL_STATE


def goal_reached(ram: Mapping[int, int]) -> bool:
    """Whether the player has won: Zelda rescued (`ram` holds GOAL_STATE's addresses). True from
    the frame Link reaches Zelda through the ending (mode $13); never before, and false again
    once the game leaves the ending, so the client reports the goal the first time it sees it."""
    return inventory.goal_reached(ram)


# --- when the pickup checks hold the loaded file ------------------------------------------------------

CHECKS_STATE = inventory.CHECKS_STATE


def checks_readable(ram: Mapping[int, int]) -> bool:
    """Whether the pickup flags (pickup_checks) hold the loaded save file (`ram` holds
    CHECKS_STATE's addresses): true from the frame a chosen file's flags are loaded (mode 2) until
    the game leaves it (a reset's RAM clear, a save, or the title and file-select screens), and
    never before the reset code has run since power-on, while RAM holds whatever it powered on
    with. A pickup check read while this is false means nothing: the flags may be garbage, zero, or
    another file's. may_receive is true only in play, which this also covers once the game has
    started; a client asks both before it writes (docs/archipelago.md "Interface")."""
    return inventory.checks_readable(ram)


# --- client_step: the client's decisions as one pure function (beta 3) ------------------------------
# docs/design/archipelago-client-step.md, with the Archipelago planning session's review: the
# world's client reads the bytes the tables list, calls client_step and does what the Decision says;
# every rule about what to report, write or send lives here. docs/archipelago.md "client_step".

CLIENT_TABLES_FORMAT = "zora-ap-client-tables"
CLIENT_TABLES_VERSION = 2                 # 2: rules.arrivalSound (item_arrival_sound)
MAX_READ_LENGTH = 252                     # bytes per read: a console bridge's read limit
# DeathLink (docs/design/archipelago-items.md piece 2; docs/reports/research-ap-item-codes-and-deathlink.md
# section 2): client-only. The game decides a death only in Link_BeHarmed's @HandleDied, which goes to
# mode $11; the client sends a death the first time it sees $11, and applies a received one by
# writing @HandleDied's stores, guarded as a received item is, plus the states below at 0.
CUR_LEVEL = 0x10                          # CurLevel: 0 on the overworld, else the level loaded (Level.level_num)
DEATH_MODE = 0x11                         # GameMode while Link dies (InitMode11 and its submodes)
CONTINUE_MODE = 0x08                      # Continue, Save, Retry, after the death
FLUTE_TIMER = 0x3C
FILLING_HEARTS = 0x63                     # World_IsFillingHearts
TRIFORCE_FANFARE_ACTIVE = 0x0509
BRIGHTENING_ROOM = 0x051E
WHIRLWIND_TELEPORTING = 0x0522            # WhirlwindTeleportingState
DEATH_STATE = (FLUTE_TIMER, FILLING_HEARTS, TRIFORCE_FANFARE_ACTIVE, BRIGHTENING_ROOM, WHIRLWIND_TELEPORTING)
HEART_VALUES = inventory.ITEMS + inventory.HEART_VALUES_SLOT    # $066F: containers - 1, hearts
HEART_PARTIAL = HEART_VALUES + 1          # $0670
LINK_DIR = 0x98                           # ObjDir, slot 0 (Link)
FACING_DOWN = 0x04
CONTAINERS_MASK = 0xF0
# The state bytes every predicate here reads (checks_readable, may_receive, goal_reached, DeathLink's
# guards and CurLevel): one scattered read, made first and again last (the bracket).
# Tune1Request, which the arrival sound's write is guarded on, and CurPpuControl, which every write is
# guarded on (inventory.frame_finished), among them.
STATE_ADDRESSES = tuple(sorted({*CHECKS_STATE, *RECEIVE_STATE, *GOAL_STATE, inventory.TUNE1_REQUEST, CUR_LEVEL,
                                *DEATH_STATE, inventory.CUR_PPU_CONTROL}))
# The inventory ($0657-$067E, with the received count and ShopBoughtFlags) and the world flags
# ($067F-$07FE, every pickup check), as (first address, length) reads of MAX_READ_LENGTH or less.
_BLOCK_START, _BLOCK_END = inventory.ITEMS, inventory.WORLD_FLAGS + 3 * inventory.WORLD_FLAGS_SIZE
READ_RANGES = tuple((start, min(MAX_READ_LENGTH, _BLOCK_END - start))
                    for start in range(_BLOCK_START, _BLOCK_END, MAX_READ_LENGTH))

NO_LEVEL_NUMBERS: Mapping[int, int] = MappingProxyType({})
Guard = tuple[int, int]                   # (address, the value the write expects there)
Write = tuple[int, int]                   # (address, value)


@dataclass(frozen=True)
class ClientTables:
    """What client_step needs of a seed, made once: each place's pickup check (by place name,
    pickup_checks), the seed's give rules (give_rules), the arrival sound, and the reads a client makes each poll:
    `state_addresses` first, then each of `ranges` ((first address, length), each at most
    MAX_READ_LENGTH bytes), then `state_addresses` again."""
    checks: Mapping[str, RamCheck]
    rules: inventory.GiveRules
    # The player's item_arrival_sound: the Tune1Request value a give plays, 0 for none.
    arrival_sound: int = inventory.ITEM_APPEARS_SOUND
    # CurLevel -> the level number the status bar shows (Level.rom_level_num), for a death's cause
    # text; empty from tables that predate it, which then name no level.
    # (A factory: Python 3.11's dataclasses refuse an unhashable default such as a mappingproxy.)
    level_numbers: Mapping[int, int] = dataclass_field(default_factory=lambda: NO_LEVEL_NUMBERS)
    state_addresses: tuple[int, ...] = STATE_ADDRESSES
    ranges: tuple[tuple[int, int], ...] = READ_RANGES

    def addresses(self) -> tuple[int, ...]:
        """Every byte client_step reads, sorted."""
        return tuple(sorted({*self.state_addresses,
                             *(address for start, length in self.ranges for address in range(start, start + length))}))


class ClientTablesRefused(ValueError):
    """Client tables in JSON that this copy of ZORA does not read (another format or version, or
    a malformed entry)."""


def arrival_sound(player_settings: Mapping[str, Any] | None) -> int:
    """The Tune1Request value item_arrival_sound names (0 for none), from player settings as
    finish() takes them."""
    return ARRIVAL_SOUNDS[multiworld_setting(player_settings or {}, PAGE_ITEM_ARRIVAL_SOUND)]


def client_tables_of(result: BuildResult, player_settings: Mapping[str, Any] | None = None) -> ClientTables:
    """A built seed's client tables, with the player's arrival sound."""
    return ClientTables(pickup_checks(result), give_rules(result), arrival_sound(player_settings),
                        level_numbers(result))


def level_numbers(result: BuildResult) -> dict[int, int]:
    """Each level's CurLevel (Level.level_num) -> the number the status bar shows (rom_level_num)."""
    return {level.level_num: level.rom_level_num for level in result.state.world.levels}


def client_tables(recipe_data: Mapping[str, Any]) -> ClientTables:
    """A recipe's client tables (ZORA's tests): its seed rebuilt with the player ROM this process
    remembered (client_ready, or a build)."""
    check_recipe(recipe_data)
    seed = recipe_data["seed"]
    return client_tables_of(build_from_strings(seed["flags"], seed["zoraFlags"], int(seed["number"]), player_rom()),
                            recipe_data["playerSettings"])


def client_tables_to_json(result: BuildResult, player_settings: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """The client tables as plain JSON for Archipelago's slot data: small and versioned. Each
    check as [place name, address, mask]; the give rules by name, with the arrival sound the
    player settings (as finish() takes them; the defaults without) name, 0 for none. The reads are
    ZORA's constants (client_tables_from_json restores them)."""
    rules = give_rules(result)
    return {
        "format": CLIENT_TABLES_FORMAT,
        "version": CLIENT_TABLES_VERSION,
        "checks": [[name, check.address, check.mask] for name, check in pickup_checks(result).items()],
        "rules": {"progressiveItems": rules.progressive_items, "l4Sword": rules.l4_sword,
                  "fourPotions": rules.four_potions, "pegasusBoots": rules.pegasus_boots,
                  "bombUpgradeCount": rules.bomb_upgrade_count, "arrivalSound": arrival_sound(player_settings)},
        "levelNumbers": [[level, shown] for level, shown in sorted(level_numbers(result).items())],
    }


def client_tables_from_json(data: Mapping[str, Any]) -> ClientTables:
    """ClientTables from client_tables_to_json's form; ClientTablesRefused for another format or
    version, or a malformed entry."""
    if (data.get("format"), data.get("version")) != (CLIENT_TABLES_FORMAT, CLIENT_TABLES_VERSION):
        raise ClientTablesRefused(f"not {CLIENT_TABLES_FORMAT} version {CLIENT_TABLES_VERSION}: "
                                  f"{data.get('format')!r} {data.get('version')!r}")
    try:
        checks = {str(name): RamCheck(int(address), int(mask)) for name, address, mask in data["checks"]}
        rules = data["rules"]
        give = inventory.GiveRules(progressive_items=bool(rules["progressiveItems"]), l4_sword=bool(rules["l4Sword"]),
                                   four_potions=bool(rules["fourPotions"]),
                                   pegasus_boots=bool(rules.get("pegasusBoots", False)),  # names only, optional
                                   bomb_upgrade_count=int(rules.get("bombUpgradeCount",            # optional (piece 8)
                                                                    inventory.VANILLA_BOMB_UPGRADE_COUNT)))
        sound = int(rules["arrivalSound"])
        shown = {int(level): int(number) for level, number in data.get("levelNumbers", [])}     # optional
    except (KeyError, TypeError, ValueError) as malformed:
        raise ClientTablesRefused(f"malformed client tables: {malformed}") from malformed
    if sound not in ARRIVAL_SOUNDS.values():
        raise ClientTablesRefused(f"malformed client tables: arrivalSound {sound!r}")
    return ClientTables(checks, give, sound, shown)


@dataclass(frozen=True)
class ReceivedItem:
    """One entry of the server's received-items list for this slot, in its order: ZORA's item
    name (item_named takes it) and, only when the finding player is this slot, the place it was
    found at, by place name (None for another world's item or a server-given one)."""
    name: str
    location: str | None = None


@dataclass(frozen=True)
class ServerView:
    """What the server has said, as of this poll: every item received for this slot in its order,
    this slot's places it holds as checked, and whether it already has this slot's goal."""
    received: tuple[ReceivedItem, ...] = ()
    checked: frozenset[str] = frozenset()
    goal_known: bool = False


@dataclass(frozen=True)
class ClientMemory:
    """What the client carries from one poll to the next (start with ClientMemory()); all of it
    may be lost safely. reported: places sent and not yet in the server's checked set;
    awaiting_count: the received count the last writes set, until RAM shows it; goal_sent: the
    goal was sent at least once. DeathLink: dead_latched, the client has seen the death it is in
    (mode $11, then the Continue screen), so it is sent once; death_applied, that death is one
    this client wrote, never sent back; pending_death, a received death not yet applied
    (death_received sets it)."""
    reported: frozenset[str] = frozenset()
    awaiting_count: int | None = None
    goal_sent: bool = False
    dead_latched: bool = False
    death_applied: bool = False
    pending_death: bool = False


NO_MEMORY = ClientMemory()                # what a client starts with (or restarts mid-game with)


@dataclass(frozen=True)
class Decision:
    """client_step's answer for one poll. readable: the snapshot held the loaded file; report:
    places to send now (LocationChecks); writes and guards: RAM writes to make, in order, with
    Archipelago's guarded_write(writes, guards), never a plain write (at most 3 writes and 13
    guards of one byte each); gives / skips / cannot_give: the received item the writes give, or
    count without giving (already held), or count without giving because it is no item ZORA gives
    (receivable() is False, or no item name at all); goal: send the goal now; send_death: send a
    DeathLink death now, its cause text from death_cause(player, death_level), death_level the
    number the status bar shows or None outside a level; applies_death: the writes apply a
    received death (seven writes, so a console bridge with a smaller buffer needs a ROM mailbox
    instead); memory: for the next poll, kept only when the guarded write succeeded or there was
    nothing to write."""
    readable: bool
    report: tuple[str, ...] = ()
    writes: tuple[Write, ...] = ()
    guards: tuple[Guard, ...] = ()
    gives: str | None = None
    skips: str | None = None
    cannot_give: str | None = None
    goal: bool = False
    send_death: bool = False
    death_level: int | None = None
    applies_death: bool = False
    memory: ClientMemory = NO_MEMORY


class _RecordedReads(Mapping[int, int]):
    """A RAM mapping that remembers which addresses were read (receive's guards)."""

    def __init__(self, ram: Mapping[int, int]) -> None:
        self.ram = ram
        self.read: dict[int, int] = {}

    def __getitem__(self, address: int) -> int:
        self.read[address] = self.ram[address]
        return self.read[address]

    def __iter__(self) -> Iterator[int]:
        return iter(self.ram)

    def __len__(self) -> int:
        return len(self.ram)


def _bracket_holds(ram: Mapping[int, int], ram_after: Mapping[int, int]) -> bool:
    """Both reads of the state bytes hold the loaded file, the same save slot and game mode: the
    snapshot between them is one file's, in one mode."""
    return (checks_readable(ram) and checks_readable(ram_after)
            and ram[inventory.CUR_SAVE_SLOT] == ram_after[inventory.CUR_SAVE_SLOT]
            and ram[inventory.GAME_MODE] == ram_after[inventory.GAME_MODE])


def client_step(ram: Mapping[int, int], ram_after: Mapping[int, int], server: ServerView, tables: ClientTables,
                memory: ClientMemory = NO_MEMORY) -> Decision:
    """The client's decisions for one poll, pure: `ram` holds the bytes of tables.addresses() as
    read this poll (the state bytes first, then the ranges), `ram_after` the state bytes read
    again last. In order:
      1. Unless both reads hold the loaded file with the same save slot and game mode, nothing:
         no report, writes or goal (memory kept, but for the awaited count, dropped).
      2. Each place whose pickup check is set and that is neither checked by the server nor
         reported and awaiting it, in tables.checks' order.
      3. The goal while goal_reached in both reads and the server does not know it.
      4. While may_receive in both reads, the server's next item, one per poll: number `count`
         (RECEIVED_COUNT) of server.received. If it is no item ZORA gives (receivable() is
         False), only the count goes up (cannot_give): the client moves on, never raising for a
         received item. If it was found at one of this slot's places whose pickup check is set in
         the loaded file, the game gave it already: only the count goes up (skips). Else
         receive's writes, then the arrival sound (tables.arrival_sound into Tune1Request, unless
         none, and only while Tune1Request reads 0: a pending sound wins, and the item comes
         without one), then the count (gives). Nothing while the count the last writes set is not
         yet in RAM (one poll).
    Writes only while the game's frame had finished in `ram_after` (inventory.frame_finished), each
    guarded on CurPpuControl as read there: a write on a frame that lags would land in the middle of
    the game's update, which may store over it (2.0.2).
    DeathLink (piece 2), around those steps:
      - With no file in play (the title, file-select and save screens, or before the reset code
        has run), a received death is dropped and the death latch cleared. A read that fails the
        bracket with a file in play (a transition) drops nothing.
      - The first poll in mode $11 sends a death (send_death, with the level the status bar
        shows) unless this client applied it. The latch holds through the Continue screen; any
        other mode clears it. A death received while Link is dying or on the Continue screen is
        dropped: he is dead already.
      - A received death is applied before any item, while may_apply_death holds in both reads:
        @HandleDied's stores (applies_death), guarded on RECEIVE_STATE, DEATH_STATE at 0,
        GOAL_STATE and HeartValues. Several received before it is applied make one death.
    The writes depend on the guards' bytes only: RECEIVE_STATE (as `ram_after` holds it), the
    count, the inventory bytes receive read or writes (or the pickup flag, for a skip),
    Tune1Request's 0 for a sound, and CurPpuControl with its NMI bit set."""
    if not _bracket_holds(ram, ram_after):
        if not checks_readable(ram_after):
            memory = replace(memory, pending_death=False, dead_latched=False, death_applied=False)
        return Decision(readable=False, memory=replace(memory, awaiting_count=None))
    reported = memory.reported - server.checked
    report = tuple(name for name, check in tables.checks.items()
                   if check.is_set(ram) and name not in server.checked and name not in reported)
    goal = goal_reached(ram) and goal_reached(ram_after) and not server.goal_known
    mode = ram_after[inventory.GAME_MODE]
    dying = mode in (DEATH_MODE, CONTINUE_MODE)
    send_death = mode == DEATH_MODE and not memory.dead_latched and not memory.death_applied
    next_memory = replace(memory, reported=reported | frozenset(report), goal_sent=memory.goal_sent or goal,
                          dead_latched=memory.dead_latched or mode == DEATH_MODE if dying else False,
                          death_applied=memory.death_applied if dying else False,
                          pending_death=memory.pending_death and not dying)
    decision = Decision(readable=True, report=report, goal=goal, memory=next_memory, send_death=send_death,
                        death_level=tables.level_numbers.get(ram_after[CUR_LEVEL]) if send_death else None)
    if not inventory.frame_finished(ram_after):
        return decision                 # the update was still running: any write waits for a poll that sees it done
    frame = {inventory.CUR_PPU_CONTROL: ram_after[inventory.CUR_PPU_CONTROL]}
    if next_memory.pending_death and may_apply_death(ram) and may_apply_death(ram_after):
        guards = {address: ram_after[address] for address in (*RECEIVE_STATE, *DEATH_STATE, *GOAL_STATE)}
        guards[HEART_VALUES] = ram[HEART_VALUES]
        guards |= frame
        return replace(decision, writes=death_writes(ram), guards=tuple(sorted(guards.items())), applies_death=True,
                       memory=replace(next_memory, pending_death=False, death_applied=True))
    if not (may_receive(ram) and may_receive(ram_after)):
        return decision
    count = ram[RECEIVED_COUNT]
    if memory.awaiting_count is not None and memory.awaiting_count != count:
        return replace(decision, memory=replace(next_memory, awaiting_count=None))   # wait one poll
    if count >= len(server.received):
        return replace(decision, memory=replace(next_memory, awaiting_count=None))
    item = server.received[count]
    guards = {address: ram_after[address] for address in RECEIVE_STATE}
    guards[RECEIVED_COUNT] = count
    guards |= frame
    check = tables.checks.get(item.location) if item.location is not None else None
    if not receivable(item.name):
        writes: tuple[Write, ...] = ((RECEIVED_COUNT, count + 1),)
        gives, skips, cannot_give = None, None, item.name
    elif check is not None and check.is_set(ram):
        guards[check.address] = ram[check.address]
        writes = ((RECEIVED_COUNT, count + 1),)
        gives, skips, cannot_give = None, item.name, None
    else:
        recorded = _RecordedReads(ram)
        given = receive(item.name, recorded, tables.rules, tables.level_numbers)
        guards |= recorded.read
        sound: tuple[Write, ...] = ()
        if tables.arrival_sound and ram_after[inventory.TUNE1_REQUEST] == 0:
            guards[inventory.TUNE1_REQUEST] = 0
            sound = ((inventory.TUNE1_REQUEST, tables.arrival_sound),)
        writes = (*sorted(given.items()), *sound, (RECEIVED_COUNT, count + 1))
        gives, skips, cannot_give = item.name, None, None
    return replace(decision, writes=writes, guards=tuple(sorted(guards.items())), gives=gives, skips=skips,
                   cannot_give=cannot_give, memory=replace(next_memory, awaiting_count=count + 1))


def may_apply_death(ram: Mapping[int, int]) -> bool:
    """Whether a received death may be written now (`ram` holds the state bytes): in normal play
    (inventory.in_normal_play: never a transition, cave, cellar, pause, text or a lifted item), with the
    recorder, a whirlwind, the Triforce fanfare, a heart refill and a room brightening all over,
    and never once Zelda is rescued."""
    return (inventory.in_normal_play(ram) and all(ram[address] == 0 for address in DEATH_STATE)
            and not goal_reached(ram))


def death_writes(ram: Mapping[int, int]) -> tuple[Write, ...]:
    """@HandleDied's stores (Z_01.asm), in its order: the hearts emptied, EndGameMode
    (IsUpdatingMode and GameSubmode), the partial heart, Link's state, mode $11, Link facing down.
    InitMode11 then runs as for any death, and the death counter rises."""
    return ((HEART_VALUES, ram[HEART_VALUES] & CONTAINERS_MASK), (inventory.IS_UPDATING_MODE, 0),
            (inventory.GAME_SUBMODE, 0), (HEART_PARTIAL, 0), (inventory.LINK_STATE, 0),
            (inventory.GAME_MODE, DEATH_MODE), (LINK_DIR, FACING_DOWN))


def death_received(memory: ClientMemory) -> ClientMemory:
    """The memory after a DeathLink death arrives: one pending death (several make one), which
    client_step applies or drops."""
    return replace(memory, pending_death=True)


def death_cause(player: str, level: int | None) -> str:
    """The cause text a sent death carries: "<player> ran out of hearts in Level 4." in a level,
    without the level elsewhere."""
    where = f" in Level {level}" if level else ""
    return f"{player} ran out of hearts{where}."



# --- HUD messages: what the client writes into the game's tile buffer (2.0.2) ------------------------------
# A line goes in the blank top row of the status bar (nametable $2022, 28 columns) as one record in
# DynTileBuf ($0302, with DynTileBufLen $0301 the index of its $FF end), which the NMI sends to the PPU and
# then empties. archipelago/client.py hud_write reads CurPpuControl, then tries hud_guard_sets' guards in
# order, each with hud_writes, through guarded_write.
HUD_ROW = 0x2022
HUD_WIDTH = 28
# The status bar's text (FormatStatusBarText), which the game queues every second frame alone in the buffer:
# its first record is the blank row above the hearts ($20B6, 8 tiles).
STATUS_BAR_REDRAW = (0x20, 0xB6, 0x08)
UPDATING = 1                              # IsUpdatingMode while a mode's update runs (not its init)
HudBytes = tuple[int, tuple[int, ...]]    # (first address, the bytes there)


def hud_record(text: str) -> tuple[int, ...]:
    """The tile-buffer record of a HUD line: text (blank for "") cut to the row and centered in it."""
    from .rom.text_encoding import CHAR_TO_BYTE
    text = text[:HUD_WIDTH]
    text = " " * ((HUD_WIDTH - len(text)) // 2) + text
    blank = CHAR_TO_BYTE[" "]
    tiles = [CHAR_TO_BYTE.get(character, blank) for character in text]
    tiles += [blank] * (HUD_WIDTH - len(tiles))
    return (HUD_ROW >> 8, HUD_ROW & 0xFF, HUD_WIDTH, *tiles, inventory.DYN_TILE_BUF_END)


def hud_writes(text: str) -> tuple[HudBytes, ...]:
    """The record, then DynTileBufLen at its end's index."""
    record = hud_record(text)
    return (inventory.DYN_TILE_BUF, record), (inventory.DYN_TILE_BUF_LEN, (len(record) - 1,))


def tile_buffer_end(buffer: Sequence[int]) -> int | None:
    """Where the records in `buffer` (DynTileBuf's bytes) end, as TransferTileBuf reads them: the index of the first
    record start whose high byte has bit 7 set; None if a record runs past the buffer."""
    index = 0
    while index < len(buffer) and buffer[index] < inventory.NMI_ENABLED:
        if index + inventory.TILE_RECORD_HEADER > len(buffer):
            return None
        control = buffer[index + 2]
        count = control & inventory.TILE_RECORD_COUNT_MASK or inventory.TILE_RECORD_FULL_COUNT
        index += inventory.TILE_RECORD_HEADER + (1 if control & inventory.TILE_RECORD_REPEAT else count)
    return index if index < len(buffer) else None


# Caves and cellars, where a HUD line may also go after the game's own short records (hud_plans)
HUD_APPEND_MODES = (inventory.CELLAR_MODE, inventory.CAVE_MODE, inventory.CAVE_ROAD_MODE)
HUD_READS = ((inventory.CUR_PPU_CONTROL, 1), (inventory.GAME_MODE, 1),
             (inventory.DYN_TILE_BUF, inventory.DYN_TILE_BUF_SIZE))


def hud_plans(text: str, control: int, mode: int, buffer: Sequence[int]) -> tuple[tuple[tuple[HudBytes, ...],
                                                                                       tuple[HudBytes, ...]], ...]:
    """The (writes, guards) pairs to try in turn for a HUD line, given HUD_READS' bytes as read just before:
    CurPpuControl, GameMode and DynTileBuf. First the record alone (hud_writes) under each of hud_guard_sets;
    then, in a cave or cellar (HUD_APPEND_MODES) whose buffer holds a short record of the game's own (a typed
    character of cave text, the Item Counter's record), the line's record after it, guarded on every byte up to
    and including the end marker: the NMI sends both, and the game's record is kept (2026-11-23: in caves a line
    used to wait for the status-bar text's frames, which stop while cave text types, up to two seconds)."""
    plans = [(hud_writes(text), guards) for guards in hud_guard_sets(control)]
    end = tile_buffer_end(buffer)
    record = hud_record(text)
    if (inventory.frame_finished({inventory.CUR_PPU_CONTROL: control}) and mode in HUD_APPEND_MODES
            and end is not None and 0 < end and end + len(record) <= inventory.DYN_TILE_BUF_SIZE):
        guards = ((inventory.CUR_PPU_CONTROL, (control,)), (inventory.GAME_MODE, (mode,)),
                  (inventory.IS_UPDATING_MODE, (UPDATING,)), (inventory.TILE_BUF_SELECTOR, (0,)),
                  (inventory.DYN_TILE_BUF, tuple(buffer[:end + 1])))
        writes = ((inventory.DYN_TILE_BUF + end, record), (inventory.DYN_TILE_BUF_LEN, (end + len(record) - 1,)))
        plans.append((writes, guards))
    return tuple(plans)


def hud_guard_sets(control: int) -> tuple[tuple[HudBytes, ...], ...]:
    """The guards to try in turn, each a guarded_write's, given CurPpuControl as read just before: none at
    all unless the game's frame had finished (inventory.frame_finished), and each guarded on that value, so the
    record lands between frames, when the next thing to touch the buffer is the NMI that sends it. On a frame
    that lags, a write landed in the middle of the update, which then stored the status-bar text over the
    record's end (the NMI sent garbage to the nametables and CHR RAM) or its own record over the start (the
    line was dropped though the write succeeded).
      1. In play with an empty buffer.
      2. In play in place of the status-bar text, which fails the empty-buffer guard on its frames: the game
         sends it again two frames later.
      3. Cellars (CELLAR_MODE) play with GameSubmode left at its last init step (9), so they need their own
         guards: updating with an empty buffer. With the Item Counter on, its record (20 8B 04) fills the
         other frames, so the buffer is never empty there. Mode $A, the way out, never updates.
      4. Caves (CAVE_MODE, CAVE_ROAD_MODE) with an empty buffer, as in play (2026-11-23).
      5. Cellars and caves in place of the status-bar text. A typed character of cave text or the Item Counter's
         record is never replaced: hud_plans puts the line after it."""
    if not inventory.frame_finished({inventory.CUR_PPU_CONTROL: control}):
        return ()
    sending = ((inventory.CUR_PPU_CONTROL, (control,)), (inventory.IS_UPDATING_MODE, (UPDATING,)),
               (inventory.TILE_BUF_SELECTOR, (0,)))
    in_play = ((inventory.GAME_MODE, (inventory.PLAY_MODE,)), (inventory.GAME_SUBMODE, (0,)), *sending)
    empty = ((inventory.DYN_TILE_BUF, (inventory.DYN_TILE_BUF_END,)), (inventory.DYN_TILE_BUF_LEN, (0,)))
    redraw = ((inventory.DYN_TILE_BUF, STATUS_BAR_REDRAW),)
    in_cellar = ((inventory.GAME_MODE, (inventory.CELLAR_MODE,)), *sending)
    return ((*in_play, *empty), (*in_play, *redraw), (*in_cellar, *empty),
            *(((inventory.GAME_MODE, (mode,)), *sending, *empty)
              for mode in (inventory.CAVE_MODE, inventory.CAVE_ROAD_MODE)),
            *(((inventory.GAME_MODE, (mode,)), *sending, *redraw)
              for mode in (inventory.CELLAR_MODE, inventory.CAVE_MODE, inventory.CAVE_ROAD_MODE)))

# --- player settings, checked (for the world) -----------------------------------------------------------

def player_setting_problem(spec_key: str, value: Any) -> str | None:
    """What is wrong with one player setting's value (by its page key or YAML key, the value in
    the page's form or by its value key), or None when finish() accepts it."""
    try:
        check_player_settings({spec_key: value})
    except PlayerSettingError as problem:
        return str(problem)
    return None


def check_player_settings(values: Mapping[str, Any]) -> None:
    """PlayerSettingError unless finish() accepts these player settings as they are: every key a
    player setting's (page or YAML key, not both) or a retired one's (any value, ignored), every
    value one it takes."""
    known = {key for spec in player_setting_fields() for key in (spec.key, spec.yaml_key)}
    known |= RETIRED_SETTINGS | RETIRED_PAGE_SETTINGS
    unknown = sorted(str(key) for key in values if key not in known)
    if unknown:
        raise PlayerSettingError(f"unknown player settings: {unknown}")
    player_settings_from_page(page_player_settings(values))
    for key in MULTIWORLD_SETTINGS:
        multiworld_setting(values, key)
