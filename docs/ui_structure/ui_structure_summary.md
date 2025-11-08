# ZORA UI Structure Overview

## Project Type
- **Framework**: Flet (Python UI framework)
- **Language**: Python 3
- **Architecture**: Multi-step form-based application

## Overall UI Architecture

The ZORA application uses a **3-step workflow** architecture, implemented as a series of container sections that appear sequentially:

```
┌─────────────────────────────────────────┐
│  Header (Logo + Title + Info)           │
├─────────────────────────────────────────┤
│  Step 1: Select Base ROM                │
│  (File pickers and ROM generation)      │
├─────────────────────────────────────────┤
│  Step 2: Configure ZORA Flags           │
│  (Expandable flag panels)               │
├─────────────────────────────────────────┤
│  Step 3: Download Randomized ROM        │
│  (Results and download options)         │
└─────────────────────────────────────────┘
```

**Main Entry Point**: `/home/user/zora/ui/main.py`
- `main(page: ft.Page, platform: str)` function initializes the application
- Page properties: 1000px width, 900px height (desktop), auto-scrolling

---

## File Organization

### Core UI Files
- **`/home/user/zora/ui/components.py`** (463 lines)
  - Component builders for all UI sections
  - Flag checkbox generation
  - Panel layout construction

- **`/home/user/zora/ui/main.py`** (160 lines)
  - Application initialization
  - Component orchestration
  - State and handler setup

- **`/home/user/zora/ui/handlers.py`** (900+ lines)
  - Event handler implementations
  - Flag state synchronization
  - ROM loading and processing

- **`/home/user/zora/ui/state.py`** (117 lines)
  - `FlagState` class - flag management
  - `RomInfo` class - ROM information storage
  - Flagstring encoding/decoding (LETTER_MAP: B,C,D,F,G,H,K,L)

- **`/home/user/zora/ui/dialogs.py`** (68 lines)
  - `info_row()` - aligned label-value pairs
  - `show_error_dialog()` - error notifications
  - `show_snackbar()` - toast notifications

### Flag Definitions
- **`/home/user/zora/logic/flags.py`**
  - `FlagCategory` enum - 9 categories (IntEnum)
  - `FlagsEnum` - 50+ individual flags with metadata
  - `Flags` class - runtime flag management

---

## Step 2 Panel Components

### Step 2 Container Structure
**Function**: `build_step2_container()` in `components.py` (lines 172-296)

```
Step 2: Configure ZORA Flags and Seed Number
├─ Flag String & Seed Row
│  ├─ ZORA Flag String Input (TextField)
│  └─ ZORA Seed Number Input (TextField + Random Seed Button)
├─ Divider
├─ Expand/Collapse Button Row
│  ├─ "Expand All" Button (icon: UNFOLD_MORE)
│  └─ "Collapse All" Button (icon: UNFOLD_LESS)
├─ Expansion Panel List (ExpansionPanelList)
│  └─ [Category Panels - see below]
└─ Randomize Button (centered)
```

### Properties
- **Border**: 2px PURPLE_200
- **Padding**: 15px
- **Margin**: 10px
- **Default State**: Disabled (opacity 0.4) until ROM loaded
- **Enabled on**: ROM file selection (both vanilla and randomized)

---

## Expandable Panels (ExpansionPanelList)

### Panel Architecture
**Location**: `build_step2_container()` lines 218-280

Each expandable panel represents a **FlagCategory**:

```
┌─────────────────────────────────────────────────┐
│ ► Item Shuffle                        [Expand ∨] │  <- Header (colored border)
├─────────────────────────────────────────────────┤
│  □ Enable Major Item Shuffle        [?]        │
│  □ Shuffle Wood Sword Cave item     [?]        │  <- Left Column
│  □ Shuffle White Sword Cave item    [?]        │
│  □ ...                                          │
│  │                                              │
│  □ Shuffle Shop Arrows              [?]        │
│  □ Shuffle Shop Candle              [?]        │  <- Right Column
│  □ Shuffle Shop Ring                [?]        │
│  □ ...                                          │
└─────────────────────────────────────────────────┘
```

### Panel Features
- **Type**: `ft.ExpansionPanel`
- **Container**: `ft.ExpansionPanelList`
- **Initial State**: `expanded=True` (all panels open by default)
- **Tapable Header**: `can_tap_header=True`
- **Styling**:
  - Elevation: 2
  - Divider Color: PURPLE_100
  - Expand Icon Color: PURPLE_700

### Category Border Colors (Expandable Panel Headers)
```python
category_border_colors = {
    FlagCategory.ITEM_SHUFFLE: BLUE_600,
    FlagCategory.ITEM_CHANGES: PURPLE_600,
    FlagCategory.OVERWORLD_RANDOMIZATION: GREEN_600,
    FlagCategory.LOGIC_AND_DIFFICULTY: ORANGE_600,
    FlagCategory.QUALITY_OF_LIFE: CYAN_600,
    FlagCategory.EXPERIMENTAL: (default GREY_600),
    FlagCategory.LEGACY: (default GREY_600)
}
```

### Panel Content Layout
**Two-Column Layout**:
```python
mid = (len(flags_in_category) + 1) // 2
left_flags = flags_in_category[:mid]
right_flags = flags_in_category[mid:]

flag_content = ft.Row([
    ft.Column(left_flags, spacing=3, expand=True),
    ft.Column(right_flags, spacing=3, expand=True)
], spacing=10)
```

### Special Content: Legacy Panel
- Has a **warning note** prepended: "⚠️ Legacy flags are only available for use with vanilla ROMs."
- Warning visibility controlled by ROM type
- Reference stored in `legacy_note_ref` list
- Shown only when randomized ROM is loaded

### Panel References Storage
- Panels stored in `expansion_panels_ref` list (line 275)
- Allows expand/collapse all functionality
- Referenced in handlers: `self.expansion_panels_ref`

---

## Flag Components (Within Panels)

### Flag Checkbox Structure
**Function**: `build_flag_checkboxes()` in `components.py` (lines 357-401)

Each flag in a panel follows this pattern:

```
┌────────────────────────────────────┐
│ □ Flag Display Name         [?]    │  <- Flag Row
│                                    │
└────────────────────────────────────┘
```

### Flag Row Components
- **Checkbox** (`ft.Checkbox`)
  - Label: `flag.display_name`
  - Value: Boolean state
  - Change handler: `on_checkbox_changed(flag_key, value)`
  - Stored in: `flag_checkboxes` dict (keyed by `flag.value`)

- **Help Icon** (`ft.IconButton`)
  - Icon: HELP_OUTLINE
  - Icon Size: 16px
  - Tooltip: `flag.help_text`
  - Button padding: 2px
  - Spacing: 0 (tight layout)
  - Tight Row: `tight=True`

### Flag Metadata (from FlagsEnum)
Each flag has:
- `value`: Internal key (e.g., 'major_item_shuffle')
- `display_name`: UI display text
- `help_text`: Tooltip description
- `category`: FlagCategory enum
- Hidden flags excluded from checkboxes

### Flag State Management
- **Complex Flags** (excluded from checkboxes):
  - `'starting_items'`
  - `'skip_items'`
- **Regular Flags**: Displayed as checkboxes
- **Total Flags**: 50+ in FlagsEnum

### Special Flag Logic
- **Major Item Shuffle Master Toggle**:
  - When disabled, automatically disables 13 related shuffle flags
  - Handler: `on_checkbox_changed()` in handlers.py (lines 127-156)
  - Affects flags: wood_sword, white_sword, magical_sword, letter, armos, coast, dungeon_hearts, shop_arrows, shop_candle, shop_ring, shop_book, shop_bait, potion_shop_items

- **Legacy Flags**:
  - Only available with vanilla ROMs
  - Disabled when randomized ROM loaded
  - Text greyed out (GREY_500) when disabled
  - Stored with `legacy_note_ref`

---

## FlagCategory Enum Reference

```python
class FlagCategory(IntEnum):
    ITEM_SHUFFLE = 1                      # Major/minor item randomization
    ITEM_CHANGES = 2                      # Item behavior modifications
    OVERWORLD_RANDOMIZATION = 3           # Overworld structure changes
    LOGIC_AND_DIFFICULTY = 4              # Logic and difficulty options
    QUALITY_OF_LIFE = 5                   # QoL features
    EXPERIMENTAL = 6                      # Untested features (WARNING)
    LEGACY = 7                            # Legacy flags (vanilla ROMs only)
    HIDDEN = 8                            # Not shown in UI
    SHUFFLE_WITHIN_DUNGEONS = 9           # Dungeon-specific shuffling
```

---

## UI Component Hierarchy

### Full Hierarchy
```
Page (ft.Page)
├─ Header Container
│  ├─ ZORA Logo (Image)
│  ├─ Title Column
│  │  ├─ Title Text
│  │  ├─ Description Text
│  │  └─ Warning Section
│  │     └─ Discord Button
│  └─ Divider
├─ Main Content Column
│  ├─ Step 1 Container (initially visible)
│  │  ├─ ROM Select Panel
│  │  │  ├─ Instructions Text
│  │  │  ├─ Info Note
│  │  │  └─ "Choose ROM" Button
│  │  └─ Generate Panel (Windows-only)
│  │     ├─ Flagstring Input
│  │     ├─ Seed Input
│  │     ├─ Random Seed Button
│  │     └─ "Generate ROM" Button
│  │
│  ├─ ROM Info Card (appears after ROM loaded)
│  │  ├─ ROM Type
│  │  ├─ Filename
│  │  ├─ ZR Flag String
│  │  ├─ ZR Seed
│  │  └─ ZR Code
│  │
│  ├─ Step 2 Container (initially disabled)
│  │  ├─ Title Text
│  │  ├─ Flag String & Seed Row
│  │  │  ├─ Flag String Input
│  │  │  └─ Seed Input + Random Button
│  │  ├─ Divider
│  │  ├─ Expand/Collapse Buttons
│  │  │  ├─ "Expand All"
│  │  │  └─ "Collapse All"
│  │  ├─ ExpansionPanelList
│  │  │  ├─ Item Shuffle Panel
│  │  │  │  ├─ Panel Header (colored)
│  │  │  │  └─ Two-Column Flag Layout
│  │  │  │     ├─ Left Column: Checkboxes
│  │  │  │     └─ Right Column: Checkboxes
│  │  │  ├─ Item Changes Panel
│  │  │  ├─ Overworld Randomization Panel
│  │  │  ├─ Logic & Difficulty Panel
│  │  │  ├─ Quality of Life Panel
│  │  │  ├─ Experimental Panel
│  │  │  └─ Legacy Panel (with warning note)
│  │  └─ "Randomize" Button (centered)
│  │
│  └─ Step 3 Container (appears after randomization)
│     ├─ Title Text
│     ├─ Success Icon & Message
│     ├─ Output File Info
│     ├─ ZORA Flag String Info
│     ├─ ZORA Seed Info
│     ├─ ZORA Code Info
│     ├─ ROM Size Info
│     ├─ Generation Time Info (optional)
│     └─ Action Buttons
│        ├─ "Download Randomized ROM"
│        └─ "Randomize Another Game"
│
└─ File Pickers (overlay)
   ├─ ROM File Picker
   └─ Generate Vanilla File Picker
```

---

## State Management

### AppState Class
```python
class AppState:
    rom_info: RomInfo              # Loaded ROM information
    flag_state: FlagState          # Current flag selections
    file_card: ft.Card             # ROM info card reference
    vanilla_rom_path: str          # Path to vanilla ROM for generation
    randomized_rom_data: bytes     # Generated ROM binary
    randomized_rom_filename: str   # Output filename
    step3_container: ft.Container  # Step 3 UI reference
    zora_settings_card: ft.Card    # Settings display card
    known_issues_page: ft.Container # Known issues page reference
    main_content: ft.Column        # Main UI column reference
```

### FlagState Class
```python
class FlagState:
    flags: dict                    # {flag_key: bool}
    complex_flags: set             # {'starting_items', 'skip_items'}
    seed: str                      # Random seed value
    
    Methods:
    - to_flagstring() -> str       # Convert flags to 5-letter string
    - from_flagstring(str) -> bool # Parse flagstring
    - to_randomizer_flags() -> Flags
```

### RomInfo Class
```python
class RomInfo:
    filename: str
    rom_type: str                  # 'vanilla' or 'randomized'
    flagstring: str
    seed: str
    code: str
```

---

## Event Handlers

### Expand/Collapse Handlers
```python
def on_expand_all(self, e):
    """Expand all expansion panels."""
    for panel in self.expansion_panels_ref:
        panel.expanded = True
    self.page.update()

def on_collapse_all(self, e):
    """Collapse all expansion panels."""
    for panel in self.expansion_panels_ref:
        panel.expanded = False
    self.page.update()
```

### Flag Handlers
- `on_checkbox_changed(flag_key, value)` - updates flag state and flagstring
- `on_flagstring_changed(e)` - parses flagstring input
- `update_flagstring()` - synchronizes flagstring display

### Step 2 Visibility
- `enable_step2()` - sets disabled=False, opacity=1.0
- `disable_step2()` - sets disabled=True, opacity=0.4

### Legacy Flag Logic
- `update_legacy_flags_state()` - manages legacy flag visibility based on ROM type

---

## Key UI Patterns

### Two-Column Layout
Used throughout for space efficiency:
- Flag checkboxes in panels (left/right columns)
- Input fields (flag string + seed)

### Color Coding
- Category headers have distinctive colors
- Error messages in RED_800
- Warning messages in ORANGE_700
- Success states in GREEN
- Disabled elements: opacity 0.4, GREY_500 text

### Accessibility
- Help icons with tooltips on all flags
- Input validation with error dialogs
- Snackbar notifications for feedback
- High contrast colors for readability

### Responsive Design
- Wrap=True on rows for mobile
- Tight spacing on related controls
- Expandable/collapsible sections
- Auto-scrolling page

---

## Summary Statistics

- **Total UI Components**: 200+
- **Flag Categories**: 9
- **Total Flags**: 50+
- **Expansion Panels**: 7-8 (based on flag availability)
- **Custom Colors**: 8 (per category)
- **Input Fields**: 6 (Step 1 & 2)
- **Buttons**: 15+
- **Lines of Code**: ~1,500 (UI-related)

