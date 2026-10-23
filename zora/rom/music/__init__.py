"""Randomized music (proof of concept; docs/music.md): Quantam's lozft, the FamiTracker music driver
for The Legend of Zelda, and songs from his standard library, imported into a finished ROM.

ZORA never holds the music or the patch: both come from Quantam's ZeldaMusicRandomizer repository at
a pinned commit (pin.py), fetched by the page or read from a local clone by scripts and tests, and
handed in as MusicAssets, whose checksums are checked before use. randomize.randomize_music is the
one entry point.
"""
