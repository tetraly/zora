"""Between levels (Triforce Shuffle and Map & Compass Shuffle, ZORA version 23; owner, 2026-11-25): BUILD places each
level's Triforce piece, map and compass as Off does, in its own level; then each kind's level numbers are shuffled
among that kind's own spots. Every level still holds exactly one of each kind, but which level's it is is drawn: the
piece found in level 3 may be level 6's. FINISH writes each spot's item as the drawn level's own code
(finish.write_level_codes), the ROM being in per-level mode, so it shows that level's digit and sets that level's bit.

The pieces, the maps and the compasses are each shuffled on their own: level 3 may hold level 6's map and level 1's
compass. The draws come from a stream of their own, keyed by the seed number and both flag strings (as Expanded
Dungeon Locations' is), so they move nothing in generation's stream, and an encoded seed's unencoded report ROM draws
the same. The logic knows them before generation: a level-9 gate that names levels (FP-TRIF-03) asks for those
levels' pieces wherever they lie (LogicRules.triforce_codes)."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass

from ..model.level_items import MAP_COMPASS_LEVELS, TRIFORCE_LEVELS, LevelItemKind
from .rng import Rng

SWAPS_STREAM = b"zora level swaps"          # 16 bytes at most (BLAKE2b's person)
SEED_BYTES = 8
KEY_SEPARATOR = "|"


@dataclass(frozen=True)
class LevelSwaps:
    """For each kind, the level whose item lies in each data level, in data-level order (entry 0 is level 1's
    spot). The identity, Off's and Anywhere's, by default."""
    triforce: tuple[int, ...] = tuple(TRIFORCE_LEVELS)
    map: tuple[int, ...] = tuple(MAP_COMPASS_LEVELS)
    compass: tuple[int, ...] = tuple(MAP_COMPASS_LEVELS)

    def of(self, kind: LevelItemKind) -> tuple[int, ...]:
        return {LevelItemKind.TRIFORCE: self.triforce, LevelItemKind.MAP: self.map,
                LevelItemKind.COMPASS: self.compass}[kind]

    def code_in(self, kind: LevelItemKind, level: int) -> int:
        """The level whose item of this kind lies in data level `level`."""
        return self.of(kind)[level - 1]

    def lies_in(self, kind: LevelItemKind, level: int) -> int:
        """The data level holding level `level`'s item of this kind."""
        return self.of(kind).index(level) + 1

    @property
    def is_identity(self) -> bool:
        return self == LevelSwaps()


NO_SWAPS = LevelSwaps()        # Off's and Anywhere's


def swaps_seed(seed: int, z1r_canonical: str, zora_canonical: str) -> int:
    """The key of the swaps' own stream: derived only from the seed number and both canonical strings."""
    message = KEY_SEPARATOR.join((str(seed), z1r_canonical, zora_canonical)).encode("utf-8")
    digest = hashlib.blake2b(message, digest_size=SEED_BYTES, person=SWAPS_STREAM).digest()
    return int.from_bytes(digest, "little")


def _shuffled(rng: Rng, levels: range) -> tuple[int, ...]:
    order = list(levels)
    rng.shuffle(order)
    return tuple(order)


def draw_level_swaps(key: int, triforces: bool, maps_compasses: bool) -> LevelSwaps:
    """The seed's swaps: the pieces' with Triforce Shuffle: Between levels, the maps' and the compasses' with Map &
    Compass Shuffle: Between levels; the identity for the others. All three are always drawn, in that order, so
    each kind's draw is the same whatever the other setting says."""
    rng = Rng(key)
    pieces, maps, compasses = (_shuffled(rng, TRIFORCE_LEVELS), _shuffled(rng, MAP_COMPASS_LEVELS),
                               _shuffled(rng, MAP_COMPASS_LEVELS))
    identity = NO_SWAPS
    return LevelSwaps(pieces if triforces else identity.triforce, maps if maps_compasses else identity.map,
                      compasses if maps_compasses else identity.compass)
