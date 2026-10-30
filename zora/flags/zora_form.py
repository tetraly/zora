"""The ZORA Extras tab and the ZORA flag-string box: what the page builds and
shows for the ZORA flag string (zora/flags/zora_flags.py, docs/zora-extras.md).

flag_form.metadata() carries `zora_metadata()` and flag_form.form_state()
carries `zora_state()`, so the page keeps no ZORA field list or rule of its
own. A conflict (the sword-hearts owner requirement, Add L4 Sword
without Progressive Items) is never resolved for the player: the state lists each conflict with
the settings it names, and the page shows its message in red at each of them.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .fields import THREE_STATE_LABELS, TOGGLES_BY_ID, Settings, ThreeState
from .zora_flags import (
    ENUM_FIELDS,
    HEARTS_CAP_CHOICES,
    ITEM_SHUFFLE_NO_VANILLA_FIELD,
    SWORDLISH_HIGHEST_FIELD,
    SWORDLISH_LOWEST_FIELD,
    SWORDLISH_PIECES,
    THREE_STATE_FIELDS,
    L4Sword,
    Swordlish,
    ZoraFlags,
    ZoraFlagStringError,
    conflicts,
    decode,
    encode,
    forced_z1r_values,
    warnings,
)

TAB_NAME = "ZORA Extras"
THREE_STATE_KIND = "three_state"         # On / Off / ? (the version-3, -6, -7 and -8 fields)
FOLLOW_Z1R_LABEL = "Follow the Z1R flags"
TAKE_ANY_NOTE = ("The logic assumes sensible take-any choices: taking, say, a candle and two potions from "
                 "three take-any caves can make the seed unbeatable.")

# The tab's fields, in the order it shows them: name, kind, label, help.
FIELDS: tuple[dict[str, Any], ...] = (
    {"name": "randomize_magical_sword", "kind": "toggle", "label": "Randomize Magical Sword",
     "help": ("The magical sword joins the shuffled major items, and the magical-sword cave offers whatever "
              "item lands there, and the cave's own text names that item. The cave may ask for at most "
              "12 hearts: turn Change Sword Hearts off, or set the hearts cap below to 12 or lower. "
              "The logic counts the heart containers you can reach without the cave's item, plus the heart "
              "containers of all but two of the take-any caves you can reach. " + TAKE_ANY_NOTE)},
    {"name": "randomize_letter", "kind": "toggle", "label": "Randomize Letter",
     "help": ("The letter joins the shuffled major items, and the letter cave offers whatever item lands "
              "there. No new logic rules.")},
    {"name": "magical_sword_hearts_highest", "kind": "option", "label": "Magical-sword hearts, highest",
     "help": ("The most hearts the magical-sword cave may ask for. Follow the Z1R flags (10 to 14 with Change "
              "Sword Hearts on, 12 with it off), or cap it."),
     "values": [{"value": 0, "label": FOLLOW_Z1R_LABEL},
                *({"value": index, "label": f"At most {hearts} hearts"}
                  for index, hearts in enumerate(HEARTS_CAP_CHOICES, start=1))]},
    # PI-FLAG-02: the plan's help texts.
    {"name": "progressive_items", "kind": "toggle", "label": "Progressive Items",
     "help": ("Swords, candles, arrows, rings and boomerangs upgrade one level at a time: each one found or "
              "bought gives the next level you lack. A shop sells each upgrade once.")},
    {"name": "shop_items_in_pool", "kind": "toggle", "label": "Shop Items in the Item Pool",
     "help": ("The wooden arrows, blue candle, blue ring and bait join the shuffled major items, one bait "
              "for each hungry Goriya. A shop may sell the item that takes their place. With one Goriya, the "
              "other shop's bait becomes a fairy costing 20-40 rupees. Bait stacks, and the logic counts it only "
              "once every bait is found, so no Goriya can eat the one another needs.")},
    # Version 6: the ZORA 1.0 flags (docs/zora-extras.md section 13), each On / Off / ?.
    {"name": "allow_triforces_in_stairways", "kind": THREE_STATE_KIND, "label": "Allow Triforces in Stairways",
     "help": ("Before the items are shuffled, each level's Triforce picks a spot among that level's major "
              "item spots: an item staircase, a major item's room, or its own room. It never leaves its "
              "level. The item it displaces takes the Triforce's old room, then the shuffle runs as usual "
              "under any Item Shuffle setting.")},
    {"name": "shuffle_wood_sword", "kind": THREE_STATE_KIND, "label": "Shuffle Wood Sword",
     "help": ("The wood sword joins the shuffled major items, and its cave offers whatever item lands there "
              "(not Shuffle Wood Sword Cave, which moves the cave). A sword or the wand is always put in a "
              "cave you can walk into from the start: the wood sword cave, or the letter cave with Randomize "
              "Letter on when the wood sword cave's entrance is blocked.")},
    # Version 8: Expanded Dungeon Locations (owner and Bogie, 2026-10-18), On / Off / ?.
    {"name": "expanded_dungeon_locations", "kind": THREE_STATE_KIND, "label": "Expanded Dungeon Locations",
     "help": ("The nine dungeons are dealt onto 9 of 15 entrances: the first quest's nine and the second quest's "
              "six on other screens (2Q2, 2Q4, 2Q6, 2Q7, 2Q8 and 2Q9), so the recorder, raft, ladder or power "
              "bracelet may or may not be needed. Unchosen entrances stay closed or hold a cave; a shop on a "
              "chosen entrance moves to a free open cave. With Cave Shuffle: Dungeons Only this is Expanded "
              "Brackets, the other caves where they are; with All Caves, every other cave is shuffled too. "
              "Needs Overworld Quest: 1st Quest or 2nd Quest.")},
    # Version 9: Highlight No-Drop Rooms (owner decision, 2026-10-18), On / Off / ?.
    {"name": "highlight_no_drop_rooms", "kind": THREE_STATE_KIND, "label": "Highlight No-Drop Rooms",
     "help": ("In the dungeons, a room with blocks that can never hold an item draws its blocks in the "
              "level's other block color; every other room with blocks uses the usual one. No colors "
              "change, so in a level whose two block colors are the same the difference doesn't show. "
              "Rooms without blocks (water, the entrance) look as before. Does nothing with Allow "
              "Universal Drops In Shapes on.")},
    # Version 10: Do Not Segment Dungeons (owner, 2026-10-22; tetraly/zora#6 and #7), On / Off / ?.
    {"name": "do_not_segment_dungeons", "kind": THREE_STATE_KIND, "label": "Do Not Segment Dungeons",
     "help": ("Shapes dungeons are never split into segments: every room can be reached through "
              "doors, and stairways become shortcuts.")},
    # Version 14: Harder Bosses and Harder Ganon (docs/zora-extras.md section 21; from Z1M1, MetalMachine).
    {"name": "harder_bosses", "kind": "option", "label": "Harder Bosses",
     "help": ("Digdogger and Manhandla move faster, Gohma fires more often, and Aquamentus fires more "
              "often and less regularly. Level 1 is a little harder, Level 3 much harder. The other "
              "bosses are unchanged, and no boss gains hit points or damage."),
     "values": [{"value": 0, "label": "Off"}, {"value": 1, "label": "Level 1"},
                {"value": 2, "label": "Level 2"}, {"value": 3, "label": "Level 3"}]},
    # Version 15: the pacing settings (docs/zora-extras.md section 22; from Z1M1, MetalMachine).
    {"name": "offense_pacing", "kind": "option", "label": "Offense Item Pacing",
     "help": ("How soon the swords must come. The logic asks for a number of swords before it counts a "
              "dungeon's items, and counts sword items, not their tiers (the wooden sword is one). Earlier: 1 sword "
              "for levels 1 to 4, 2 from level 5. Normal: 1 sword from level 3, 2 from level 7. Later: 1 sword "
              "from level 5, 2 for level 9. Off asks for none. Needs Swords: Normal."),
     "values": [{"value": 0, "label": "Off"}, {"value": 1, "label": "Earlier"},
                {"value": 2, "label": "Normal"}, {"value": 3, "label": "Later"}]},
    {"name": "defense_pacing", "kind": "option", "label": "Defense Item Pacing",
     "help": ("How soon the rings must come. The logic asks for a number of rings before it counts a "
              "dungeon's items. Earlier: 1 ring from level 5, 2 for level 9. Normal: 1 ring from level 7. "
              "Later: 1 ring for level 9. Off asks for none. The blue ring counts once its shop's door is "
              "reached."),
     "values": [{"value": 0, "label": "Off"}, {"value": 1, "label": "Earlier"},
                {"value": 2, "label": "Normal"}, {"value": 3, "label": "Later"}]},
    {"name": "recorder_warping", "kind": "toggle", "label": "Recorder Warping",
     "help": ("The logic may ask you to reach a dungeon by playing the recorder instead of using the raft, "
              "where the dungeon's door stands on a screen only the raft reaches. Greyed out, and doing nothing, "
              "unless both Recorder to Unbeaten Dungeons and Recorder to New Dungeons are on.")},
    {"name": "harder_ganon", "kind": "option", "label": "Harder Ganon",
     "help": ("Ganon heals slowly while the sword can hurt him, the time he stays visible after a hit "
              "varies, he may jump to another spot while the silver arrows can finish him, and Ganon's "
              "room shoots fireballs. Level 1 is a little harder, Level 3 much harder."),
     "values": [{"value": 0, "label": "Off"}, {"value": 1, "label": "Level 1"},
                {"value": 2, "label": "Level 2"}, {"value": 3, "label": "Level 3"}]},
    # The owner's 2.0 flags (docs/design/zora-flags-2.0.md): each On / Off / ?, "?" decided per seed.
    *({"name": name, "kind": THREE_STATE_KIND, "label": label, "help": help_text} for name, label, help_text in (
        ("shuffle_blue_potion", "Shuffle Blue Potion",
         ("A blue potion joins the shuffled major items from the potion shop's middle slot, which sells "
          "any major item once in its place (never the letter, which opens the shop). The shop's own blue "
          "and red potions stay. With a needed item there, the logic needs the letter too.")),
        ("extra_raft_blocks", "Extra Raft Blocks",
         "Six more cave screens near Westlake Mall and Casino Corner can only be reached by raft."),
        ("extra_power_bracelet_blocks", "Extra Power Bracelet Blocks",
         ("Seven more cave screens on West Death Mountain sit behind power-bracelet boulders. Needs "
          'Shuffle "Take Any Road" Caves off.')),
        ("speed_up_dungeon_transitions", "Speed Up Dungeon Transitions",
         "No scroll delay between dungeon rooms. By fiskbit."),
        ("speed_up_heart_fill", "Speed Up Heart Fill",
         "Fairies and potions refill hearts four times as fast. By snarfblam."),
        ("recorder_kills_pols_voice", "Recorder Kills Dungeon Pols Voice",
         "In a dungeon, playing the recorder kills every Pols Voice in the room. By Stratoform."),
        ("four_potion_inventory", "Four Potion Inventory",
         "You can carry four potions instead of two."),
        ("like_like_eats_rupees", "Like-Like Eats Rupees",
         "A Like-Like drains rupees instead of eating the magical shield. By gzip."),
        ("magical_boomerang_damage", "Magical Boomerang Does 1 HP Damage",
         "The magical boomerang deals 1 HP of damage as well as stunning."),
        ("randomize_lost_hills", "Randomize Lost Hills",
         ("The Lost Hills' path is new. The hint shop that sells the path in the original game sells the new "
          "one, for 1 rupee; the screens beyond the maze need it in the logic.")),
        ("randomize_dead_woods", "Randomize Dead Woods",
         ("The Dead Woods' path is new. The hint shop that sells the path in the original game sells the new "
          "one, for 1 rupee; the screens beyond the maze need it in the logic. The maze now lets you out to the "
          "south, so Add Lost Woods Shortcut is on with it, the way west.")),
        ("full_health", "Start With Full Health",
         ("Loading a save file, and continuing or retrying after death, leave every heart container full. "
          "By ShadowOne333, kalita-kun and gzip.")),
    )),
)
FIELD_NAMES = tuple(field["name"] for field in FIELDS)

# All Swords No Boards (docs/design/asnb.md section 1). Add L4 Sword is one three-way control over
# two encoded fields (the released three-state add_l4_sword and version 4's l4_sword_in_level_2),
# placed where its old switch was; Level 9 Entrance follows it. Neither has a random option.
L4_SWORD_FIELD = "add_l4_sword"
LEVEL_9_ENTRANCE_FIELD = "level_9_entrance_sword"
L4_SWORD_CHOICES = (L4Sword.OFF, L4Sword.LEVEL_2, L4Sword.LEVEL_9)        # control values 0, 1, 2
L4_SWORD_HELP = (
    "Off: no level-4 sword. Level 2: a new item staircase is added to level 2, holding one more sword "
    "upgrade. That sword joins the item shuffle, so it can end up anywhere. Collect all four sword "
    "upgrades, in any order, for a level-4 sword. Needs generated dungeon shapes. Level 9: one more sword "
    "upgrade is added to level 9 as a floor item (a room item). Taken with the magical sword, it gives a "
    "level-4 sword. Needs Progressive Items.")
LEVEL_9_ENTRANCE_HELP = (
    "Triforce pieces: the NPC at level 9's entrance lets you in with the triforce pieces, as always. "
    "Level 4 sword: level 9 opens for a level-4 sword only; no triforce pieces are needed. Needs Add L4 "
    "Sword = Level 2 and the wooden sword in its cave.")
_L4_SWORD_FIELDS = (
    {"name": L4_SWORD_FIELD, "kind": "option", "label": "Add L4 Sword", "help": L4_SWORD_HELP,
     "values": [{"value": 0, "label": "Off"}, {"value": 1, "label": "Level 2"}, {"value": 2, "label": "Level 9"}]},
    {"name": LEVEL_9_ENTRANCE_FIELD, "kind": "option", "label": "Level 9 Entrance", "help": LEVEL_9_ENTRANCE_HELP,
     "values": [{"value": 0, "label": "Triforce pieces"}, {"value": 1, "label": "Level 4 sword"}]},
)
_AFTER = FIELD_NAMES.index("shuffle_blue_potion") + 1
FIELDS = (*FIELDS[:_AFTER], *_L4_SWORD_FIELDS, *FIELDS[_AFTER:])

# Oops All (docs/design/oops-all.md section 3): version 5's two option fields, before Pegasus Boots.
_OOPS_ALL_FIELDS = (
    {"name": "oops_all_enemies", "kind": "option", "label": "Oops All Enemies",
     "help": ("Every dungeon room's enemies come from one family, drawn room by room: Wizzrobes (red and "
              "blue), Keese (blue, red and dark) or Bouncers (Pols Voice and Vire). Rooms keep their enemy "
              "counts. Bosses, people, traps and Bubbles stay."),
     "values": [{"value": 0, "label": "Off"}, {"value": 1, "label": "Wizzrobes"},
                {"value": 2, "label": "Keese"}, {"value": 3, "label": "Bouncers"}]},
    {"name": "oops_all_bosses", "kind": "option", "label": "Oops All Bosses",
     "help": ("Dodongos: every boss room in levels 1 to 8 holds Dodongos, triple or single, wherever its "
              "layout allows them; the few rooms that cannot keep their own boss. Level 9 is unchanged."),
     "values": [{"value": 0, "label": "Off"}, {"value": 1, "label": "Dodongos"}]},
)
FIELDS = (*FIELDS, *_OOPS_ALL_FIELDS)

# Disable Custom Music (docs/design/music-settings.md section 7): before Pegasus Boots, which stays last.
DISABLE_CUSTOM_MUSIC_FIELD = {
    "name": "disable_custom_music", "kind": "toggle", "label": "Disable Custom Music",
    "help": ("For races: the Music setting offers only Off and Vanilla, so every racer plays with the game's "
             "own sound engine. Randomized music changes how often the game lags a little, so it could give "
             "one racer an edge over another. It changes nothing in the seed itself.")}
FIELDS = (*FIELDS, DISABLE_CUSTOM_MUSIC_FIELD)

# Pegasus Boots last on the tab (owner request, beta 7), so the page's pairs (Randomize Lost Hills
# and Dead Woods, Oops All Enemies and Bosses) share their lines. Only the tab's order: the flag
# string encodes ZoraFlags' fields by name (zora_flags_from_values), so its place there stays.
PEGASUS_BOOTS_FIELD = {"name": "pegasus_boots", "kind": THREE_STATE_KIND, "label": "Pegasus Boots",
                       "help": ("The boomerang becomes the Pegasus Boots and the magical boomerang the Magical "
                                "Boots. With them on B, hold B and a direction to run: the Pegasus Boots charge "
                                "for half a second, then run about a third faster than walking; the Magical "
                                "Boots run about three quarters faster at once. Release B to walk. The file "
                                "saved after the ending holds the Magical Boots. Needs "
                                "Magical Boomerang Does 1 HP Damage off. With a custom-sprite ROM, a custom "
                                "sprite in the boomerang's tiles is replaced by the boot.")}
# Version 16: BogieSmalls' additions (features-behavior.md FP-SWAP and FP-SWL; docs/zora-extras.md
# section 23), named as he names them.
BOGIESMALLS_CREDIT = "From BogieSmalls."
SWORDLISH_RANGE_HELP = ("The pieces the wooden sword costs under Swordlish are drawn per seed from this range "
                        "(a reversed range is put in order).")
BOGIESMALLS_FIELDS: tuple[dict[str, Any], ...] = (
    {"name": "swap_swords_and_rings", "kind": THREE_STATE_KIND, "label": "Swap Swords and Rings",
     "help": ("The White Sword and the Blue Ring trade places wherever they were placed, and so do the Magical "
              "Sword and the Red Ring: the White Sword is sold where the Blue Ring was, at its price, and the "
              "magical-sword cave offers the Red Ring for its hearts. Each cave keeps its heart requirement, "
              "and the hints name what is really there. A pair with a starting item is not swapped. Not with "
              "Swords: Wood Sword Only or Swordless. " + BOGIESMALLS_CREDIT)},
    {"name": "swordlish", "kind": "option", "label": "Swordlish",
     "help": ("The wooden-sword cave gives its sword only to a player holding N triforce pieces (starting "
              "pieces count), and its old man says how many. The logic reaches the sword once N levels are "
              "won, or treats the white sword as the first sword. Swordlish removes the cave's extra candle (Extra "
              "Candles still adds the other one). Random picks one of five per seed: Normal, Wood Sword Only, "
              "No Wood Sword, Swordless or Swordlish. Needs Swords: Normal. " + BOGIESMALLS_CREDIT),
     "values": [{"value": int(Swordlish.OFF), "label": "Off"}, {"value": int(Swordlish.ON), "label": "On"},
                {"value": int(Swordlish.RANDOM), "label": "Random"}]},
    *({"name": name, "kind": "option", "label": label, "help": SWORDLISH_RANGE_HELP,
       "values": [{"value": pieces - SWORDLISH_PIECES[0], "label": str(pieces)} for pieces in SWORDLISH_PIECES],
       **extra}
      for name, label, extra in (
          # The page's flag summary reads the pair as one line, and only while Swordlish is not Off.
          (SWORDLISH_LOWEST_FIELD, "Swordlish pieces (min)",
           {"summaryRange": {"max": SWORDLISH_HIGHEST_FIELD, "needs": "swordlish"}}),
          (SWORDLISH_HIGHEST_FIELD, "Swordlish pieces (max)", {}))),
)
FIELDS = (*FIELDS, PEGASUS_BOOTS_FIELD, *BOGIESMALLS_FIELDS)
# Version 17: Item Shuffle: Random (No Vanilla) (owner, 2026-10-29). The page offers it as Item Shuffle's sixth
# choice (flag_form.ITEM_SHUFFLE_NO_VANILLA_CHOICE), never on this tab: its row is hidden, and its control only
# carries the value between the two strings.
ITEM_SHUFFLE_NO_VANILLA_ROW = {
    "name": ITEM_SHUFFLE_NO_VANILLA_FIELD, "kind": "toggle", "label": "Item Shuffle: Random (No Vanilla)",
    "hidden": True,
    "help": "Set by Item Shuffle's Random (No Vanilla): each seed draws Item Only, Intra-Dungeon or Full, never None."}
FIELDS = (*FIELDS, ITEM_SHUFFLE_NO_VANILLA_ROW)
FIELD_NAMES = tuple(field["name"] for field in FIELDS)


def _with_switch_values(field: dict[str, Any]) -> dict[str, Any]:
    """A switch with its states and their names, as an option field carries its values."""
    if field["kind"] == "option":
        return field
    states = list(ThreeState) if field["kind"] == THREE_STATE_KIND else [ThreeState.OFF, ThreeState.ON]
    return {**field, "values": [{"value": int(state), "label": THREE_STATE_LABELS[state]} for state in states]}


def zora_metadata() -> dict[str, Any]:
    return {"tab": TAB_NAME, "fields": [_with_switch_values(field) for field in FIELDS]}


def control_value(flags: ZoraFlags, name: str) -> int:
    """A field as the page's control holds it: 0/1 for a switch, the option's index for the cap
    and for Add L4 Sword's three-way control (a released string's "?" there, which the control does
    not offer, shows Off; the string itself keeps it until a control is changed)."""
    if name == L4_SWORD_FIELD:
        return L4_SWORD_CHOICES.index(flags.l4_sword)
    value = getattr(flags, name)
    if name == "magical_sword_hearts_highest":
        return 0 if value is None else HEARTS_CAP_CHOICES.index(value) + 1
    if name in (SWORDLISH_LOWEST_FIELD, SWORDLISH_HIGHEST_FIELD):
        return int(value) - SWORDLISH_PIECES[0]
    return int(value)


def _field_value(name: str, control: int) -> bool | int | ThreeState | None:
    if name in ENUM_FIELDS:
        return ENUM_FIELDS[name](control)
    if name == "magical_sword_hearts_highest":
        return None if control == 0 else HEARTS_CAP_CHOICES[control - 1]
    if name in (SWORDLISH_LOWEST_FIELD, SWORDLISH_HIGHEST_FIELD):
        return SWORDLISH_PIECES[0] + control         # a control counts from 0, as every option's does
    if name in THREE_STATE_FIELDS:
        return ThreeState(control)
    return bool(control)


# Recorder Warping does something only where the recorder warps to an unbeaten dungeon's door (Recorder to
# Unbeaten Dungeons, OW-WARP-02) and to the new doors (Recorder to New Dungeons, OW-WARP-01): the page greys it out
# until both are on.
RECORDER_WARPING_NEEDS = (TOGGLES_BY_ID["B01"], TOGGLES_BY_ID["B07"])
RECORDER_WARPING_UNAVAILABLE = ("Recorder Warping does nothing until both Recorder to Unbeaten Dungeons and Recorder "
                                "to New Dungeons are on.")


def unavailable_fields(z1r: Settings | None) -> list[dict[str, str]]:
    """The ZORA settings that do nothing under these Z1R settings, each with its note."""
    if z1r is None or all(z1r.toggle(toggle) is ThreeState.ON for toggle in RECORDER_WARPING_NEEDS):
        return []
    return [{"field": "recorder_warping", "message": RECORDER_WARPING_UNAVAILABLE}]


def zora_state(zora_flag_string: str, z1r: Settings | None) -> dict[str, Any]:
    """The ZORA box and tab for a ZORA string: its canonical spelling and control values, or
    the decoder's error; and each conflict and warning with the settings it names (judged against
    the Z1R settings when they decode)."""
    try:
        flags = decode(zora_flag_string.strip())
    except ZoraFlagStringError as exc:
        return {"ok": False, "error": f"ZORA flag string: {exc}"}
    found = conflicts(flags, z1r) if z1r is not None else []
    warned = warnings(flags, z1r) if z1r is not None else []
    return {
        "ok": True,
        "flags": encode(flags),
        "values": {name: control_value(flags, name) for name in FIELD_NAMES},
        "conflicts": [{"message": message, "fields": list(names)} for message, names in found],
        # accepted, but worth a note beside the settings it names (not red)
        "warnings": [{"message": message, "fields": list(names)} for message, names in warned],
        # Z1R fields these flags set whatever the Z1R string holds (shown so, with the note)
        "forced": [{"field": field_id, "value": int(value), "message": message}
                   for field_id, value, message in forced_z1r_values(flags)],
        # ZORA settings greyed out until the Z1R settings they need are on (the value is kept)
        "unavailable": unavailable_fields(z1r),
    }


def zora_flags_from_values(values: Mapping[str, int | str]) -> str:
    """The canonical ZORA string of the tab's control values (the page reads them as strings)."""
    unknown = set(values) - set(FIELD_NAMES)
    if unknown:
        raise ValueError(f"unknown ZORA fields {sorted(unknown)}")
    chosen: dict[str, Any] = {name: _field_value(name, int(control)) for name, control in values.items()
                              if name != L4_SWORD_FIELD}
    if L4_SWORD_FIELD in values:
        setting = L4_SWORD_CHOICES[int(values[L4_SWORD_FIELD])]
        chosen["add_l4_sword"] = ThreeState.OFF if setting is L4Sword.OFF else ThreeState.ON
        chosen["l4_sword_in_level_2"] = setting is L4Sword.LEVEL_2
    return encode(ZoraFlags(**chosen))
