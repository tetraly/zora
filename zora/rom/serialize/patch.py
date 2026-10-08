"""Patch: the byte writes a serialization makes, applied to a ROM."""

import logging
from dataclasses import dataclass, field

log = logging.getLogger(__name__)


@dataclass
class Patch:
    data: dict[int, bytes] = field(default_factory=dict)

    def add(self, address: int, bytes_: bytes | bytearray) -> None:
        self.data[address] = bytes(bytes_)

    def merge(self, other: "Patch") -> "Patch":
        """Return a new Patch combining self and other.
        Raises ValueError if any offset appears in both."""
        conflicts = self.data.keys() & other.data.keys()
        if conflicts:
            raise ValueError(
                f"Patch merge conflict at offsets: "
                f"{[hex(a) for a in sorted(conflicts)]}"
            )
        return Patch(data={**self.data, **other.data})

    def apply(self, rom: bytearray) -> None:
        for address, bytes_ in self.data.items():
            rom[address:address + len(bytes_)] = bytes_
