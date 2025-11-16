# ZORA UI Component Details

## Key Component Functions & Locations

### 1. Main Entry Point
**File**: `/home/user/zora/ui/main.py`

```python
def main(page: ft.Page, platform: str = "web") -> None:
    # Initializes the application
    # Creates state management
    # Builds all UI components
    # Sets up event handlers
```

---

## 2. Component Builders

### build_header() [lines 404-462]
Creates the application header with:
- ZORA logo (96x96 image)
- Title and version info
- Description and links
- Warning section
- Discord server button

**File**: `/home/user/zora/ui/components.py`

---

### build_step1_container() [lines 96-169]
Creates Step 1 UI with:
- ROM file selector
- Vanilla ROM option (Windows-only)
- Zelda Randomizer integration
- Flagstring and seed inputs

**File**: `/home/user/zora/ui/components.py`

---

### build_step2_container() [lines 172-296] **MAIN FOCUS**
Creates Step 2 with:
- Input fields for flagstring and seed
- Expand/Collapse All buttons
- **ExpansionPanelList with category panels**
- Randomize button

**Key parameters:**
- `categorized_flag_rows`: dict of FlagCategory -> flag rows
- `expansion_panels_ref`: list to store panel references
- `legacy_note_ref`: list to store legacy warning reference

**Structure breakdown:**
```
1. Input Section
   - Flag String Input (TextField)
   - Seed Input + Random Seed Button (Row)
   
2. Control Section
   - Expand All Button
   - Collapse All Button
   
3. Expansion Panel List
   - ExpansionPanelList container
   - 7-8 ExpansionPanel children (one per category)
   
4. Action Section
   - Randomize Button (centered)
```

**File**: `/home/user/zora/ui/components.py`

---

### build_step3_container() [lines 299-354]
Creates Step 3 UI with:
- Success message
- Output file information
- Download button
- "Randomize Another" button

**File**: `/home/user/zora/ui/components.py`

---

### build_flag_checkboxes() [lines 357-401]
Generates all flag checkboxes:
- Filters by category (skips HIDDEN)
- Excludes complex flags
- Creates checkbox + help icon rows
- Returns: (flag_checkboxes dict, categorized_flag_rows dict)

**Returns:**
```python
(
    {
        'major_item_shuffle': ft.Checkbox(...),
        'shuffle_wood_sword_cave_item': ft.Checkbox(...),
        ...
    },
    {
        FlagCategory.ITEM_SHUFFLE: [Row(...), Row(...), ...],
        FlagCategory.ITEM_CHANGES: [Row(...), ...],
        ...
    }
)
```

**File**: `/home/user/zora/ui/components.py`

---

## 3. Expansion Panel Construction Details

### ExpansionPanel Creation Loop [lines 218-275]

```python
expansion_panels = []
for category in FlagCategory:
    if category == FlagCategory.HIDDEN:
        continue  # Skip entirely
    
    if categorized_flag_rows[category]:  # Only if flags exist
        
        # Get flags for this category
        flags_in_category = categorized_flag_rows[category]
        
        # Split into two columns
        mid = (len(flags_in_category) + 1) // 2
        left_flags = flags_in_category[:mid]
        right_flags = flags_in_category[mid:]
        
        # Create two-column layout
        flag_content = ft.Row([
            ft.Column(left_flags, spacing=3, expand=True),
            ft.Column(right_flags, spacing=3, expand=True)
        ], spacing=10)
        
        # Add legacy warning if applicable
        if category == FlagCategory.LEGACY:
            legacy_note = ft.Container(
                content=ft.Text(
                    "⚠️ Legacy flags are only available for use with vanilla ROMs.",
                    color=ft.Colors.ORANGE_700,
                    size=12,
                    weight="bold"
                ),
                padding=ft.padding.only(bottom=10),
                visible=False  # Hidden initially
            )
            category_content = ft.Column([legacy_note, flag_content], spacing=5)
            
            if legacy_note_ref is not None:
                legacy_note_ref.append(legacy_note)  # Store for later
        else:
            category_content = flag_content
        
        # Create colored header
        header = ft.Container(
            content=ft.ListTile(
                title=ft.Text(category.display_name, weight="bold"),
                dense=True,
                content_padding=ft.padding.symmetric(horizontal=10, vertical=2)
            ),
            border=ft.border.all(2, category_border_colors.get(category, ft.Colors.GREY_600)),
            border_radius=5,
            padding=0
        )
        
        # Create expansion panel
        panel = ft.ExpansionPanel(
            header=header,
            content=ft.Container(
                content=category_content,
                padding=ft.padding.only(left=5, right=5, top=5, bottom=2)
            ),
            can_tap_header=True,
            expanded=True  # Start open
        )
        
        expansion_panels.append(panel)
        
        # Store reference for expand/collapse all
        if expansion_panels_ref is not None:
            expansion_panels_ref.append(panel)

# Create the final list
expansion_panel_list = ft.ExpansionPanelList(
    controls=expansion_panels,
    elevation=2,
    divider_color=ft.Colors.PURPLE_100,
    expand_icon_color=ft.Colors.PURPLE_700
)
```

---

## 4. Flag Checkbox Structure Details

### Single Flag Row Structure

Each flag is represented as:

```
ft.Row([
    ft.Checkbox(
        label="Flag Display Name",
        value=False,
        on_change=lambda e, key='flag_key': on_change_callback(key, e.control.value)
    ),
    ft.IconButton(
        icon=ft.Icons.HELP_OUTLINE,
        icon_size=16,
        tooltip="Detailed help text for this flag...",
        style=ft.ButtonStyle(padding=2)
    )
], spacing=0, tight=True)
```

### Data Flow for Flag Changes

```
User clicks checkbox
         ↓
on_change event triggered
         ↓
lambda calls on_change_callback(flag_key, bool_value)
         ↓
EventHandlers.on_checkbox_changed(flag_key, value)
         ↓
FlagState.flags[flag_key] = value
         ↓
Special logic check (e.g., Major Item Shuffle master toggle)
         ↓
Update related checkboxes if needed
         ↓
Call update_flagstring() to sync display
         ↓
FlagState.to_flagstring() converts dict to 5-letter string
         ↓
UI updates: flagstring_input.value = "BCDLF" (example)
```

---

## 5. Expand/Collapse Implementation

### Handler Functions [lines 887-897]

```python
def on_expand_all(self, e) -> None:
    """Expand all flag category panels."""
    for panel in self.expansion_panels_ref:
        panel.expanded = True
    self.page.update()

def on_collapse_all(self, e) -> None:
    """Collapse all flag category panels."""
    for panel in self.expansion_panels_ref:
        panel.expanded = False
    self.page.update()
```

### Usage
- Buttons created in Step 2 with these handlers
- Buttons have icons: UNFOLD_MORE (expand), UNFOLD_LESS (collapse)
- Height set to 35px for consistency

---

## 6. Legacy Flag Special Handling

### Visibility Control

```python
def update_legacy_flags_state(self) -> None:
    """Enable/disable LEGACY flags based on ROM type."""
    is_vanilla = self.state.rom_info.rom_type == "vanilla"
    
    for flag in FlagsEnum:
        if flag.category == FlagCategory.LEGACY:
            if flag.value in self.flag_checkboxes:
                checkbox = self.flag_checkboxes[flag.value]
                checkbox.disabled = not is_vanilla
                
                if not is_vanilla:
                    # Grey out when disabled
                    checkbox.label_style = ft.TextStyle(color=ft.Colors.GREY_500)
                    checkbox.value = False
                    self.state.flag_state.flags[flag.value] = False
                else:
                    # Restore when enabled
                    checkbox.label_style = None
                
                checkbox.update()
    
    # Update legacy warning note
    if self.legacy_note_ref:
        for legacy_note in self.legacy_note_ref:
            legacy_note.visible = not is_vanilla
            legacy_note.update()
```

---

## 7. Color Scheme

### Category Colors
```python
category_border_colors = {
    FlagCategory.ITEM_SHUFFLE: "#1976D2" (BLUE_600),
    FlagCategory.ITEM_CHANGES: "#7B1FA2" (PURPLE_600),
    FlagCategory.OVERWORLD_RANDOMIZATION: "#388E3C" (GREEN_600),
    FlagCategory.LOGIC_AND_DIFFICULTY: "#D84315" (ORANGE_600),
    FlagCategory.QUALITY_OF_LIFE: "#00838F" (CYAN_600),
    FlagCategory.EXPERIMENTAL: "#616161" (GREY_600 - default),
    FlagCategory.LEGACY: "#616161" (GREY_600 - default),
    FlagCategory.HIDDEN: N/A (not displayed),
    FlagCategory.SHUFFLE_WITHIN_DUNGEONS: "#616161" (GREY_600 - default)
}
```

### UI Element Colors
- Container borders: PURPLE_200
- Text warnings: ORANGE_700
- Success messages: GREEN
- Disabled state: GREY_500
- Error messages: RED_800
- Divider: PURPLE_100
- Panel expand icon: PURPLE_700

---

## 8. State Synchronization

### Flagstring Encoding/Decoding

**Encoding** (Flag state -> 5-letter string):
```
Flags: [major=1, wood=1, white=0, magical=1, ...]
Binary: 1101...
Grouped: 110 1... (3 bits per letter)
Octal values: 6, 4, ... (0-7)
Letter map: B=0, C=1, D=2, F=3, G=4, H=5, K=6, L=7 (avoiding vowels)
Result: "KFDLC" (example)
```

**Decoding** (5-letter string -> Flag state):
```
Input: "KFDLC"
Letters to octal: K=6, F=3, D=2, L=7, C=1
Octal to binary: 110 011 010 111 001
Apply to flags: [1=True, 1=True, 0=False, 0=False, 1=True, ...]
```

---

## 9. Step 2 Container CSS-like Properties

```
Step 2 Container
├─ Border: 2px solid #E1BEE7 (PURPLE_200)
├─ Border Radius: 10px
├─ Padding: 15px
├─ Margin: 10px
├─ Background: default (light)
├─ Elevation: N/A (container doesn't have elevation)
└─ When Disabled:
   ├─ disabled: True
   └─ opacity: 0.4 (faded)
```

---

## 10. Reference Lists Management

### expansion_panels_ref Usage
```python
# In EventHandlers.__init__()
self.expansion_panels_ref = []

# In build_step2_container()
if expansion_panels_ref is not None:
    expansion_panels_ref.append(panel)  # Called for each category

# In main.py
expansion_panels_ref = handlers.expansion_panels_ref
step2_container = build_step2_container(
    ...,
    expansion_panels_ref=expansion_panels_ref,  # Passed in
    ...
)

# In handlers
def on_expand_all(self, e):
    for panel in self.expansion_panels_ref:
        panel.expanded = True
```

### legacy_note_ref Usage
```python
# Similar pattern for legacy warning notes
self.legacy_note_ref = []

# In build_step2_container()
if legacy_note_ref is not None:
    legacy_note_ref.append(legacy_note)

# In main.py
step2_container = build_step2_container(
    ...,
    legacy_note_ref=handlers.legacy_note_ref,
    ...
)

# In handlers
def update_legacy_flags_state(self):
    if self.legacy_note_ref:
        for legacy_note in self.legacy_note_ref:
            legacy_note.visible = not is_vanilla
```

---

## File Size Summary

```
/home/user/zora/ui/main.py          160 lines
/home/user/zora/ui/components.py    463 lines
/home/user/zora/ui/handlers.py      900+ lines
/home/user/zora/ui/state.py         117 lines
/home/user/zora/ui/dialogs.py        68 lines
/home/user/zora/logic/flags.py      456 lines
────────────────────────────────────────
Total UI-related code:              ~2,200 lines
```

