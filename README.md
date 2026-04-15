# ZORA — Zelda One Randomizer

A randomizer for *The Legend of Zelda* (NES). Parses a vanilla ROM into a structured data model, randomizes gameplay elements, and produces an IPS patch. Served as a Flask API with a vanilla JS frontend — the ROM never leaves the browser.

## How it works

```
ROM bin files ──► parser ──► GameWorld ──► randomizer pipeline ──► serializer ──► IPS patch
                                 ▲                                                    │
                            data model                                                │
                          (dataclasses/enums)                                         ▼
                                                                              browser applies
                                                                              patch to ROM
```

1. **Parse** — Binary ROM data files are read into a `GameWorld`: a tree of Python dataclasses representing the overworld, dungeons, items, enemies, sprites, and caves.
2. **Randomize** — A pipeline of 14 randomizer steps mutates the `GameWorld` in place, each gated on resolved flag settings. Steps include item placement (assumed fill), entrance shuffling, enemy redistribution, shop/cave randomization, hint generation, and more.
3. **Serialize** — The mutated `GameWorld` is written back as a `Patch` (dict of ROM addresses to bytes), then encoded as an IPS patch.
4. **Deliver** — The API returns the base64-encoded IPS patch. The frontend applies it client-side to the user's ROM.

## What gets randomized

- **Items** — Assumed fill algorithm places items across the game world, with reachability validation ensuring every seed is completable.
- **Entrances** — Cave and dungeon entrances shuffle on the overworld.
- **Enemies** — Enemies shuffle within and between dungeon levels. Sprite groups redistribute which enemies share NES sprite banks. Boss tiers reassign across dungeons. HP values scale up, down, or randomize.
- **Dungeons** — Color palettes randomize. Items shuffle within each dungeon.
- **Overworld** — Start screen randomizes. Lost Hills / Dead Woods maze directions randomize with matching hint text.
- **Shops & caves** — Shop items and prices shuffle. Cave payouts randomize.
- **Hints** — Dynamic hint text generated from the randomized game state.

## Project structure

```
zora/                    Core Python package
  api/                   Flask API (routes, validation, app factory)
  enemy/                 Enemy randomization subsystem (10+ modules)
  patches/               Conditional ASM behavior patches (BehaviorPatch subclasses)
  data_model.py          All game entities as dataclasses/enums
  parser.py              Binary ROM files → GameWorld
  serializer.py          GameWorld → Patch
  rom_layout.py          ROM addresses and table layout constants
  generate_game.py       Main entry point — runs the full pipeline
  game_config.py         Resolves flag tristates into concrete config
  item_randomizer.py     Assumed fill item placement
  entrance_randomizer.py Entrance shuffling
  ...                    Other single-file randomizer modules

flags/                   Flag system (YAML source of truth + generated Python codec)
static/                  Frontend (vanilla JS, no build step)
rom_data/                Vanilla ROM binary data files (gitignored)
tests/                   Test suite
```

## Running locally

```bash
# Start the API server
flask --app "zora.api:create_app()" run --port 5003

# Run tests
python3 -m pytest tests/

# Regenerate flags after editing flags.yaml
python3 flags/validate_flags.py --generate
```

## Flag system

The single source of truth is `flags/flags.yaml`. It defines all flag metadata (bit offsets, types, groups, constraints) used by both the Python backend and the JS frontend to encode/decode the same base64 flag string. The frontend fetches flag definitions from `GET /flags` at runtime — no manual JS changes needed when flags change.

## Architecture notes

- **Parse → model → serialize**: All ROM regions are fully parsed into the data model, mutated by randomizers, then serialized back. The serializer starts from original bin bytes and overwrites only modeled fields.
- **IPS patching is client-side**: The API returns a patch, not a ROM. The browser applies it locally.
- **Enemy subsystem** (`zora/enemy/`): The most complex randomizer domain — handles within-level shuffling, cross-level redistribution, sprite bank repacking, boss tier assignment, and NES engine compatibility. Room-type safety checks are centralized in `safety_checks.py`.
- **Behavior patches** (`zora/patches/`): Conditional 6502 ASM patches auto-discovered at import time. Each subclass gates on `GameConfig` flags and returns ROM edits.
- **Frontend is data-driven**: Flag codec, UI controls, and validation are all generated from server-provided flag definitions. No hardcoded flag knowledge in JS.
