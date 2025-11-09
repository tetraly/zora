# ZORA UI Structure Documentation

This directory contains comprehensive documentation of the ZORA application's user interface architecture, with a focus on the Step 2 panel components, expandable panels, and flag system.

## Documentation Files

### 1. **quick_reference.md** - START HERE
   - Navigation shortcuts and file locations
   - Quick component breakdown
   - State management class definitions
   - Event handler function signatures
   - Flag categories and encoding
   - Common modifications guide
   
   **Best for**: Quick lookups, finding specific functions, understanding class definitions

### 2. **ui_structure_summary.md** - COMPREHENSIVE OVERVIEW
   - Overall UI architecture (3-step workflow)
   - File organization and responsibilities
   - Complete Step 2 panel structure
   - Expandable panel architecture and features
   - Flag component organization
   - Full component hierarchy
   - State management classes
   - Summary statistics
   
   **Best for**: Understanding the big picture, learning how components fit together

### 3. **ui_component_details.md** - DEEP DIVES
   - Detailed component function documentation
   - Expansion panel construction code
   - Flag checkbox structure and data flow
   - Color scheme reference
   - Reference list management patterns
   - Step 2 container CSS-like properties
   
   **Best for**: Understanding implementation details, code examples, styling properties

### 4. **ui_data_flow_diagrams.md** - ARCHITECTURE & FLOWS
   - Application initialization flow
   - Step 2 component construction flow
   - Flag checkbox creation flow
   - Flag state change and synchronization flow
   - Expand/Collapse button flow
   - Legacy flag visibility control flow
   - Expansion panel structure diagram
   - Two-column flag layout algorithm
   - Major Item Shuffle master toggle logic
   
   **Best for**: Understanding data flows, state synchronization, complex interactions

## Key Takeaways

### UI Architecture
- **Framework**: Flet (Python UI framework)
- **Architecture**: 3-step form-based workflow
- **Main Entry**: `/home/user/zora/ui/main.py`
- **Component Builders**: `/home/user/zora/ui/components.py`
- **Event Handlers**: `/home/user/zora/ui/handlers.py`
- **State Management**: `/home/user/zora/ui/state.py`
- **Flag Definitions**: `/home/user/zora/logic/flags.py`

### Step 2 Panel Structure
```
Step 2: Configure ZORA Flags and Seed Number
├─ Input Section (Flag String + Seed)
├─ Control Section (Expand All / Collapse All)
├─ Expansion Panel List (7-8 category panels)
│  └─ Each panel contains 2-column flag layout
└─ Action Section (Randomize Button)
```

### Expandable Panels (ExpansionPanelList)
- **Type**: `ft.ExpansionPanel` children in `ft.ExpansionPanelList`
- **Initial State**: All expanded by default
- **Header Colors**: Category-specific (Blue, Purple, Green, Orange, Cyan, Grey)
- **Content**: Two-column layout with flag checkboxes
- **Special**: LEGACY panel has warning note when randomized ROM loaded

### Flag Components
- **Checkbox + Help Icon** per flag
- **50+ flags** across 9 categories
- **2 complex flags** excluded (starting_items, skip_items)
- **Master toggle**: Major Item Shuffle controls 13 related flags
- **Special handling**: Legacy flags disabled for randomized ROMs

### State Synchronization
- **Bidirectional**: Flagstring ↔ Checkboxes
- **Encoding**: Binary flags → 3-bit chunks → octal → 5-letter string
- **Letter Map**: B,C,D,F,G,H,K,L (avoiding vowels)
- **Auto-update**: Flagstring updates when any checkbox changes

## Important Concepts

### Reference Lists
The application uses reference lists to manage UI component interactions:

1. **expansion_panels_ref**: List of all ExpansionPanel objects
   - Populated in `build_step2_container()`
   - Used by `on_expand_all()` and `on_collapse_all()`

2. **legacy_note_ref**: List containing LEGACY panel warning note
   - Populated in `build_step2_container()`
   - Used by `update_legacy_flags_state()`

3. **flag_checkboxes**: Dictionary of all flag checkboxes
   - Keys: flag.value (e.g., 'major_item_shuffle')
   - Values: ft.Checkbox objects
   - Used by multiple handlers for state synchronization

### State Classes

**FlagState**
- Manages flag states (50+ boolean flags)
- Handles flagstring encoding/decoding
- 5-letter format: B,C,D,F,G,H,K,L (octal based)

**RomInfo**
- Stores loaded ROM information
- Type: 'vanilla' or 'randomized' (affects legacy flag availability)

**AppState**
- Container for rom_info and flag_state
- Stores references to UI components
- Manages visibility of different sections

### Event Handlers

**Key handlers:**
- `on_checkbox_changed()` - Flag selection changes
- `on_flagstring_changed()` - Manual flagstring input
- `on_expand_all()` / `on_collapse_all()` - Panel expansion control
- `update_legacy_flags_state()` - ROM type-based flag availability
- `enable_step2()` / `disable_step2()` - Step 2 visibility

## File Sizes
```
ui/main.py          160 lines     (Application entry point)
ui/components.py    463 lines     (Component builders)
ui/handlers.py      900+ lines    (Event handlers)
ui/state.py         117 lines     (State management)
ui/dialogs.py        68 lines     (Dialog helpers)
logic/flags.py      456 lines     (Flag definitions)
────────────────────────────────
Total UI Code:    ~2,200 lines
```

## Color Palette

| Element | Color | Usage |
|---------|-------|-------|
| ITEM_SHUFFLE (panel) | BLUE_600 | Category header |
| ITEM_CHANGES (panel) | PURPLE_600 | Category header |
| OVERWORLD_RANDOMIZATION (panel) | GREEN_600 | Category header |
| LOGIC_AND_DIFFICULTY (panel) | ORANGE_600 | Category header |
| QUALITY_OF_LIFE (panel) | CYAN_600 | Category header |
| Container border | PURPLE_200 | Step 2 container edge |
| Panel divider | PURPLE_100 | Panel separation |
| Panel expand icon | PURPLE_700 | Expand/collapse icon |
| Warning text | ORANGE_700 | Legacy flag warning |
| Disabled text | GREY_500 | Greyed out text |
| Default category | GREY_600 | Experimental, etc |

## Quick Navigation

### By Task

**Add a new flag:**
1. Add to `FlagsEnum` in `logic/flags.py`
2. Include: value, display_name, help_text, category
3. Auto-included in UI (unless in complex_flags or HIDDEN)

**Change panel styling:**
1. Edit `category_border_colors` in `components.py` line 210-215
2. Modify `spacing` values in `ft.Column()` and `ft.Row()`
3. Change `expanded=True/False` for initial panel state

**Add event handler:**
1. Define in `EventHandlers` class in `handlers.py`
2. Pass as callback to component in `components.py`
3. Store component reference in handler if needed

**Debug UI state:**
```python
# Check panel references
len(handlers.expansion_panels_ref)
len(handlers.legacy_note_ref)

# Check flag state
handlers.state.flag_state.flags['flag_key']
handlers.state.flag_state.to_flagstring()

# Verify checkboxes
len(handlers.flag_checkboxes)
```

## Related Documentation

See also:
- `/home/user/zora/ui/` - UI implementation files
- `/home/user/zora/logic/flags.py` - Flag enum definitions
- `/home/user/zora/logic/randomizer.py` - Randomization logic

## Questions & Debugging

For issues related to:

- **UI Layout**: Check `ui_structure_summary.md` (Component Hierarchy)
- **Panel Expansion**: Check `ui_data_flow_diagrams.md` (Expand/Collapse Flow)
- **Flag State**: Check `ui_component_details.md` (Flag State Synchronization)
- **Function Signatures**: Check `quick_reference.md` (Event Handlers)
- **Color Scheme**: Check `ui_component_details.md` (Color Scheme)
- **Implementation Details**: Check `ui_component_details.md` (Component Details)

---

**Last Updated**: 2025-11-08
**Documentation Version**: 1.0
**ZORA Version**: RC7

