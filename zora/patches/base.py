from abc import ABC, abstractmethod
from dataclasses import dataclass

from zora.game_config import GameConfig


@dataclass
class RomEdit:
    offset: int
    new_bytes: bytes
    old_bytes: bytes | None = None
    comment: str = ""

    @staticmethod
    def _parse(value: str | bytes) -> bytes:
        if isinstance(value, str):
            return bytes(int(x, 16) for x in value.split())
        return value

    def __init__(
        self,
        offset: int,
        new_bytes: str | bytes,
        old_bytes: str | bytes | None = None,
        comment: str = "",
    ) -> None:
        self.offset = offset
        self.new_bytes = self._parse(new_bytes)
        self.old_bytes = self._parse(old_bytes) if old_bytes is not None else None
        self.comment = comment


class BehaviorPatch(ABC):

    @abstractmethod
    def is_active(self, config: GameConfig) -> bool: ...

    @abstractmethod
    def get_edits(self, rom_version: int | None = None) -> list[RomEdit]: ...

    @property
    def name(self) -> str:
        return type(self).__name__


class VariableBehaviorPatch(BehaviorPatch):
    """A BehaviorPatch whose edits depend on GameConfig values.

    Override get_edits_for_config(config, rom_version) instead of get_edits(rom_version).
    The dispatcher in build_behavior_patch calls get_edits_for_config for these patches.
    """

    def get_edits(self, rom_version: int | None = None) -> list[RomEdit]:
        raise NotImplementedError(
            f"{type(self).__name__} is a VariableBehaviorPatch — "
            "call get_edits_for_config(config, rom_version) instead"
        )

    @abstractmethod
    def get_edits_for_config(self, config: GameConfig, rom_version: int | None = None) -> list[RomEdit]: ...

    @abstractmethod
    def test_only_get_all_variant_edits(self) -> list[RomEdit]:
        """Return edits for every distinct config variant. For use in tests only."""
        ...
