# ZORA UI Data Flow & Architecture Diagrams

## 1. Application Initialization Flow

```
main(page, platform)
    │
    ├─ Create State Objects
    │  ├─ RomInfo()
    │  ├─ FlagState()
    │  └─ AppState(rom_info, flag_state)
    │
    ├─ Create Event Handlers
    │  └─ EventHandlers(page, state, platform)
    │
    ├─ Build UI Components
    │  ├─ build_header()
    │  ├─ build_step1_container()
    │  ├─ build_flag_checkboxes()
    │  └─ build_step2_container()
    │
    ├─ Initialize File Pickers
    │  ├─ rom_file_picker
    │  └─ generate_vanilla_file_picker
    │
    └─ Render to Page
       └─ page.add(main_content)
```

---

## 2. Step 2 Component Construction Flow

```
build_step2_container(
    categorized_flag_rows,
    flagstring_input,
    seed_input,
    random_seed_button,
    on_randomize,
    on_expand_all,
    on_collapse_all,
    expansion_panels_ref,
    legacy_note_ref
)
    │
    ├─ Create Input Section
    │  └─ Row[TextField(flags), Row[TextField(seed), Button]]
    │
    ├─ Create Control Section
    │  └─ Row[Button("Expand All"), Button("Collapse All")]
    │
    ├─ Loop Through FlagCategories
    │  ├─ Category 1: ITEM_SHUFFLE
    │  │  ├─ Split flags into 2 columns
    │  │  ├─ Create colored header
    │  │  └─ Create ExpansionPanel
    │  │
    │  ├─ Category 2: ITEM_CHANGES
    │  │  └─ [Same pattern]
    │  │
    │  ├─ ...
    │  │
    │  └─ Category N: LEGACY
    │     ├─ Create warning note
    │     ├─ Store in legacy_note_ref
    │     └─ Create ExpansionPanel with warning
    │
    ├─ Create ExpansionPanelList
    │  └─ Add all panels
    │
    ├─ Create Action Section
    │  └─ Button("Randomize")
    │
    └─ Return Container with all sections
```

---

## 3. Flag Checkbox Creation Flow

```
build_flag_checkboxes(flag_state, on_change_callback)
    │
    ├─ Initialize:
    │  ├─ flag_checkboxes = {}
    │  └─ categorized_flag_rows = {category: [] for each}
    │
    ├─ Loop Through FlagsEnum
    │  │
    │  ├─ Skip if: HIDDEN category
    │  ├─ Skip if: in complex_flags set
    │  │
    │  └─ For Each Valid Flag:
    │     │
    │     ├─ Create ft.Checkbox
    │     │  ├─ label: flag.display_name
    │     │  ├─ value: False (default)
    │     │  └─ on_change: lambda(key, value) -> on_change_callback
    │     │
    │     ├─ Create ft.IconButton (help)
    │     │  ├─ icon: HELP_OUTLINE
    │     │  ├─ tooltip: flag.help_text
    │     │  └─ padding: 2px
    │     │
    │     ├─ Create ft.Row combining checkbox + help icon
    │     │  └─ spacing: 0, tight: True
    │     │
    │     ├─ Store checkbox in flag_checkboxes[flag.value]
    │     │
    │     └─ Add row to categorized_flag_rows[flag.category]
    │
    └─ Return (flag_checkboxes, categorized_flag_rows)
```

---

## 4. Flag State Change & Synchronization Flow

```
User clicks checkbox
    │
    └─> Checkbox.on_change event
        │
        └─> lambda e, key='flag_key': on_change_callback(key, e.control.value)
            │
            └─> EventHandlers.on_checkbox_changed(flag_key, value)
                │
                ├─ FlagState.flags[flag_key] = value
                │
                ├─ Check if Major Item Shuffle:
                │  └─ If disabled, disable 13 related shuffle flags
                │     └─ Update their checkboxes in UI
                │
                ├─ update_flagstring()
                │  │
                │  ├─ Call FlagState.to_flagstring()
                │  │  │
                │  │  ├─ Get all non-complex flags
                │  │  ├─ Build binary string from states
                │  │  ├─ Group into 3-bit chunks
                │  │  ├─ Convert each chunk to octal (0-7)
                │  │  ├─ Map to letters: B,C,D,F,G,H,K,L
                │  │  └─ Return 5-letter string
                │  │
                │  └─ Set flagstring_input.value = result
                │
                └─ page.update()
```

---

## 5. Expand/Collapse All Buttons Flow

```
User clicks "Expand All" or "Collapse All"
    │
    ├─ on_expand_all(e)
    │  └─ Loop: for panel in self.expansion_panels_ref:
    │     └─ panel.expanded = True
    │
    └─ on_collapse_all(e)
       └─ Loop: for panel in self.expansion_panels_ref:
          └─ panel.expanded = False
    
    Then:
    └─ page.update()
```

---

## 6. Legacy Flag Visibility Control Flow

```
ROM Loading Complete
    │
    ├─ determine rom_type (vanilla or randomized)
    │
    ├─ call update_legacy_flags_state()
    │  │
    │  ├─ is_vanilla = (rom_info.rom_type == "vanilla")
    │  │
    │  ├─ For each flag in FlagsEnum:
    │  │  └─ If flag.category == LEGACY:
    │  │     │
    │  │     ├─ Get checkbox from flag_checkboxes[flag.value]
    │  │     │
    │  │     ├─ If NOT vanilla (is randomized):
    │  │     │  ├─ checkbox.disabled = True
    │  │     │  ├─ checkbox.label_style = GREY_500 text
    │  │     │  ├─ checkbox.value = False
    │  │     │  └─ flag_state.flags[flag.value] = False
    │  │     │
    │  │     └─ Else (is vanilla):
    │  │        ├─ checkbox.disabled = False
    │  │        └─ checkbox.label_style = None (default)
    │  │     
    │  │     └─ checkbox.update()
    │  │
    │  └─ For each note in legacy_note_ref:
    │     ├─ If NOT vanilla:
    │     │  └─ note.visible = True
    │     └─ Else:
    │        └─ note.visible = False
    │     
    │     └─ note.update()
    │
    └─ page.update()
```

---

## 7. Component Reference Management Architecture

```
EventHandlers
├─ expansion_panels_ref: list
│  │  
│  └─ Populated in build_step2_container()
│     └─ One entry per visible FlagCategory
│        └─ Used by: on_expand_all(), on_collapse_all()
│
├─ legacy_note_ref: list
│  │
│  └─ Populated in build_step2_container()
│     └─ One entry for LEGACY category warning note
│        └─ Used by: update_legacy_flags_state()
│
├─ flag_checkboxes: dict
│  │
│  ├─ Keys: flag.value (e.g., 'major_item_shuffle')
│  ├─ Values: ft.Checkbox objects
│  │
│  └─ Used by:
│     ├─ on_checkbox_changed() - direct state update
│     ├─ on_flagstring_changed() - sync from string
│     ├─ update_legacy_flags_state() - disable legacy
│     └─ Major Item Shuffle logic - cascade disable
│
└─ step2_container: ft.Container
   │
   └─ Used by:
      ├─ enable_step2() - set disabled=False, opacity=1.0
      └─ disable_step2() - set disabled=True, opacity=0.4
```

---

## 8. Expansion Panel Structure (Visual)

```
ExpansionPanelList (ft.ExpansionPanelList)
├─ elevation: 2
├─ divider_color: PURPLE_100
├─ expand_icon_color: PURPLE_700
│
└─ controls: [
    ExpansionPanel (ITEM_SHUFFLE)
    ├─ header:
    │  └─ Container (border: BLUE_600)
    │     └─ ListTile
    │        └─ Text("Item Shuffle", bold)
    │
    ├─ content:
    │  └─ Container
    │     └─ Row
    │        ├─ Column (left flags)
    │        │  └─ Row[Checkbox + Help Icon] x N
    │        └─ Column (right flags)
    │           └─ Row[Checkbox + Help Icon] x N
    │
    ├─ can_tap_header: True
    └─ expanded: True (initially)
    
    ExpansionPanel (ITEM_CHANGES)
    ├─ header:
    │  └─ Container (border: PURPLE_600)
    │     └─ ListTile
    │        └─ Text("Item Changes", bold)
    │
    └─ [Same content structure]
    
    ...
    
    ExpansionPanel (LEGACY)
    ├─ header:
    │  └─ Container (border: GREY_600)
    │     └─ ListTile
    │        └─ Text("Legacy Flags...", bold)
    │
    ├─ content:
    │  └─ Container
    │     └─ Column
    │        ├─ Container (warning note)
    │        │  └─ Text("⚠️ Legacy flags are only...")
    │        │     visible: True/False (based on ROM type)
    │        │
    │        └─ Row (actual flag layout)
    │           └─ [Two-column flag layout]
    │
    └─ [Same panel config]
  ]
```

---

## 9. Flag State Synchronization (Bidirectional)

```
FlagState Object
├─ flags: dict
│  ├─ 'major_item_shuffle': False
│  ├─ 'shuffle_wood_sword_cave_item': False
│  └─ [50+ more flags]
│
├─ to_flagstring() -> str
│  └─ Returns: "BCDGH" (example)
│
└─ from_flagstring(str) -> bool
   └─ Parses: "BCDGH"
      └─ Updates: flags dict

                    ↑ ↓
UI Layer (Checkboxes & Input)
├─ Checkboxes in panels
│  └─ Value synced with flags dict
│
└─ flagstring_input TextField
   └─ Value synced with to_flagstring() result
```

---

## 10. Step 2 Container Lifecycle

```
Initial State (No ROM loaded):
    Step 2 Container
    ├─ disabled: True
    ├─ opacity: 0.4 (faded)
    └─ All controls visible but inactive

                ↓ (ROM selected and loaded)

Active State (ROM loaded):
    Step 2 Container
    ├─ disabled: False
    ├─ opacity: 1.0 (fully visible)
    ├─ Flag inputs enabled
    ├─ Expansion panels active
    ├─ Expand/Collapse buttons active
    └─ Randomize button enabled

                ↓ (ROM type-specific adjustments)

Vanilla ROM Loaded:
    ├─ Legacy flags: ENABLED (enabled=True, normal color)
    └─ Legacy warning note: HIDDEN (visible=False)

Randomized ROM Loaded:
    ├─ Legacy flags: DISABLED (disabled=True, GREY_500 color)
    ├─ Legacy warning note: VISIBLE (visible=True)
    └─ Legacy flags: UNCHECKED (value=False)
```

---

## 11. Input & Seed Management

```
ZORA Seed Input
├─ Type: ft.TextField
├─ Label: "ZORA Seed Number"
├─ Default: "12345"
├─ Handler: None (manual entry)
└─ State stored in: handlers.seed_input.value

Seed Random Button
├─ Type: ft.ElevatedButton
├─ Icon: SHUFFLE
├─ Handler: on_random_seed_click
└─ Action: Generates random seed -> updates seed_input.value

ZORA Flag String Input
├─ Type: ft.TextField
├─ Label: "ZORA Flag String"
├─ Handler: on_flagstring_changed
└─ Action: 
   ├─ Parse input string
   ├─ Call FlagState.from_flagstring()
   └─ Update all checkboxes to match

Flag String Auto-Update
├─ Triggered by: Any checkbox change
├─ Handler: update_flagstring()
└─ Action:
   ├─ Call FlagState.to_flagstring()
   └─ Update flagstring_input.value
```

---

## 12. Two-Column Flag Layout Algorithm

```
flags_in_category = [flag_row_1, flag_row_2, ..., flag_row_N]

mid = (len(flags_in_category) + 1) // 2
      └─ Ceiling division to favor left column

left_flags = flags_in_category[0:mid]
             └─ First half + 1 if odd

right_flags = flags_in_category[mid:]
              └─ Remaining flags

Example with 5 flags:
mid = (5 + 1) // 2 = 3
left_flags = [0, 1, 2]    (3 flags)
right_flags = [3, 4]      (2 flags)

Resulting Layout:
┌─────────────────┬─────────────────┐
│  Left (3)       │  Right (2)      │
├─────────────────┼─────────────────┤
│  Flag 1         │  Flag 4         │
│  Flag 2         │  Flag 5         │
│  Flag 3         │                 │
└─────────────────┴─────────────────┘
```

---

## 13. Complex Flag Exclusion

```
FlagState.complex_flags = {'starting_items', 'skip_items'}

In build_flag_checkboxes():
    for flag in FlagsEnum:
        if flag.value not in complex_flags:
            # Create checkbox for this flag
        else:
            # Skip - don't create checkbox
            # (handled separately in randomization logic)
```

---

## 14. Major Item Shuffle Master Toggle Logic

```
User toggles: Major Item Shuffle checkbox
    │
    └─> on_checkbox_changed('major_item_shuffle', False)
        │
        ├─ If flag_key == 'major_item_shuffle' AND value is False:
        │  │
        │  ├─ Define shuffle_flags list (13 flags):
        │  │  └─ [
        │  │    'shuffle_wood_sword_cave_item',
        │  │    'shuffle_white_sword_cave_item',
        │  │    'shuffle_magical_sword_cave_item',
        │  │    'shuffle_letter_cave_item',
        │  │    'shuffle_armos_item',
        │  │    'shuffle_coast_item',
        │  │    'shuffle_dungeon_hearts',
        │  │    'shuffle_shop_arrows',
        │  │    'shuffle_shop_candle',
        │  │    'shuffle_shop_ring',
        │  │    'shuffle_shop_book',
        │  │    'shuffle_shop_bait',
        │  │    'shuffle_potion_shop_items'
        │  │  ]
        │  │
        │  └─ For each shuffle_flag:
        │     ├─ flag_state.flags[shuffle_flag] = False
        │     └─ If checkbox exists:
        │        ├─ checkbox.value = False
        │        └─ checkbox.update()
        │
        └─ Always: update_flagstring()
```

