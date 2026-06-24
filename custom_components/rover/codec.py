"""Codec for Rover protocol — msgpack encode/decode."""
from __future__ import annotations

import msgpack


def encode(fields: dict) -> bytes:
    """Encode fields to msgpack bytes."""
    return msgpack.packb(fields, use_bin_type=True)


def decode(data: bytes) -> dict:
    """Decode msgpack bytes to dict."""
    return msgpack.unpackb(data, raw=False)
