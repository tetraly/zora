"""Archipelago's slot identity in the ROM (Archipelago Phase 4c; docs/archipelago.md "Interface",
docs/rom-map.md "Archipelago slot identity"). AP's BizHawk client recognises its game and logs in
to the right slot by reading bytes the patch wrote into PRG ROM; ZORA writes them into 32 bytes
of bank 0's free space, only in External mode with a slot name (ZORA mode writes nothing there).

The record: the marker "ZORA-AP", the recipe format version (major, minor), then the slot name
(AP's bytes, 1 to 23 of them, no zero byte) padded with zeros.
"""
from __future__ import annotations

from dataclasses import dataclass

from .layout import NES_HEADER_SIZE

SLOT_IDENTITY_BANK = 0
SLOT_IDENTITY_CPU = 0xBF00                       # bank 0's free space, before its ISR copy at $BF50
BANK_SIZE, SWITCHED_BANK_BASE = 0x4000, 0x8000
SLOT_IDENTITY_ADDRESS = NES_HEADER_SIZE + SLOT_IDENTITY_BANK * BANK_SIZE + SLOT_IDENTITY_CPU - SWITCHED_BANK_BASE
SLOT_IDENTITY_SIZE = 32
MARKER = b"ZORA-AP"
VERSION_SIZE = 2                                 # the recipe format version's major and minor
NAME_START = len(MARKER) + VERSION_SIZE
MAX_NAME_LENGTH = SLOT_IDENTITY_SIZE - NAME_START       # 23
PADDING = 0x00


class SlotNameRefused(ValueError):
    """A slot name the record cannot hold: empty, too long, or with a zero byte (the padding)."""


@dataclass(frozen=True)
class SlotIdentity:
    """What the record holds: the recipe format version that wrote it, and the slot name."""
    format_version: tuple[int, int]
    ap_name: bytes


def slot_identity_record(ap_name: bytes, format_version: tuple[int, int]) -> bytes:
    """The record's 32 bytes for this slot name."""
    if not 0 < len(ap_name) <= MAX_NAME_LENGTH or PADDING in ap_name:
        raise SlotNameRefused(f"a slot name is 1 to {MAX_NAME_LENGTH} bytes with no zero byte, "
                              f"not {ap_name!r}")
    return MARKER + bytes(format_version) + ap_name.ljust(MAX_NAME_LENGTH, bytes([PADDING]))


def write_slot_identity(rom: bytearray, record: bytes) -> None:
    assert len(record) == SLOT_IDENTITY_SIZE
    rom[SLOT_IDENTITY_ADDRESS:SLOT_IDENTITY_ADDRESS + SLOT_IDENTITY_SIZE] = record


def read_slot_identity(rom: bytes) -> SlotIdentity | None:
    """The record in a .nes file (with its 16-byte header), or None when the marker is not there
    (a ZORA-mode ROM: PRG0's $FF bytes)."""
    record = rom[SLOT_IDENTITY_ADDRESS:SLOT_IDENTITY_ADDRESS + SLOT_IDENTITY_SIZE]
    if len(record) != SLOT_IDENTITY_SIZE or not record.startswith(MARKER):
        return None
    major, minor = record[len(MARKER):NAME_START]
    name = record[NAME_START:].rstrip(bytes([PADDING]))
    return SlotIdentity((major, minor), name) if name else None
