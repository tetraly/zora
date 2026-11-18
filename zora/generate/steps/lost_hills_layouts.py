"""Randomize Lost Hills: screen $0B shows a layout of its own (zora/rom/extra_layouts.py), so that its right
edge opens onto $0C without $3C's, which shares $0B's layout ($0A in the first quest's look, $7B in the
second's).

FINISH gives it on the copy it writes (pipeline.written_world), as it flips the overworld for Mirror
Overworld: generation, its logic and the seed's documents see $0B's shared layout number, the finished ROM
and the world parsed from it its own."""
from ...model.overworld import Overworld
from ...rom.extra_layouts import OWN_LAYOUTS

SCREEN_11 = 0x0B
SHARED_LAYOUTS = {own: shared for shared, own in OWN_LAYOUTS.items()}


def give_screen_11_its_own_layout(overworld: Overworld) -> None:
    """$0B's layout number becomes its own copy's ($7B -> $7C, $0A -> $7D); a world that already shows
    its own (parsed from a finished ROM) is left as it is."""
    screen = overworld.screens[SCREEN_11]
    assert screen.screen_code in OWN_LAYOUTS or screen.screen_code in SHARED_LAYOUTS, \
        f"screen $0B shows layout ${screen.screen_code:02X}, which Lost Hills has no copy of"
    screen.screen_code = OWN_LAYOUTS.get(screen.screen_code, screen.screen_code)


def shared_layout(layout: int) -> int:
    """The layout a screen's layout number shows the look of: $0B's own copies read as the layouts they copy."""
    return SHARED_LAYOUTS.get(layout, layout)
