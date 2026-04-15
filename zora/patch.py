"""IPS patch generation and base64 encoding utilities."""
from __future__ import annotations

import base64
import struct

# IPS format constants
_IPS_HEADER = b"PATCH"
_IPS_EOF = b"EOF"
_IPS_MAX_OFFSET = 0xFFFFFF  # 3-byte offset limit


def build_ips_patch(records: list[tuple[int, bytes]]) -> bytes:
    """Encode a list of (offset, data) records into an IPS patch bytestring.

    Offsets must be 0-0xFFFFFF. Data length must be 1-65535 per record.
    Records are not sorted or merged — pass them in the order you want.
    """
    out = bytearray(_IPS_HEADER)
    for offset, data in records:
        if offset > _IPS_MAX_OFFSET:
            raise ValueError(f"IPS offset {offset:#x} exceeds maximum {_IPS_MAX_OFFSET:#x}")
        if not data:
            raise ValueError("IPS record data must not be empty")
        out += struct.pack(">I", offset)[1:]  # 3-byte big-endian offset
        out += struct.pack(">H", len(data))   # 2-byte length
        out += data
    out += _IPS_EOF
    return bytes(out)


def encode_patch(patch_bytes: bytes) -> str:
    """Base64-encode patch bytes for JSON transport."""
    return base64.b64encode(patch_bytes).decode("ascii")
