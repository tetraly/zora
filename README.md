# ZORA

> **Beta.** ZORA 2.0 has been tested by automated checks but not yet tested by hand. Expect
> there to be bugs and unbeatable seeds. Please don't use it for races yet. If something looks
> wrong, report it with the seed, flags and version in the
> [ZORA Discord](https://discord.gg/DVyPXcG5v).

**ZORA (Zelda One Randomizer App)** is an open-source randomizer for
*The Legend of Zelda*.

**Play it:** https://tetraly.github.io/zora/

ZORA is built on the notion that there isn't one right way to play a game.
It aims to support as many ways to reimagine, randomize, and replay Zelda 1
as possible.

## What it is

ZORA is a clean-room reconstruction of the core randomization features the
Zelda 1 community has come to expect from over a decade of Zelda 1
randomization, along with new options, flags, and ways to experience the
game. It's designed to decouple game data and logic from technical ROM
details, so adding a new feature doesn't require being an expert programmer.

ZORA is currently maintained by Tetra and welcomes new contributors.

## Who it's for

ZORA is for gamers who want to try new flags and features, for contributors
who want to shape what the randomizer becomes, and for anyone who's wanted a
way to change the game that didn't exist yet.

It's not for everyone. Some players will prefer other randomizers for their
stability, polish, or original vision, and that's okay. ZORA exists
alongside those projects, not in opposition to them.

## ZORA's values

- **Zelda for all.** ZORA belongs to everyone who plays it and everyone who
  shapes it. No single person should be indispensable, and no one who
  participates in good faith should be excluded.
- **Openness.** Open source, open governance, open reasoning. Decisions are
  made as transparently as possible.
- **Room for growth.** Zelda 1 can be reimagined in countless ways. Limits
  exist, but ZORA aims to support as many features as it can hold
  coherently.
- **Accessibility.** The codebase, the community, and the decision-making
  are all intended to welcome a wide range of skill levels.

## What comes next

ZORA is still experimental. The framework exists, the core features are in
place, and the foundation is laid for the community to shape what it
becomes. If you want to play, contribute, suggest, or just watch it develop,
you're welcome here.

*It's dangerous to go alone. Take this.*

## Known limitations (2.0 beta 2)

- Some flag values are not made yet: the page shows them greyed out as "Not yet implemented".
- "Encode level data" is not available in the public build.
- This beta has not been playtested by hand. Its seeds are checked by automated tests only.
- To report a bug, give the seed, the flags, the version and the spoiler log (the page's
  "Download spoiler log" button).

## Developer notes

The code is a Python package, `zora/`, with its tests in `tests/` (`sh scripts/verify.sh` runs
them). The web page lives in `web/`, and the ROM patches in `asm/`. Further docs: the flag names
(`docs/flag-names.md`), the seed document and spoiler log (`docs/seed-format/`) and the notes for
beta testers (`docs/beta-testers.md`). A public developer guide is still to be written.

## Licence

ZORA is released under the MIT licence; see `LICENSE`. Third-party material (community
features, fonts, the NES palette) is credited in `docs/credits.md`.

## Credits

See `docs/credits.md` for details.
