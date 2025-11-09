# Randomizer Determinism

This document explains how the ZORA randomizer ensures deterministic behavior (same seed + flags = same ROM every time).

## Critical Requirements

### PYTHONHASHSEED=0

The randomizer **requires** `PYTHONHASHSEED=0` to be set. This is automatically handled by **all entry points**, so you don't need to set it manually.

**Protected entry points:**
- `cli/cli.py` - Command-line interface
- `ui/main.py` - Desktop UI (Flet app)
- `web/web.py` - Web server (Render.com deployment)
- `macos/macos.py` - macOS app bundle
- `windows/app.py` - Windows executable
- `tests/test_determinism.py` - Determinism test suite

**Why is this needed?**

Python has built-in hash randomization for security purposes. Without `PYTHONHASHSEED=0`:
- Dictionary and set internal ordering varies between Python interpreter runs
- Even with deterministic algorithms, the hash values are different each time
- This causes the randomizer to produce different ROMs for the same seed

**Technical details:**
- All entry points check for `PYTHONHASHSEED=0` at startup
- If not set, they automatically re-execute themselves with the environment variable set
- This happens transparently before any randomization logic runs
- No manual configuration needed!

## Deterministic Design

### 1. Seeded RNG (`rng/random_number_generator.py`)
- All randomization uses a **single seeded RNG instance**
- No use of the global `random` module in randomization logic
- The RNG seed determines all random decisions

### 2. Sorted Iteration
- Sets and dictionaries are **sorted before iteration** where order matters
- Examples:
  - `bait_blocker.py` lines 135-136, 189: `sorted(partition_a)` before iteration
  - `patch.py` line 171: `sorted(self._data.keys())` for hash generation
  - `inventory.py` line 29: `sorted(self.items)` for debug output

### 3. Deterministic Validation
- `validator.py` uses deterministic iteration order for accessible destinations
- Processes caves/levels in insertion order (preserved in Python 3.7+)

### 4. Deterministic Patch Generation
- All patch addresses are sorted before hashing
- Hash generation is consistent across runs

## Testing Determinism

Run the determinism test suite:

```bash
python3 tests/test_determinism.py
```

This tests multiple seeds with various flag combinations to ensure:
- Same seed + same flags = same hash code
- Works with progressive items, hints, maze randomization, etc.

## What Sets Are Used For

Sets are used appropriately for **O(1) membership testing** in performance-critical code:

1. **`bait_blocker.py`**: Partition tracking during flood-fill
   - Heavy use of `in partition_a` checks
   - Sorted before iteration

2. **`inventory.py`**: Item inventory tracking
   - `Has(item)` called very frequently during validation
   - Sorted before string conversion

3. **`validator.py`**: Deduplication of accessible destinations
   - Only used for `in` checks, not iteration

**Performance note:** Converting these to lists would cause O(n) lookups instead of O(1), significantly slowing down validation.

## Known Non-Deterministic Code

The following uses of non-determinism are **intentional**:

- **UI random seed generation** (`ui/handlers.py`): Uses global `random` module to generate random seed values when user clicks "Random Seed" button
- This is expected behavior - users want different random seeds each time

## Troubleshooting

If you're getting different ROMs for the same seed/flags:

1. **Check PYTHONHASHSEED**: Verify it's set to 0
   ```bash
   python3 -c "import os; print('PYTHONHASHSEED:', os.environ.get('PYTHONHASHSEED'))"
   ```

2. **Use entry points**: Always use `cli/cli.py` or `ui/main.py`, not direct imports
   - These automatically set `PYTHONHASHSEED=0`

3. **Check for modifications**: Ensure no code is using global `random` module in logic

4. **Run determinism tests**: `python3 tests/test_determinism.py` should pass all tests

## Recent Fixes

### November 2025
- Added `PYTHONHASHSEED=0` to all entry points to fix hash randomization
- Sorted `inventory.ToString()` output for consistent debug logging
- Previous fixes: Sorted set iterations in `bait_blocker.py` and `patch.py`

### Pull Request #24
- Separated RNG into its own class for better determinism guarantees
- Ensured all randomization goes through seeded RNG instance
