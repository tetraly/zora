# ZORA UI Structure - Quick Reference Guide

## Navigation Shortcuts

### Key Files
- **UI Entry Point**: `/home/user/zora/ui/main.py`
- **Component Builders**: `/home/user/zora/ui/components.py`
- **Event Handlers**: `/home/user/zora/ui/handlers.py`
- **State Management**: `/home/user/zora/ui/state.py`
- **Flag Definitions**: `/home/user/zora/logic/flags.py`

---

## Step 2 Panel - Component Breakdown

### Main Container
```python
# Location: components.py, lines 172-296
build_step2_container()
    → Returns: ft.Container with PURPLE_200 border
```

### Sections (in order)
1. **Input Section** (lines 284-285)
   - Flag String TextField
   - Seed TextField + Random Button

2. **Control Section** (lines 285)
   - Expand All Button (UNFOLD_MORE icon)
   - Collapse All Button (UNFOLD_LESS icon)

3. **Expansion Panel List** (lines 277-280, 286)
   - Type: `ft.ExpansionPanelList`
   - Contains 7-8 `ft.ExpansionPanel` children

4. **Action Section** (line 287)
   - Randomize Button (centered)

---

## Expandable Panels (Expansion Panels)

### Panel Creation
**Location**: `components.py`, lines 218-275

```python
# For each FlagCategory (except HIDDEN):
panel = ft.ExpansionPanel(
    header=ft.Container(
        content=ft.ListTile(
            title=ft.Text(category.display_name, weight="bold")
        ),
        border=ft.border.all(2, color)  # Category-specific color
    ),
    content=ft.Container(
        content=ft.Row([
            ft.Column(left_flags, spacing=3, expand=True),
            ft.Column(right_flags, spacing=3, expand=True)
        ])
    ),
    can_tap_header=True,
    expanded=True  # Start open
)
```

### Panel Colors
| Category | Color |
|----------|-------|
| ITEM_SHUFFLE | BLUE_600 |
| ITEM_CHANGES | PURPLE_600 |
| OVERWORLD_RANDOMIZATION | GREEN_600 |
| LOGIC_AND_DIFFICULTY | ORANGE_600 |
| QUALITY_OF_LIFE | CYAN_600 |
| EXPERIMENTAL | GREY_600 |
| LEGACY | GREY_600 |
| SHUFFLE_WITHIN_DUNGEONS | GREY_600 |

---

## Flag Components Structure

### Single Flag Row
```python
ft.Row([
    ft.Checkbox(
        label=flag.display_name,
        value=False,
        on_change=lambda e, key=flag.value: on_checkbox_changed(key, e.control.value)
    ),
    ft.IconButton(
        icon=ft.Icons.HELP_OUTLINE,
        icon_size=16,
        tooltip=flag.help_text,
        style=ft.ButtonStyle(padding=2)
    )
], spacing=0, tight=True)
```

### Flag Row Storage
- All checkboxes stored in: `handlers.flag_checkboxes` dict
- Organized by category in: `categorized_flag_rows` dict
- Created by: `build_flag_checkboxes()` (lines 357-401)

---

## State Management Classes

### FlagState (state.py)
```python
class FlagState:
    flags: dict                    # {flag_key: bool}
    complex_flags: set             # {'starting_items', 'skip_items'}
    seed: str
    
    # Key methods:
    to_flagstring() -> str         # Convert flags to 5-letter code
    from_flagstring(str) -> bool   # Parse flagstring to flags
    to_randomizer_flags() -> Flags
```

### RomInfo (state.py)
```python
class RomInfo:
    filename: str
    rom_type: str                  # 'vanilla' or 'randomized'
    flagstring: str
    seed: str
    code: str
```

### AppState (handlers.py)
```python
class AppState:
    rom_info: RomInfo
    flag_state: FlagState
    file_card: ft.Card
    step2_container: ft.Container
    expansion_panels_ref: list     # References for expand/collapse
    legacy_note_ref: list          # References for legacy warnings
    # ... 8 more properties
```

---

## Event Handlers - Key Functions

### Expand/Collapse (handlers.py, lines 887-897)
```python
def on_expand_all(self, e):
    for panel in self.expansion_panels_ref:
        panel.expanded = True
    self.page.update()

def on_collapse_all(self, e):
    for panel in self.expansion_panels_ref:
        panel.expanded = False
    self.page.update()
```

### Flag Change (handlers.py, lines 127-156)
```python
def on_checkbox_changed(self, flag_key: str, value: bool):
    self.state.flag_state.flags[flag_key] = value
    
    # Special logic for Major Item Shuffle master toggle
    if flag_key == 'major_item_shuffle' and not value:
        # Disable 13 related shuffle flags
    
    self.update_flagstring()
```

### Flag String Input (handlers.py, lines 119-125)
```python
def on_flagstring_changed(self, e):
    if self.state.flag_state.from_flagstring(self.flagstring_input.value):
        # Update checkbox UI to match parsed state
        for flag_key, checkbox in self.flag_checkboxes.items():
            checkbox.value = self.state.flag_state.flags.get(flag_key, False)
            checkbox.update()
```

### Legacy Flags (handlers.py, lines 181-214)
```python
def update_legacy_flags_state(self):
    is_vanilla = self.state.rom_info.rom_type == "vanilla"
    
    for flag in FlagsEnum:
        if flag.category == FlagCategory.LEGACY:
            if flag.value in self.flag_checkboxes:
                checkbox = self.flag_checkboxes[flag.value]
                checkbox.disabled = not is_vanilla
                # Update colors and values
```

---

## Flag Categories (9 Total)

| Enum Value | Display Name | Description |
|------------|---|---|
| ITEM_SHUFFLE (1) | Item Shuffle | Major/minor item randomization |
| ITEM_CHANGES (2) | Item Changes | Item behavior modifications |
| OVERWORLD_RANDOMIZATION (3) | Overworld Randomization | Overworld structure changes |
| LOGIC_AND_DIFFICULTY (4) | Logic & Difficulty | Logic and difficulty options |
| QUALITY_OF_LIFE (5) | Quality of Life / Other | QoL features |
| EXPERIMENTAL (6) | Experimental | Untested features (WARNING) |
| LEGACY (7) | Legacy Flags... | Vanilla ROM only |
| HIDDEN (8) | Hidden | Not shown in UI |
| SHUFFLE_WITHIN_DUNGEONS (9) | Shuffle Within Dungeons | Dungeon-specific shuffling |

---

## Flagstring Encoding (5-Letter Format)

### Letter Map
```python
LETTER_MAP = ['B', 'C', 'D', 'F', 'G', 'H', 'K', 'L']
# Index:        0    1    2    3    4    5    6    7 (octal values)
# No vowels to avoid confusion
```

### Encoding Process
1. Collect all non-complex flags in order
2. Convert flag boolean values to binary string (1 or 0)
3. Pad to multiple of 3
4. Group into 3-bit chunks
5. Convert each chunk to octal (0-7)
6. Map to letter: 0→B, 1→C, 2→D, 3→F, 4→G, 5→H, 6→K, 7→L
7. Combine: 5-letter flagstring

---

## Step 2 Container States

### Disabled (Initial)
```
disabled: True
opacity: 0.4  # Faded appearance
```

### Enabled (After ROM loaded)
```
disabled: False
opacity: 1.0  # Full visibility
```

### ROM Type-Specific Adjustments
```
If ROM type == "vanilla":
    Legacy flags: enabled
    Legacy warning note: hidden

If ROM type == "randomized":
    Legacy flags: disabled, greyed out
    Legacy warning note: visible
```

---

## Two-Column Flag Layout Algorithm

```python
mid = (len(flags_in_category) + 1) // 2  # Ceiling division
left_flags = flags_in_category[:mid]
right_flags = flags_in_category[mid:]

# Result: Two columns with left having 1 more if odd count
```

---

## Master Toggle: Major Item Shuffle

**When disabled, auto-disables:**
1. shuffle_wood_sword_cave_item
2. shuffle_white_sword_cave_item
3. shuffle_magical_sword_cave_item
4. shuffle_letter_cave_item
5. shuffle_armos_item
6. shuffle_coast_item
7. shuffle_dungeon_hearts
8. shuffle_shop_arrows
9. shuffle_shop_candle
10. shuffle_shop_ring
11. shuffle_shop_book
12. shuffle_shop_bait
13. shuffle_potion_shop_items

---

## Key Import Statements

```python
# components.py imports
from logic.flags import FlagsEnum, FlagCategory

# main.py imports
from ui.components import (
    build_rom_info_card, build_zora_settings_card,
    build_step1_container, build_step2_container,
    build_step3_container, build_flag_checkboxes,
    build_header
)
from ui.state import FlagState, RomInfo
from ui.handlers import AppState, EventHandlers
```

---

## Useful Constants

### Color Scheme
```python
PURPLE_200 = "#E1BEE7"    # Container borders
PURPLE_100 = "#F3E5F5"    # Panel divider
PURPLE_700 = "#7B1FA2"    # Panel expand icon
ORANGE_700 = "#D84315"    # Warnings
GREY_500   = "#9E9E9E"    # Disabled text
GREY_600   = "#616161"    # Default category color
```

### Flet Components Used
- `ft.Page` - Main page
- `ft.Column` - Vertical layout
- `ft.Row` - Horizontal layout
- `ft.Container` - General container
- `ft.Checkbox` - Boolean flag control
- `ft.TextField` - Text input (flagstring, seed)
- `ft.ElevatedButton` - Action buttons
- `ft.IconButton` - Help icons
- `ft.ExpansionPanel` - Collapsible panel
- `ft.ExpansionPanelList` - Container for panels
- `ft.Text` - Display text
- `ft.ListTile` - Panel header content
- `ft.Divider` - Visual separator
- `ft.Card` - Information card

---

## Testing/Debugging Tips

### Check Panel References
```python
# Verify expansion_panels_ref is populated
len(handlers.expansion_panels_ref)  # Should equal number of categories

# Verify legacy_note_ref is populated
len(handlers.legacy_note_ref)  # Should be 1 (for LEGACY category)
```

### Check Flag Checkboxes
```python
# Verify all flags have checkboxes
len(handlers.flag_checkboxes)  # Should be 50+ (excluding complex flags)

# Test flagstring parsing
handlers.state.flag_state.from_flagstring("BCDGH")  # Returns True if valid
```

### Monitor Flag State
```python
# Check individual flag state
handlers.state.flag_state.flags['major_item_shuffle']  # True or False

# Get current flagstring
handlers.state.flag_state.to_flagstring()  # Returns "BCDGH" format
```

---

## Common Modifications

### Add New Flag
1. Add to `FlagsEnum` in `/home/user/zora/logic/flags.py`
2. Include: value, display_name, help_text, category
3. Automatically included in checkboxes if not in complex_flags

### Change Panel Color
Edit `category_border_colors` dict in `components.py`, line 210-215

### Adjust Panel Spacing
Modify `spacing=3` in `ft.Column()` (line 232) for flags
Modify `spacing=10` in `ft.Row()` (line 234) for columns

### Change Initial Panel State
Edit `expanded=True` in `ft.ExpansionPanel()` (line 269)

---

## File Sizes
- main.py: 160 lines
- components.py: 463 lines
- handlers.py: 900+ lines
- state.py: 117 lines
- dialogs.py: 68 lines
- flags.py: 456 lines

**Total UI Code: ~2,200 lines**

