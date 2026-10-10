"""The ZORA Extras tab and the ZORA flag-string box: what the page builds and
shows for the ZORA flag string (zora/flags/zora_flags.py, docs/zora-extras.md).

flag_form.metadata() carries `zora_metadata()` and flag_form.form_state()
carries `zora_state()`, so the page keeps no ZORA field list or rule of its
own. A conflict (the sword-hearts owner requirement, PI-FLAG-03's Extra
Candles) is never resolved for the player: the state lists each conflict with
the settings it names, and the page shows its message in red at each of them.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .fields import Settings, ThreeState
from .zora_flags import (
    HEARTS_CAP_CHOICES,
    OWNER_2_0_FIELDS,
    L4Sword,
    ZoraFlags,
    ZoraFlagStringError,
    conflicts,
    decode,
    encode,
)

TAB_NAME = "ZORA Extras"
THREE_STATE_KIND = "three_state"         # On / Off / ? (the version-3 fields)
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
     "help": ("The wooden arrows, blue candle and blue ring join the shuffled major items. A shop may sell "
              "the item that takes their place.")},
    # The owner's 2.0 flags (docs/design/zora-flags-2.0.md): each On / Off / ?, "?" decided per seed.
    *({"name": name, "kind": THREE_STATE_KIND, "label": label, "help": help_text} for name, label, help_text in (
        ("shuffle_blue_potion", "Shuffle Blue Potion",
         "A blue potion joins the shuffled major items from the potion shop's middle slot, which sells "
         "any major item once in its place (never the letter, which opens the shop). The shop's own blue "
         "and red potions stay. With a needed item there, the logic needs the letter too."),
        ("extra_raft_blocks", "Extra Raft Blocks",
         "Six more cave screens near Westlake Mall and Casino Corner can only be reached by raft."),
        ("extra_power_bracelet_blocks", "Extra Power Bracelet Blocks",
         "Seven more cave screens on West Death Mountain sit behind power-bracelet boulders. Needs "
         'Shuffle "Take Any Road" Caves off.'),
        ("speed_up_dungeon_transitions", "Speed Up Dungeon Transitions",
         "No scroll delay between dungeon rooms."),
        ("speed_up_heart_fill", "Speed Up Heart Fill",
         "Fairies and potions refill hearts four times as fast. By snarfblam."),
        ("recorder_kills_pols_voice", "Recorder Kills Dungeon Pols Voice",
         "In a dungeon, playing the recorder kills every Pols Voice in the room. By Stratoform."),
        ("four_potion_inventory", "Four Potion Inventory",
         "You can carry four potions instead of two."),
        ("auto_show_letter", "Auto Show Letter",
         "The old woman takes the letter as soon as you have it, without using it."),
        ("like_like_eats_rupees", "Like-Like Eats Rupees",
         "A Like-Like drains rupees instead of eating the magical shield."),
        ("magical_boomerang_damage", "Magical Boomerang Does 1 HP Damage",
         "The magical boomerang deals 1 HP of damage as well as stunning."),
        ("randomize_lost_hills", "Randomize Lost Hills",
         "The Lost Hills' path is new. The hint shop that sells the path in the original game sells the new "
         "one, for 1 rupee; the screens beyond the maze need it in the logic."),
        ("randomize_dead_woods", "Randomize Dead Woods",
         "The Dead Woods' path is new. The hint shop that sells the path in the original game sells the new "
         "one, for 1 rupee; the screens beyond the maze need it in the logic."),
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
    "Triforce pieces: the old man at level 9's entrance lets you in with the triforce pieces, as always. "
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
FIELD_NAMES = tuple(field["name"] for field in FIELDS)


def zora_metadata() -> dict[str, Any]:
    return {"tab": TAB_NAME, "fields": list(FIELDS)}


def control_value(flags: ZoraFlags, name: str) -> int:
    """A field as the page's control holds it: 0/1 for a switch, the option's index for the cap
    and for Add L4 Sword's three-way control (a released string's "?" there, which the control does
    not offer, shows Off; the string itself keeps it until a control is changed)."""
    if name == L4_SWORD_FIELD:
        return L4_SWORD_CHOICES.index(flags.l4_sword)
    value = getattr(flags, name)
    if name == "magical_sword_hearts_highest":
        return 0 if value is None else HEARTS_CAP_CHOICES.index(value) + 1
    return int(value)


def _field_value(name: str, control: int) -> bool | int | ThreeState | None:
    if name == "magical_sword_hearts_highest":
        return None if control == 0 else HEARTS_CAP_CHOICES[control - 1]
    if name in OWNER_2_0_FIELDS:
        return ThreeState(control)
    return bool(control)


def zora_state(zora_flag_string: str, z1r: Settings | None) -> dict[str, Any]:
    """The ZORA box and tab for a ZORA string: its canonical spelling and control values, or
    the decoder's error; and each conflict with the settings it names (judged against the Z1R
    settings when they decode)."""
    try:
        flags = decode(zora_flag_string.strip())
    except ZoraFlagStringError as exc:
        return {"ok": False, "error": f"ZORA flag string: {exc}"}
    found = conflicts(flags, z1r) if z1r is not None else []
    return {
        "ok": True,
        "flags": encode(flags),
        "values": {name: control_value(flags, name) for name in FIELD_NAMES},
        "conflicts": [{"message": message, "fields": list(names)} for message, names in found],
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
