"""Message dispatcher for Rover protocol — normalizes wire keys and routes by type."""
from __future__ import annotations

import logging
from typing import Callable

from .const import LOGGER_HND
from .registry import RoverRegistry

_GENERAL_MAP: dict[int, str] = {
    0: "tp",
    1: "section",
    2: "h",
    3: "data",
}

_TP_MAPS: dict[int, dict[int, str]] = {
    # All types use the same flat key space as _OUT_KEY_MAP
    # STATUS (tp=2) — snapshot response
    2: {4: "v", 5: "s", 6: "b", 7: "ct", 8: "rgb"},
    # PUSH (tp=3) — state change  
    3: {35: "id", 4: "v", 6: "b", 7: "ct", 8: "rgb"},
    # CONFIG (tp=4) — section contents
    4: {1: "section", 37: "hash", 3: "data"},
    # CMD (tp=5) — device command
    5: {35: "id", 5: "s", 6: "b", 7: "ct", 8: "rgb"},
    # PING/PONG (tp=6) — section hashes
    6: {30: "m", 28: "u", 31: "a", 32: "d", 33: "diffs", 60: "sections"},
    # FORBIDDEN (tp=7)
    7: {34: "reason"},
    # REQ (tp=8)
    8: {60: "sections", 34: "reason"},
    # REGISTER (tp=9)
    9: {49: "uid", 50: "dst", 36: "name"},
}

_LOGGER = logging.getLogger(LOGGER_HND)


def normalize(fields: dict) -> tuple[int, dict]:
    """Normalize wire integer keys to Python string keys.
    
    Args:
        fields: Raw fields from wire (integer keys) or already normalized dict
        
    Returns:
        Tuple of (tp, normalized_fields_dict)
    """
    # Check if fields are already normalized (have string keys)
    if not fields:
        return 0, {}
    
    # Check if tp is already present as string key
    if "tp" in fields:
        tp = fields["tp"]
        normalized = fields.copy()
        return tp, normalized
    
    # Check if tp is present as integer key 0
    if 0 in fields:
        tp = fields[0]
        normalized = {}
        
        # Apply general map
        for int_key, str_key in _GENERAL_MAP.items():
            if int_key in fields:
                normalized[str_key] = fields[int_key]
        
        # Apply type-specific map
        if tp in _TP_MAPS:
            for int_key, str_key in _TP_MAPS[tp].items():
                if int_key in fields:
                    normalized[str_key] = fields[int_key]
        
        return tp, normalized
    
    # If no tp found, return 0
    return 0, {}


class RoverDispatcher:
    """Message dispatcher for Rover protocol."""
    
    def __init__(self, registry: RoverRegistry) -> None:
        """Initialize the dispatcher."""
        self._registry = registry
        self._handlers: dict[int, Callable[[bytes, dict], None]] = {}
        self._default_handler: Callable[[bytes, dict], None] | None = None
    
    def register_handler(self, tp: int, handler: Callable[[bytes, dict], None]) -> None:
        """Register a handler function for a given message type.
        
        Args:
            tp: Message type (e.g., 2 for STATUS, 3 for PUSH)
            handler: Async handler function with signature (src_hash: bytes, fields: dict) -> None
        """
        self._handlers[tp] = handler
    
    def set_default_handler(self, handler: Callable[[bytes, dict], None]) -> None:
        """Set handler for unknown tp values.
        
        Args:
            handler: Default handler function with signature (src_hash: bytes, fields: dict) -> None
        """
        self._default_handler = handler
    
    async def dispatch(self, src_hash: bytes, fields: dict) -> None:
        """Main entry point called by the transport.
        
        Args:
            src_hash: Source identity hash
            fields: Raw fields from wire (integer keys) or already normalized dict
        """
        # Normalize fields
        tp, normalized_fields = normalize(fields)
        
        # Look up handler by tp
        handler = self._handlers.get(tp)
        
        if handler:
            await handler(src_hash, normalized_fields)
        elif self._default_handler:
            _LOGGER.warning("Unknown message type %d, using default handler", tp)
            await self._default_handler(src_hash, normalized_fields)
        else:
            _LOGGER.warning("Unknown message type %d, no default handler registered", tp)