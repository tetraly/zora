# ZORA Beta 1.1 Comprehensive Testing Plan

**Version:** 1.1 BETA 2
**Date:** November 17, 2025
**Branch:** beta-1.1
**Status:** Ready for Beta Testing

---

## Executive Summary

This testing plan covers the comprehensive validation of ZORA (Zelda One Randomizer Add-ons) version 1.1 Beta 2. This release includes significant new features:

- **Major Item Randomizer** - Inter-dungeon item shuffle (13 new shuffle flags, 8 constraint flags)
- **Three Solver Implementations** - Interchangeable constraint solvers with different performance profiles
- **Complete UI Redesign** - Tab-based interface replacing accordion panels
- **CLI Tool** - New command-line interface for headless operation
- **Health System Overhaul** - 4 configurable respawn modes
- **Start Screen Randomizer** - Randomized spawn locations
- **Enhanced Validation & Hints** - Improved seed validation and hint generation

**Key Statistics:**
- 74 files changed (11,108 insertions, 473 deletions)
- 47+ commits with new features and bug fixes
- 15 new/updated test files (2,500+ lines of test code)
- 50+ configuration flags

---

## Table of Contents

1. [Test Environment Setup](#test-environment-setup)
2. [Testing Strategy](#testing-strategy)
3. [Critical Test Cases](#critical-test-cases)
4. [Test Scenarios](#test-scenarios)
5. [Regression Testing](#regression-testing)
6. [Performance Testing](#performance-testing)
7. [User Acceptance Testing](#user-acceptance-testing)
8. [Test Schedule](#test-schedule)
9. [Risk Assessment](#risk-assessment)
10. [Bug Reporting Process](#bug-reporting-process)
11. [Acceptance Criteria](#acceptance-criteria)

---

## Test Environment Setup

### Prerequisites

**Hardware Requirements:**
- OS: Windows, macOS, or Linux
- RAM: 4GB minimum
- Storage: 500MB free space

**Software Requirements:**
- Python 3.8+
- Vanilla Zelda 1 ROM (for testing)
- Dependencies from `requirements.txt`

**Setup Steps:**
```bash
# 1. Clone and checkout beta-1.1
git fetch origin beta-1.1
git checkout beta-1.1

# 2. Install dependencies
pip install -r requirements.txt

# 3. Verify test ROM is available
# Place vanilla Zelda 1 ROM in test location

# 4. Run quick validation
python -m pytest tests/test_determinism_quick.py -v
```

**Test Data:**
- Vanilla ROM: Required for all tests
- Test data files: `tests/data/*.bin` (extracted via `extract_test_data.py`)
- Sample flagstrings: Documented in test cases

---

## Testing Strategy

### Test Pyramid

```
        ┌─────────────────┐
        │   Manual UAT    │ ← User Acceptance (10%)
        │    (20 tests)   │
        ├─────────────────┤
        │  Integration    │ ← System/Integration (30%)
        │   (60 tests)    │
        ├─────────────────┤
        │   Unit Tests    │ ← Automated Unit Tests (60%)
        │  (150+ tests)   │
        └─────────────────┘
```

### Testing Phases

**Phase 1: Automated Testing (Week 1)**
- Run existing test suite
- Execute unit tests for new features
- Validate determinism and solver correctness

**Phase 2: Feature Testing (Week 2)**
- Test major item randomizer extensively
- Validate UI functionality
- Test CLI tool
- Health system validation

**Phase 3: Integration Testing (Week 3)**
- Cross-feature interaction tests
- Flagstring combinations
- ROM generation end-to-end

**Phase 4: User Acceptance Testing (Week 4)**
- Beta tester feedback
- Playthrough testing
- Edge case discovery
- Performance validation

---

## Critical Test Cases

### Priority Legend
- 🔴 **CRITICAL** - Blocking issues, must pass before release
- 🟡 **HIGH** - Important features, should pass before release
- 🟢 **MEDIUM** - Nice-to-have, can be addressed in patch
- 🔵 **LOW** - Minor issues, cosmetic or documentation

---

### 🔴 CRITICAL Test Cases

#### TC-001: Seed Determinism
**Priority:** 🔴 CRITICAL
**Feature:** Core Randomization
**Description:** Verify identical seed+flags produces identical ROM

**Test Steps:**
1. Generate ROM with seed=12345, flags="AS"
2. Note output ROM hash/size
3. Repeat generation 10 times with same seed+flags
4. Binary compare all generated ROMs

**Expected Result:** All 10 ROMs are byte-identical

**Automated:** Yes - `tests/test_determinism_comprehensive.py`

**Validation Command:**
```bash
python -m pytest tests/test_determinism_comprehensive.py::test_determinism_with_major_item_shuffle -v
```

---

#### TC-002: Major Item Randomizer - Basic Functionality
**Priority:** 🔴 CRITICAL
**Feature:** Major Item Randomizer
**Description:** Verify major items shuffle correctly

**Test Steps:**
1. Enable `major_item_shuffle` flag
2. Generate seed with flags="AS"
3. Parse generated ROM
4. Verify items shuffled from original positions
5. Verify all major items present in ROM

**Expected Result:**
- Items moved from vanilla locations
- All 12+ major items accounted for
- No duplicate/missing items

**Automated:** Yes - `tests/test_major_item_randomizer.py`

**Validation Command:**
```bash
python -m pytest tests/test_major_item_randomizer.py::test_basic_major_item_shuffle -v
```

---

#### TC-003: Beatable Seed Validation
**Priority:** 🔴 CRITICAL
**Feature:** Validator
**Description:** Verify validator correctly identifies beatable seeds

**Test Steps:**
1. Generate 20 seeds with major item shuffle
2. Run validator on each seed
3. Verify validator passes all seeds
4. Check validator logs for unreachable items

**Expected Result:**
- All seeds marked as valid
- No unreachable required items
- Validator logs show all checks passed

**Automated:** Partial - `tests/test_major_item_randomizer.py`

**Manual Verification:** Review validator output logs

---

#### TC-004: UI Flag Synchronization
**Priority:** 🔴 CRITICAL
**Feature:** UI
**Description:** Verify checkbox state syncs with flagstring

**Test Steps:**
1. Launch UI
2. Check "Major Item Shuffle" checkbox
3. Verify flagstring updates to include "A"
4. Manually edit flagstring to add "S" (shuffle_wood_sword)
5. Verify "Shuffle Wood Sword Cave Item" checkbox becomes checked

**Expected Result:**
- Checkbox changes update flagstring
- Flagstring edits update checkboxes
- No desynchronization

**Automated:** No - Manual UI test

---

#### TC-005: Master Toggle Behavior
**Priority:** 🔴 CRITICAL
**Feature:** UI/Flags
**Description:** Verify master toggle enables/disables dependent flags

**Test Steps:**
1. Launch UI
2. Navigate to Item Shuffle tab
3. Uncheck "Major Item Shuffle" master toggle
4. Verify all 13 dependent shuffle flags become disabled
5. Check "Major Item Shuffle" master toggle
6. Verify all 13 dependent flags become enabled

**Expected Result:**
- Master toggle controls all dependent flags
- Disabled flags cannot be checked
- Flagstring updates correctly

**Automated:** No - Manual UI test

---

#### TC-006: Progressive Item Chains
**Priority:** 🔴 CRITICAL
**Feature:** Item Logic
**Description:** Verify progressive items upgrade correctly

**Test Steps:**
1. Generate seed with Wood Sword → White Sword → Magical Sword progression
2. Collect Wood Sword
3. Verify inventory shows Wood Sword
4. Collect White Sword
5. Verify inventory upgrades to White Sword (Wood Sword removed)
6. Collect Magical Sword
7. Verify inventory upgrades to Magical Sword

**Expected Result:**
- Progressive upgrades work correctly
- No duplicate items in inventory
- Item effects apply correctly

**Automated:** Partial - logic tests exist

**Manual Verification:** Playthrough testing required

---

#### TC-007: Health System - All Modes
**Priority:** 🔴 CRITICAL
**Feature:** Health Patches
**Description:** Verify all 4 health respawn modes work correctly

**Test Modes:**
1. **Mode 1:** Neither flag enabled → Respawn with 3 hearts (vanilla)
2. **Mode 2:** `keep_health_after_death_warp` only → Keep current if ≥3, else 3
3. **Mode 3:** `increase_minimum_health` only → Reset to max(3, maxHearts/2)
4. **Mode 4:** Both flags → Keep max(current, 3, maxHearts/2)

**Test Steps for Each Mode:**
1. Generate ROM with specific health flags
2. Play until max health = 10 hearts
3. Take damage to 2 hearts
4. Die or use death warp
5. Verify respawn health matches expected mode

**Expected Results:**
- Mode 1: 3 hearts
- Mode 2: 3 hearts (current < 3)
- Mode 3: 5 hearts (10/2 = 5)
- Mode 4: 5 hearts (max of 2, 3, 5)

**Automated:** No - Requires emulator testing

---

#### TC-008: CLI Tool Basic Operation
**Priority:** 🔴 CRITICAL
**Feature:** CLI
**Description:** Verify CLI generates ROMs correctly

**Test Steps:**
1. Run CLI command:
   ```bash
   python -m cli.cli --seed 12345 --flagstring "AS" --input-file vanilla.nes --output-dir ./output
   ```
2. Verify ROM generated in output directory
3. Verify filename follows convention
4. Compare ROM to UI-generated ROM with same seed/flags

**Expected Result:**
- ROM generated successfully
- Output filename correct
- CLI ROM matches UI ROM (binary identical)

**Automated:** Partial - can script CLI calls

**Validation Command:**
```bash
python -m cli.cli --seed 99999 --flagstring "AS" --input-file path/to/vanilla.nes --output-dir ./test_output --loglevel DEBUG
```

---

### 🟡 HIGH Priority Test Cases

#### TC-009: Solver Constraint Conflicts
**Priority:** 🟡 HIGH
**Feature:** Solvers
**Description:** Verify solver detects impossible constraint combinations

**Test Steps:**
1. Enable `force_arrow_to_level_nine`
2. Enable `force_ring_to_level_nine`
3. Enable `force_wand_to_level_nine`
4. Enable `force_two_heart_containers_to_level_nine`
5. Attempt to generate seed
6. Verify solver fails gracefully with clear error

**Expected Result:**
- Solver detects impossible constraints (too many items forced to one location)
- Clear error message explaining conflict
- No crash or hang

**Automated:** Should be - add to test suite

---

#### TC-010: Start Screen Randomization
**Priority:** 🟡 HIGH
**Feature:** Overworld Randomizer
**Description:** Verify start screen randomization works

**Test Steps:**
1. Enable `shuffle_start_screen` flag
2. Generate 10 seeds
3. Verify Link spawns in different screens
4. Verify new spawn location has no enemies
5. Verify enemy data swapped correctly

**Expected Result:**
- Link spawns in randomized safe locations
- No enemies in starting screen
- Original starting screen now has enemies (from new start)

**Automated:** No - Requires ROM inspection/emulator

---

#### TC-011: All Shuffle Flags Individually
**Priority:** 🟡 HIGH
**Feature:** Item Shuffle
**Description:** Test each of the 13 shuffle flags independently

**Flags to Test:**
1. `shuffle_wood_sword_cave_item`
2. `shuffle_white_sword_cave_item`
3. `shuffle_magical_sword_cave_item`
4. `shuffle_letter_cave_item`
5. `shuffle_armos_item`
6. `shuffle_coast_item`
7. `shuffle_dungeon_hearts`
8. `shuffle_shop_arrows`
9. `shuffle_shop_candle`
10. `shuffle_shop_ring`
11. `shuffle_shop_book`
12. `shuffle_shop_bait`
13. `shuffle_potion_shop_items`
14. `shuffle_minor_dungeon_items`

**Test Steps (per flag):**
1. Enable only `major_item_shuffle` and one specific flag
2. Generate seed
3. Verify only the targeted item type is shuffled
4. Verify seed is beatable

**Expected Result:**
- Each flag shuffles only its designated items
- No unintended items shuffled
- Seeds remain beatable

**Automated:** Partial - coverage exists in test suite

---

#### TC-012: All Constraint Flags Individually
**Priority:** 🟡 HIGH
**Feature:** Item Constraints
**Description:** Test each of the 8 constraint flags

**Flags to Test:**
1. `force_arrow_to_level_nine`
2. `force_ring_to_level_nine`
3. `force_wand_to_level_nine`
4. `force_heart_container_to_level_nine`
5. `force_two_heart_containers_to_level_nine`
6. `force_heart_container_to_armos`
7. `force_heart_container_to_coast`
8. `force_sword_to_open_cave`
9. `allow_important_items_in_level_nine`

**Test Steps (per flag):**
1. Enable major item shuffle
2. Enable one specific constraint flag
3. Generate 10 seeds
4. Parse ROMs to verify constraint satisfied
5. Verify seeds are beatable

**Expected Result:**
- Constraint always satisfied (item in specified location)
- Seeds remain valid and beatable

**Automated:** Should be - add to test suite

---

#### TC-013: Hint System Changes
**Priority:** 🟡 HIGH
**Feature:** Hints
**Description:** Verify hints generate correctly without blanks

**Test Steps:**
1. Generate seed with hint text enabled
2. Parse ROM hint text regions
3. Verify no blank hints
4. Verify hints fit in available space
5. Verify hint accuracy (hint matches actual item location)

**Expected Result:**
- All hints contain valid text
- No overflow or truncation
- Hints are accurate and helpful

**Automated:** Partial - `tests/test_hint_safeguard.py`, `test_hint_limit_overflow.py`

---

#### TC-014: ROM Config Validation
**Priority:** 🟡 HIGH
**Feature:** ROM Memory
**Description:** Verify ROM memory regions documented in rom_config.yaml are correct

**Test Steps:**
1. Load `rom_config.yaml`
2. For each documented region:
   - Read data from specified offset
   - Verify data matches expected type/format
   - Test writing to writable regions
3. Verify test data extraction works

**Expected Result:**
- All regions documented correctly
- Offsets match actual ROM layout
- Test data extraction succeeds

**Automated:** Partial - `tests/extract_test_data.py`

---

#### TC-015: Patch System (IPS Loading)
**Priority:** 🟡 HIGH
**Feature:** Patches
**Description:** Verify IPS patches load and apply correctly

**Test Steps:**
1. Generate ROM with QoL patches enabled
2. Verify IPS files loaded from `ips/` directory
3. Verify patches applied to ROM
4. Test ROM in emulator for patch effects

**Expected Result:**
- IPS files load without error
- Patches apply correctly
- In-game effects visible

**Automated:** Partial - `tests/test_patch_validation.py`

---

#### TC-016: QoL Flags Individually
**Priority:** 🟡 HIGH
**Feature:** Quality of Life
**Description:** Test each QoL flag individually

**Flags to Test:**
1. `speed_up_dungeon_transitions`
2. `fast_fill`
3. `four_potion_inventory`
4. `auto_show_letter`
5. `speed_up_text`

**Test Steps (per flag):**
1. Generate ROM with one QoL flag enabled
2. Test in emulator
3. Verify effect works as intended
4. Verify no side effects

**Expected Result:**
- Each QoL feature works independently
- No conflicts or bugs
- Effects are noticeable and helpful

**Automated:** No - Requires emulator testing

---

#### TC-017: Validator Catches Impossible Seeds
**Priority:** 🟡 HIGH
**Feature:** Validator
**Description:** Verify validator rejects truly impossible seeds

**Test Steps:**
1. Manually create impossible scenario (e.g., required item behind locked door, key unreachable)
2. Run validator
3. Verify validator fails seed
4. Verify error message explains why seed is impossible

**Expected Result:**
- Validator correctly identifies impossible seeds
- Clear failure message
- No false positives (valid seeds marked invalid)

**Automated:** Should be - add negative test cases

---

### 🟢 MEDIUM Priority Test Cases

#### TC-018: Solver A/B/C Comparison
**Priority:** 🟢 MEDIUM
**Feature:** Solvers
**Description:** Verify all three solvers produce valid results

**Test Steps:**
1. Configure to use AssignmentSolver (OR-Tools)
2. Generate 10 seeds
3. Configure to use RandomizedBacktrackingSolver
4. Generate same 10 seeds
5. Configure to use RejectionSamplingSolver
6. Generate same 10 seeds
7. Compare results

**Expected Result:**
- All solvers produce valid solutions
- Solutions may differ (randomization) but all valid
- No crashes or errors

**Automated:** Yes - `tests/test_solver_comparison.py`, `test_abc_solver_comparison.py`

---

#### TC-019: Performance Benchmarks
**Priority:** 🟢 MEDIUM
**Feature:** Performance
**Description:** Verify seed generation performance is acceptable

**Test Steps:**
1. Run performance test suite
2. Measure time to generate 100 seeds
3. Compare against baseline (v1.0)
4. Verify no significant regression

**Expected Result:**
- Seed generation <5 seconds average
- No major performance regression from v1.0
- Solver performance matches documented benchmarks

**Automated:** Yes - `tests/test_solver_scaling.py`

---

#### TC-020: UI Edge Cases
**Priority:** 🟢 MEDIUM
**Feature:** UI
**Description:** Test UI handles edge cases gracefully

**Test Scenarios:**
1. Very long flagstring (100+ characters)
2. Invalid flagstring (garbage input)
3. Missing ROM file
4. Corrupted ROM file
5. Rapid flag toggling
6. Window resize during generation

**Expected Result:**
- No crashes
- Graceful error messages
- UI remains responsive

**Automated:** No - Manual UI testing

---

#### TC-021: CLI Error Handling
**Priority:** 🟢 MEDIUM
**Feature:** CLI
**Description:** Verify CLI handles errors gracefully

**Test Scenarios:**
1. Missing required arguments
2. Invalid flagstring
3. Non-existent input file
4. Invalid output directory
5. Disk full scenario

**Expected Result:**
- Clear error messages
- Non-zero exit codes on failure
- No stack traces for user errors

**Automated:** Scriptable

---

#### TC-022: Documentation Accuracy
**Priority:** 🟢 MEDIUM
**Feature:** Documentation
**Description:** Verify documentation matches implementation

**Test Steps:**
1. Review `docs/ui_structure/*.md`
2. Verify UI screenshots match current UI
3. Verify flag descriptions match behavior
4. Check solver docs match implementation

**Expected Result:**
- Documentation up-to-date
- No misleading information
- Examples work as documented

**Automated:** No - Manual review

---

#### TC-023: Test Data Extraction
**Priority:** 🟢 MEDIUM
**Feature:** Testing Infrastructure
**Description:** Verify test data extraction works

**Test Steps:**
1. Run `tests/extract_test_data.py`
2. Verify data files generated in `tests/data/`
3. Use extracted data in tests
4. Verify data matches vanilla ROM

**Expected Result:**
- Extraction completes without error
- Data files valid
- Tests using extracted data pass

**Automated:** Yes - can be scripted

---

#### TC-024: RNG Randomness Quality
**Priority:** 🟢 MEDIUM
**Feature:** RNG
**Description:** Verify random number generator produces quality randomness

**Test Steps:**
1. Generate 1000 seeds with sequential seed values
2. Analyze distribution of item placements
3. Verify no obvious patterns or biases
4. Run statistical tests (chi-square, etc.)

**Expected Result:**
- Item placements appear random
- No detectable bias
- Passes statistical tests for randomness

**Automated:** Partially - statistical tests can be automated

---

#### TC-025: Hint Space Limits
**Priority:** 🟢 MEDIUM
**Feature:** Hints
**Description:** Verify hint system handles space limits

**Test Steps:**
1. Generate seeds with maximum hints enabled
2. Verify all hints fit in available ROM space
3. Test hint selection when space limited
4. Verify shorter hints chosen when necessary

**Expected Result:**
- No hint overflow
- Important hints prioritized
- All hints readable

**Automated:** Yes - `tests/test_hint_limit_overflow.py`

---

### 🔵 LOW Priority Test Cases

#### TC-026: Code Organization
**Priority:** 🔵 LOW
**Feature:** Code Quality
**Description:** Verify code follows project conventions

**Test Steps:**
1. Run linter (yapf/flake8)
2. Check for code smells
3. Verify consistent naming
4. Review import organization

**Expected Result:**
- Code passes linting
- Consistent style throughout
- No obvious code smells

**Automated:** Yes - can use pre-commit hooks

---

#### TC-027: Logging Improvements
**Priority:** 🔵 LOW
**Feature:** Logging
**Description:** Verify logging is helpful for debugging

**Test Steps:**
1. Generate seed with `--loglevel DEBUG`
2. Review log output
3. Verify log messages are clear
4. Verify log levels appropriate

**Expected Result:**
- Logs help debug issues
- No spam or excessive logging
- Levels used correctly

**Automated:** Partial - log parsing tests

---

---

## Test Scenarios

### Scenario 1: Basic Shuffle - New User Experience

**Objective:** Simulate a new user trying basic item shuffle

**Steps:**
1. Launch ZORA UI
2. Load vanilla Zelda ROM
3. Check "Major Item Shuffle" only
4. Leave seed blank (random)
5. Click "Randomize"
6. Save output ROM
7. Play ROM for 30 minutes

**Success Criteria:**
- ROM generates successfully
- Items are shuffled
- Seed is beatable (can make progress)
- No obvious bugs or crashes

**Tester Feedback:** Collect user experience notes

---

### Scenario 2: Full Shuffle - Advanced User

**Objective:** Test maximum randomization

**Steps:**
1. Enable `major_item_shuffle`
2. Enable all 13 shuffle flags
3. Enable several constraint flags (compatible set)
4. Add QoL flags: `speed_up_text`, `fast_fill`
5. Add cosmetic: `shuffle_start_screen`
6. Generate seed
7. Validate seed with validator logs
8. Attempt playthrough

**Success Criteria:**
- ROM generates without timeout
- Validator passes seed
- All flags apply correctly
- Seed is completable

**Expected Time:** 10-30 seconds generation time

---

### Scenario 3: Constraint Conflicts

**Objective:** Test error handling for impossible constraints

**Steps:**
1. Enable `major_item_shuffle`
2. Enable incompatible constraints:
   - `force_arrow_to_level_nine`
   - `force_ring_to_level_nine`
   - `force_wand_to_level_nine`
   - `force_two_heart_containers_to_level_nine`
   - `force_heart_container_to_level_nine`
3. Attempt seed generation

**Success Criteria:**
- System detects impossible constraint set
- Clear error message displayed
- No crash or hang
- User can adjust flags and retry

**Error Message Should Include:**
- Which constraints conflict
- Suggested resolution

---

### Scenario 4: Health Mode Matrix

**Objective:** Test all 4 health respawn modes

**Setup:**
Generate 4 ROMs with different health configurations:

| ROM | increase_minimum_health | keep_health_after_death_warp |
|-----|-------------------------|------------------------------|
| A   | ❌ No                  | ❌ No                       |
| B   | ❌ No                  | ✅ Yes                      |
| C   | ✅ Yes                 | ❌ No                       |
| D   | ✅ Yes                 | ✅ Yes                      |

**Test Procedure (for each ROM):**
1. Play until max health = 10 hearts
2. Take damage to 2 hearts (< 3)
3. Die or death warp
4. Note respawn health

**Expected Results:**
- ROM A: 3 hearts (vanilla)
- ROM B: 3 hearts (current < 3)
- ROM C: 5 hearts (max/2 = 10/2)
- ROM D: 5 hearts (max of 2, 3, 5)

**Additional Test:**
5. Take damage to 6 hearts (> 3)
6. Die or death warp
7. Note respawn health

**Expected Results:**
- ROM A: 3 hearts (vanilla)
- ROM B: 6 hearts (kept current)
- ROM C: 5 hearts (max/2 = 10/2)
- ROM D: 6 hearts (max of 6, 3, 5)

---

### Scenario 5: UI Stress Test

**Objective:** Test UI robustness under rapid interaction

**Steps:**
1. Launch UI
2. Rapidly toggle flags on/off (50+ toggles in 30 seconds)
3. Edit flagstring manually while checkboxes updating
4. Load different ROMs while flags checked
5. Resize window during generation
6. Switch tabs rapidly

**Success Criteria:**
- No crashes
- No UI deadlock
- State synchronization remains correct
- Flagstring always matches checkbox state

**Known Issues to Watch:**
- Race conditions
- Event handler conflicts
- State desynchronization

---

### Scenario 6: Determinism Validation

**Objective:** Prove seed determinism across platforms

**Setup:**
- 3 test machines: Windows, macOS, Linux
- Same Python version on all
- Same ZORA beta-1.1 code

**Steps:**
1. Generate ROM with seed=99999, flags="AS" on Windows
2. Calculate SHA256 hash of output ROM
3. Repeat on macOS with identical parameters
4. Repeat on Linux with identical parameters
5. Compare all 3 ROM hashes

**Success Criteria:**
- All 3 ROMs have identical SHA256 hash
- Binary comparison shows 0 differences
- Proves cross-platform determinism

**Additional Test:**
6. Generate same seed 10 times on same machine
7. Verify all 10 are identical

---

### Scenario 7: CLI vs UI Parity

**Objective:** Verify CLI and UI produce identical output

**Steps:**
1. In UI: Generate ROM with seed=12345, flags="AS_BCDE"
2. Note output ROM path and hash
3. In CLI: Run identical generation:
   ```bash
   python -m cli.cli --seed 12345 --flagstring "AS_BCDE" --input-file vanilla.nes --output-file test_cli.nes
   ```
4. Compare UI ROM and CLI ROM

**Success Criteria:**
- ROMs are byte-identical
- Same generation time (within 10%)
- Both produce valid ROMs

**Edge Cases:**
- Test with blank seed (random)
- Test with very long flagstring
- Test with all flags enabled

---

### Scenario 8: Progressive Item Playthrough

**Objective:** Verify progressive items work correctly in gameplay

**Setup:**
- Generate seed with major item shuffle
- Use flagstring that guarantees progressive sword locations

**Playthrough Checklist:**
- [ ] Find Wood Sword
- [ ] Verify Wood Sword in inventory (not White/Magical)
- [ ] Verify Wood Sword damage correct
- [ ] Find White Sword location
- [ ] Verify automatic upgrade to White Sword
- [ ] Verify Wood Sword removed from inventory
- [ ] Verify White Sword damage increased
- [ ] Find Magical Sword location
- [ ] Verify automatic upgrade to Magical Sword
- [ ] Verify only Magical Sword in inventory
- [ ] Repeat for Boomerang progression
- [ ] Repeat for Ring progression

**Success Criteria:**
- Upgrades happen automatically
- No duplicate items
- Damage/effects match expected item tier

---

### Scenario 9: Validator Edge Cases

**Objective:** Test validator's ability to catch subtle issues

**Test Cases:**
1. **Unreachable Item**: Required item behind ladder barrier, ladder unreachable
2. **Circular Dependency**: Bow needed to get arrows, arrows needed to get bow
3. **Progressive Item Confusion**: White Sword obtained before Wood Sword
4. **Heart Container Shortage**: Not enough hearts to survive required damage
5. **Missing Required Item**: Silver Arrows not in pool when Ganon enabled

**For Each Test:**
1. Manually construct scenario (may need to hack ROM)
2. Run validator
3. Verify validator FAILS seed
4. Verify error message explains issue

**Success Criteria:**
- Validator catches all 5 scenarios
- Clear error messages
- No false positives on valid seeds

---

### Scenario 10: Performance Regression Test

**Objective:** Ensure beta-1.1 performs as well as v1.0

**Benchmark Suite:**
1. Generate 100 seeds with basic shuffle
2. Generate 100 seeds with full shuffle
3. Generate 100 seeds with max constraints
4. Measure total time for each suite

**Baseline (v1.0):**
- Suite 1: ~60 seconds
- Suite 2: ~90 seconds
- Suite 3: ~120 seconds

**Acceptance Criteria:**
- Beta-1.1 within 20% of baseline
- No individual seed >10 seconds
- Average <3 seconds per seed

**Tools:**
```bash
python tests/test_solver_scaling.py --benchmark
```

---

## Regression Testing

### Purpose
Verify that bug fixes from 1.0 remain fixed in 1.1, and no new bugs introduced.

### Bug Fixes to Validate

#### Fix #1: Item.RUPEE Bug
**Original Issue:** Rupee handling broken in item shuffle
**Verification:**
1. Enable major item shuffle
2. Generate 10 seeds
3. Parse ROMs to check rupee item data
4. Verify rupees in correct locations
5. Verify no corrupted rupee items

**Pass Criteria:** No rupee-related issues

---

#### Fix #2: Compass Pointers & Start Screens
**Original Issue:** Compass pointers and start screens not writing to ROM correctly
**Verification:**
1. Generate ROM with start screen randomization
2. Check ROM bytes at compass pointer regions
3. Verify data written correctly
4. Test in emulator: compass should point correctly

**Pass Criteria:** Compass works in randomized ROMs

---

#### Fix #3: Progressive Item Downgrading
**Original Issue:** Armos/coast items causing progressive item issues
**Verification:**
1. Generate seed with armos/coast items shuffled
2. Collect progressive items in various orders
3. Verify no downgrades occur
4. Verify no item loss

**Pass Criteria:** Progressive items always upgrade, never downgrade

---

#### Fix #4: Health Settings Patches
**Original Issue:** Health patches had bugs
**Verification:**
1. Test all 4 health modes (see Scenario 4)
2. Verify all modes work correctly
3. Verify no edge case bugs

**Pass Criteria:** All health modes work as designed

---

#### Fix #5: Hint Shop Fixes
**Original Issue:** Blank hints appearing
**Verification:**
1. Generate 20 seeds
2. Parse hint text from all ROMs
3. Verify no blank hints
4. Verify all hints are valid strings

**Pass Criteria:** No blank or corrupted hints

---

### Regression Test Suite Execution

**Command:**
```bash
# Run full regression test suite
python -m pytest tests/ -v --tb=short

# Run specific regression markers (if implemented)
python -m pytest tests/ -m regression -v
```

**Expected Results:**
- All tests pass
- No new failures vs v1.0 test results
- Test coverage ≥80%

---

## Performance Testing

### Performance Targets

| Metric | Target | Maximum |
|--------|--------|---------|
| Single seed generation | <3s avg | 10s max |
| 100 seed batch | <5min | 10min |
| UI responsiveness | <100ms | 500ms |
| ROM file size | <256KB | 512KB |
| Memory usage | <500MB | 1GB |

### Performance Test Suite

#### Test 1: Solver Performance
**Tool:** `tests/test_solver_scaling.py`

**Measurements:**
- AssignmentSolver: ~3.6ms (requires ortools)
- RandomizedBacktrackingSolver: ~3.6ms (current default)
- RejectionSamplingSolver: ~0.2ms (fastest)

**Validation:**
```bash
python -m pytest tests/test_solver_scaling.py -v --benchmark
```

---

#### Test 2: Generation Throughput
**Objective:** Measure seeds generated per minute

**Test:**
```bash
time python -m cli.cli --seed {1..100} --flagstring "AS" --input-file vanilla.nes --output-dir ./perf_test/
```

**Target:** ≥20 seeds/minute

---

#### Test 3: Memory Profiling
**Objective:** Ensure no memory leaks

**Tool:** `memory_profiler`

**Test:**
```bash
python -m memory_profiler ui/main.py
# Generate 50 seeds
# Monitor memory usage
```

**Pass Criteria:**
- Memory usage stable over time
- No leaks after repeated generations
- Peak memory <1GB

---

#### Test 4: UI Responsiveness
**Objective:** Measure UI lag during generation

**Manual Test:**
1. Start ROM generation
2. Try to interact with UI (toggle flags, switch tabs)
3. Measure response time

**Target:** UI remains responsive (<500ms delay)

---

## User Acceptance Testing

### Beta Tester Recruitment

**Target Audience:**
- Experienced Zelda randomizer players (10 testers)
- Casual players (5 testers)
- First-time users (5 testers)

**Platforms:**
- Windows (10 testers)
- macOS (5 testers)
- Linux (5 testers)

---

### UAT Test Plan

#### Week 1: Functionality Testing
**Tasks for Testers:**
1. Install ZORA beta-1.1
2. Generate 5 seeds with various flag combinations
3. Play each seed for 30-60 minutes
4. Report any bugs or issues
5. Rate user experience (1-10 scale)

**Feedback Collection:**
- Bug reports via GitHub issues
- Experience survey via Google Forms
- Discord/forum discussion thread

---

#### Week 2: Feature Exploration
**Tasks for Testers:**
1. Try all new features:
   - Major item shuffle
   - Start screen randomization
   - Health mode variants
   - QoL patches
2. Test CLI tool
3. Test edge cases (max flags, constraints)
4. Provide feedback on UI/UX

---

#### Week 3: Playthrough Testing
**Tasks for Testers:**
1. Complete at least 1 full playthrough
2. Report softlocks or unbeatable seeds
3. Note progression pacing issues
4. Evaluate difficulty balance

**Success Criteria:**
- ≥80% of seeds beatable
- ≥70% positive user feedback
- <5 critical bugs reported

---

### UAT Metrics

| Metric | Target |
|--------|--------|
| User satisfaction score | ≥8/10 |
| Critical bugs found | <5 |
| Unbeatable seeds | <5% |
| UI usability rating | ≥7/10 |
| Feature adoption rate | ≥60% try new features |

---

## Test Schedule

### Week 1: Automated Testing (Nov 18-24)
- **Mon-Tue:** Run existing test suite, fix failures
- **Wed-Thu:** Execute critical test cases (TC-001 to TC-008)
- **Fri:** Execute high priority tests (TC-009 to TC-017)
- **Weekend:** Performance testing

### Week 2: Feature & Integration Testing (Nov 25 - Dec 1)
- **Mon:** Test all shuffle flags individually (TC-011)
- **Tue:** Test all constraint flags (TC-012)
- **Wed:** Test scenarios 1-5
- **Thu:** Test scenarios 6-10
- **Fri:** Regression testing
- **Weekend:** Buffer for re-testing failures

### Week 3: User Acceptance Testing (Dec 2-8)
- **Mon:** Deploy beta to testers
- **Tue-Thu:** UAT Week 1 (functionality)
- **Fri:** Collect and triage feedback
- **Weekend:** Fix critical bugs

### Week 4: Final Validation (Dec 9-15)
- **Mon-Wed:** UAT Week 2 (feature exploration)
- **Thu:** UAT Week 3 (playthrough testing)
- **Fri:** Final bug fixes
- **Weekend:** Prepare release

### Week 5: Release Preparation (Dec 16-22)
- **Mon-Tue:** Final regression testing
- **Wed:** Release candidate build
- **Thu:** Final validation
- **Fri:** Release 1.1 Beta 2 to public

---

## Risk Assessment

### High Risk Areas

#### Risk 1: Unsolvable Seeds
**Probability:** Medium
**Impact:** High
**Mitigation:**
- Comprehensive validator testing
- Statistical analysis of 1000+ generated seeds
- Beta tester playthroughs
- Failsafe: Allow multiple generation attempts

---

#### Risk 2: Determinism Breaks
**Probability:** Low
**Impact:** Critical
**Mitigation:**
- Extensive determinism test suite
- Cross-platform validation
- RNG refactor review
- Automated regression tests

---

#### Risk 3: UI Regression
**Probability:** Medium
**Impact:** Medium
**Mitigation:**
- Manual UI testing checklist
- User acceptance testing
- Backward compatibility testing
- Flagstring validation tests

---

#### Risk 4: Performance Regression
**Probability:** Low
**Impact:** Medium
**Mitigation:**
- Performance benchmarks
- Solver comparison tests
- Load testing (100+ seed generation)
- Profiling for bottlenecks

---

#### Risk 5: Progressive Item Bugs
**Probability:** Medium
**Impact:** High
**Mitigation:**
- Dedicated progressive item test suite
- Playthrough testing
- Edge case scenarios
- Validator checks for progressive items

---

### Medium Risk Areas

#### Risk 6: Constraint Conflict Detection
**Probability:** Medium
**Impact:** Medium
**Mitigation:**
- Test impossible constraint combinations
- Clear error messaging
- UI hints for compatible constraints

---

#### Risk 7: Platform-Specific Bugs
**Probability:** Low
**Impact:** Medium
**Mitigation:**
- Multi-platform testing (Windows/macOS/Linux)
- Cross-platform determinism validation
- Platform-specific testers

---

### Low Risk Areas

#### Risk 8: Documentation Gaps
**Probability:** Medium
**Impact:** Low
**Mitigation:**
- Documentation review
- User feedback on clarity
- In-app help text

---

#### Risk 9: Minor UI Glitches
**Probability:** Medium
**Impact:** Low
**Mitigation:**
- Manual UI testing
- Beta tester feedback
- Cosmetic fixes can be deferred

---

## Bug Reporting Process

### Bug Report Template

```markdown
**Bug Title:** [Concise description]

**Severity:** [Critical / High / Medium / Low]

**Test Case:** [TC-XXX if applicable]

**Environment:**
- OS: [Windows 10 / macOS 13 / Ubuntu 22.04]
- Python Version: [3.8 / 3.9 / 3.10]
- ZORA Version: [1.1 BETA 2]
- Commit Hash: [git commit hash]

**Steps to Reproduce:**
1. [First step]
2. [Second step]
3. [And so on...]

**Expected Behavior:**
[What should happen]

**Actual Behavior:**
[What actually happens]

**Screenshots/Logs:**
[Attach relevant files]

**Additional Context:**
[Any other relevant information]
```

---

### Severity Levels

#### Critical (P0)
- Crashes or data loss
- Completely unusable feature
- Determinism broken
- Unbeatable seeds generated consistently

**Response Time:** Fix immediately, halt testing

---

#### High (P1)
- Major feature not working as designed
- Workaround exists but difficult
- Affects majority of users

**Response Time:** Fix within 24-48 hours

---

#### Medium (P2)
- Minor feature issues
- Cosmetic bugs
- Edge cases
- Affects small subset of users

**Response Time:** Fix within 1 week

---

#### Low (P3)
- Typos, documentation issues
- Minor UI glitches
- Performance optimization opportunities

**Response Time:** Fix before release or defer to future version

---

### Bug Triage Process

**Daily Triage Meeting:**
1. Review new bugs reported in last 24h
2. Assign severity levels
3. Assign to developer
4. Prioritize fixes
5. Update testing status

**Tracking:**
- Use GitHub Issues with labels: `bug`, `critical`, `high`, `medium`, `low`, `beta-1.1`
- Update test case status when bugs found
- Link bugs to test cases

---

## Acceptance Criteria

### Release Criteria for Beta 1.1

#### Must Pass (Blockers)
- ✅ All critical test cases (TC-001 to TC-008) pass
- ✅ Zero critical (P0) bugs open
- ✅ Determinism tests pass 100%
- ✅ Validator accuracy ≥95%
- ✅ UI flag synchronization works correctly
- ✅ CLI generates identical ROMs to UI
- ✅ All existing tests in test suite pass
- ✅ Regression tests pass (no v1.0 bugs reintroduced)

#### Should Pass (Strong Preference)
- ✅ All high priority test cases (TC-009 to TC-017) pass
- ✅ ≤2 high (P1) bugs open
- ✅ User satisfaction score ≥8/10
- ✅ Performance targets met
- ✅ Documentation complete and accurate

#### Nice to Have
- ✅ All medium priority test cases pass
- ✅ Zero medium (P2) bugs open
- ✅ Test coverage ≥80%
- ✅ All platforms tested (Windows, macOS, Linux)

---

### Definition of Done

A test case is considered **DONE** when:
1. Test executed successfully
2. Results documented
3. Any bugs filed and linked
4. Tester sign-off
5. Results reviewed by QA lead

A feature is considered **DONE** when:
1. All related test cases pass
2. No open critical or high bugs
3. Code reviewed
4. Documentation updated
5. User acceptance criteria met

---

### Sign-Off Requirements

**QA Lead Sign-Off:**
- All critical tests passed
- Bug triage complete
- Test report published

**Developer Sign-Off:**
- All P0/P1 bugs fixed
- Code review complete
- Regression tests pass

**Product Owner Sign-Off:**
- UAT results satisfactory
- Release criteria met
- Documentation approved

**Final Release Decision:**
- Requires all three sign-offs
- Final smoke test on release build
- Release notes prepared

---

## Appendices

### Appendix A: Flagstring Reference

**Common Flagstrings for Testing:**
```
A          - Major item shuffle only
AS         - Major shuffle + wood sword shuffle
AS_BCDEFG  - Major shuffle + all sword caves
FULL       - All shuffle flags enabled
HEALTH1    - increase_minimum_health
HEALTH2    - keep_health_after_death_warp
HEALTH3    - Both health flags
QOL        - All quality of life flags
```

---

### Appendix B: Test Environment Setup Details

**Required Files:**
- Vanilla Zelda 1 ROM (MD5: cfb224e274a70f3c3e800b469c28f12f)
- Python 3.8+ with packages from requirements.txt
- Optional: Emulator for playthrough testing (FCEUX recommended)

**Directory Structure:**
```
zora/
├── tests/
│   ├── data/          # Extracted test data
│   ├── test_*.py      # Test files
│   └── roms/          # Test ROM output
├── output/            # Generated ROMs
└── vanilla.nes        # Input vanilla ROM
```

---

### Appendix C: Useful Commands

**Run All Tests:**
```bash
python -m pytest tests/ -v
```

**Run Specific Test File:**
```bash
python -m pytest tests/test_major_item_randomizer.py -v
```

**Run Tests with Coverage:**
```bash
python -m pytest tests/ --cov=logic --cov-report=html
```

**Generate ROM via CLI:**
```bash
python -m cli.cli --seed 12345 --flagstring "AS" --input-file vanilla.nes --output-dir ./output --loglevel INFO
```

**Extract Test Data:**
```bash
python tests/extract_test_data.py --rom vanilla.nes --output-dir tests/data/
```

---

### Appendix D: Contact Information

**QA Lead:** [TBD]
**Lead Developer:** [TBD]
**Product Owner:** [TBD]

**Bug Reports:** https://github.com/tetraly/zora/issues
**Discord:** [TBD]
**Email:** [TBD]

---

## Conclusion

This testing plan provides comprehensive coverage of ZORA Beta 1.1's new features, bug fixes, and existing functionality. Following this plan will ensure a high-quality beta release that meets user expectations and maintains the stability of the randomizer.

**Key Takeaways:**
1. Focus on critical test cases first (seed determinism, item shuffle, validation)
2. Extensive automated testing to catch regressions
3. User acceptance testing to validate real-world usage
4. Clear bug reporting and triage process
5. Defined acceptance criteria for release

**Estimated Testing Effort:**
- Automated testing: 40 hours
- Manual testing: 60 hours
- User acceptance testing: 80 hours (distributed across testers)
- Bug fixing: 40 hours
- **Total: ~220 hours over 5 weeks**

Good luck with the beta testing! 🎮
