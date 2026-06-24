"""Rover Registry — Store-backed persistent CRUD for all protocol sections."""
from __future__ import annotations

import hashlib
import logging
from typing import Any, Callable

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import (
    DEFAULT_TCP_PORT,
    IDENTITY_HASH_LEN,
    LOGGER_REG,
    MAX_PENDING_REMOTES,
    ROLE_OWNER,
    ROLE_REGULAR,
    SECTION_HASH_LEN,
    SHORT_ID_MAX,
    SHORT_ID_MIN,
    STORAGE_KEY,
    STORAGE_VERSION,
    TYPE_DEFS,
)

_LOGGER = logging.getLogger(LOGGER_REG)


class RoverRegistry:
    """Persistent registry for Rover protocol sections."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the registry."""
        self._store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self._data: dict[str, Any] = {}
        self._on_changed_cb: Callable[[str], None] | None = None
        self._qr_token: str | None = None
        self._next_short_id = SHORT_ID_MIN
        self._next_area_id = 1

    @staticmethod
    def _compute_hash(data: Any) -> str:
        """Compute canonical hash for data."""
        import json
        canonical = json.dumps(
            data, sort_keys=True, ensure_ascii=False, separators=(",", ":")
        )
        return hashlib.md5(canonical.encode("utf-8")).hexdigest()[:SECTION_HASH_LEN]

    async def async_load(self) -> None:
        """Load registry from store or create defaults."""
        loaded = await self._store.async_load()
        if loaded:
            self._data = loaded
            # Sync in-memory counters from _data
            self._next_short_id = self._data.get("_next_short_id", SHORT_ID_MIN)
            self._next_area_id = self._data.get("_next_area_id", 1)
        else:
            self._data = {
                "meta": {
                    "server_name": "Rover Hub",
                    "version": "0.0.1",
                    "tcp_port": DEFAULT_TCP_PORT,
                    "local_ip": "",
                    "ssid": "",
                    "_hash": "0000",
                },
                "users": [],
                "areas": [],
                "devices": [],
                "pending": [],
                "_hash_m": "0000",
                "_hash_u": "0000",
                "_hash_a": "0000",
                "_hash_d": "0000",
                "_next_short_id": self._next_short_id,
                "_next_area_id": self._next_area_id,
            }
        self._recalc_hashes()

    async def async_save(self) -> None:
        """Persist registry data to store."""
        await self._store.async_save(self._data)

    def _recalc_hashes(self) -> None:
        """Recalculate section hashes."""
        self._data["_hash_m"] = self._compute_hash(self._data["meta"])
        self._data["_hash_u"] = self._compute_hash(
            {"users": self._data["users"], "pending": self._data["pending"]}
        )
        self._data["_hash_a"] = self._compute_hash(self._data["areas"])
        self._data["_hash_d"] = self._compute_hash(self._data["devices"])

    def _on_changed(self, section: str) -> None:
        """Call change callback if set."""
        if self._on_changed_cb:
            self._on_changed_cb(section)

    def set_on_changed(self, callback: Callable[[str], None]) -> None:
        """Set change callback."""
        self._on_changed_cb = callback

    def get_on_changed(self) -> Callable[[str], None] | None:
        """Get change callback."""
        return self._on_changed_cb

    def set_qr_token(self, token: str) -> None:
        """Set QR auth token."""
        self._qr_token = token

    def consume_qr_token(self, token: str) -> bool:
        """Consume QR token if it matches."""
        if self._qr_token == token:
            self._qr_token = None
            return True
        _LOGGER.warning("QR token mismatch: got=%s expected=%s", token, self._qr_token)
        return False

    def _mutate(self, section: str, old_hash: str, new_hash: str, **kwargs) -> None:
        """Common mutation logic."""
        _LOGGER.info(
            "MUTATION %s: %s %s->%s",
            section.upper(),
            kwargs.get("action", "unknown"),
            old_hash,
            new_hash,
        )
        self._recalc_hashes()
        self._on_changed(section)
        # Note: async_save is called by individual methods

    # Meta section
    def get_meta(self) -> dict:
        """Get meta data."""
        return self._data["meta"].copy()

    async def set_server_name(self, name: str) -> None:
        """Set server name."""
        old_hash = self._data["meta"]["_hash"]
        self._data["meta"]["server_name"] = name
        new_hash = self._compute_hash(self._data["meta"])
        self._data["meta"]["_hash"] = new_hash
        self._mutate("m", old_hash, new_hash, action="set_server_name")
        await self.async_save()

    async def set_tcp_port(self, port: int) -> None:
        """Set TCP port."""
        old_hash = self._data["meta"]["_hash"]
        self._data["meta"]["tcp_port"] = port
        new_hash = self._compute_hash(self._data["meta"])
        self._data["meta"]["_hash"] = new_hash
        self._mutate("m", old_hash, new_hash, action="set_tcp_port")
        await self.async_save()

    async def set_local_ip(self, ip: str) -> None:
        """Set local IP."""
        old_hash = self._data["meta"]["_hash"]
        self._data["meta"]["local_ip"] = ip
        new_hash = self._compute_hash(self._data["meta"])
        self._data["meta"]["_hash"] = new_hash
        self._mutate("m", old_hash, new_hash, action="set_local_ip")
        await self.async_save()

    async def set_ssid(self, ssid: str) -> None:
        """Set SSID."""
        old_hash = self._data["meta"]["_hash"]
        self._data["meta"]["ssid"] = ssid
        new_hash = self._compute_hash(self._data["meta"])
        self._data["meta"]["_hash"] = new_hash
        self._mutate("m", old_hash, new_hash, action="set_ssid")
        await self.async_save()

    # Devices section
    async def add_device(
        self, entity_id: str, name: str, type_code: str, area_id: int | None = None
    ) -> int:
        """Add a device."""
        if type_code not in TYPE_DEFS:
            raise ValueError(f"Invalid type_code: {type_code}")
        if any(d["entity_id"] == entity_id for d in self._data["devices"]):
            raise ValueError(f"Duplicate entity_id: {entity_id}")

        short_id = self._next_short_id
        self._next_short_id += 1
        if self._next_short_id > SHORT_ID_MAX:
            self._next_short_id = SHORT_ID_MIN

        device = {
            "short_id": short_id,
            "entity_id": entity_id,
            "name": name,
            "type": type_code,
            "area_id": area_id,
            "enabled": True,
        }
        self._data["devices"].append(device)

        old_hash = self._data["_hash_d"]
        self._recalc_hashes()
        new_hash = self._data["_hash_d"]
        self._on_changed("d")
        self._data["_next_short_id"] = self._next_short_id
        await self.async_save()

        _LOGGER.info(
            "MUTATION add_device id=%s type=%s: d %s->%s",
            short_id,
            type_code,
            old_hash,
            new_hash,
        )

        return short_id

    async def remove_device(self, short_id: int) -> bool:
        """Remove a device."""
        for i, device in enumerate(self._data["devices"]):
            if device["short_id"] == short_id:
                del self._data["devices"][i]

                old_hash = self._data["_hash_d"]
                self._recalc_hashes()
                new_hash = self._data["_hash_d"]
                self._on_changed("d")
                await self.async_save()

                _LOGGER.info(
                    "MUTATION remove_device id=%s: d %s->%s",
                    short_id,
                    old_hash,
                    new_hash,
                )
                return True
        return False

    async def update_device(self, short_id: int, **kwargs) -> bool:
        """Update a device."""
        for device in self._data["devices"]:
            if device["short_id"] == short_id:
                old_hash = self._data["_hash_d"]
                for key, value in kwargs.items():
                    if key in device:
                        device[key] = value
                self._recalc_hashes()
                new_hash = self._data["_hash_d"]
                self._on_changed("d")
                await self.async_save()

                _LOGGER.info(
                    "MUTATION update_device id=%s: d %s->%s",
                    short_id,
                    old_hash,
                    new_hash,
                )
                return True
        return False

    def get_device(self, short_id: int) -> dict | None:
        """Get device by short_id."""
        for device in self._data["devices"]:
            if device["short_id"] == short_id:
                return device.copy()
        return None

    def get_device_by_entity_id(self, entity_id: str) -> dict | None:
        """Get device by entity_id."""
        for device in self._data["devices"]:
            if device["entity_id"] == entity_id:
                return device.copy()
        return None

    def all_devices(self) -> list[dict]:
        """Get all devices."""
        return [d.copy() for d in self._data["devices"]]

    # Areas section
    async def add_area(self, name: str) -> int:
        """Add an area."""
        area_id = self._next_area_id
        self._next_area_id += 1

        area = {"id": area_id, "name": name}
        self._data["areas"].append(area)

        old_hash = self._data["_hash_a"]
        self._recalc_hashes()
        new_hash = self._data["_hash_a"]
        self._on_changed("a")
        self._data["_next_area_id"] = self._next_area_id
        await self.async_save()

        _LOGGER.info(
            "MUTATION add_area id=%s: a %s->%s",
            area_id,
            old_hash,
            new_hash,
        )

        return area_id

    def get_area(self, area_id: int) -> dict | None:
        """Get area by id."""
        for area in self._data["areas"]:
            if area["id"] == area_id:
                return area.copy()
        return None

    def all_areas(self) -> list[dict]:
        """Get all areas."""
        return [a.copy() for a in self._data["areas"]]

    # Pending remotes section
    async def add_pending(self, identity_hash: str, name: str, requested_at: int | None = None) -> bool:
        """Add a pending remote."""
        if len(self._data["pending"]) >= MAX_PENDING_REMOTES:
            return False
        if any(p["hash"] == identity_hash for p in self._data["pending"]):
            return False
        if any(u["hash"] == identity_hash for u in self._data["users"]):
            return False

        pending = {
            "hash": identity_hash,
            "name": name,
            "requested_at": requested_at or 0,
        }
        self._data["pending"].append(pending)

        old_hash = self._data["_hash_u"]
        self._recalc_hashes()
        new_hash = self._data["_hash_u"]
        self._on_changed("u")
        await self.async_save()

        _LOGGER.info(
            "MUTATION add_pending hash=%s: u %s->%s",
            identity_hash,
            old_hash,
            new_hash,
        )

        return True

    def all_pending(self) -> list[dict]:
        """Get all pending remotes."""
        return [p.copy() for p in self._data["pending"]]

    # Users section
    async def approve_pending(self, identity_hash: str, role: str = ROLE_REGULAR) -> bool:
        """Approve a pending remote."""
        for i, pending in enumerate(self._data["pending"]):
            if pending["hash"] == identity_hash:
                user = {
                    "hash": identity_hash,
                    "name": pending["name"],
                    "role": role,
                }
                if len(self._data["users"]) == 0:
                    user["role"] = ROLE_OWNER

                self._data["users"].append(user)
                del self._data["pending"][i]

                old_hash = self._data["_hash_u"]
                self._recalc_hashes()
                new_hash = self._data["_hash_u"]
                self._on_changed("u")
                await self.async_save()

                _LOGGER.info(
                    "MUTATION approve_pending hash=%s: u %s->%s",
                    identity_hash,
                    old_hash,
                    new_hash,
                )
                return True
        return False

    async def revoke_user(self, identity_hash: str) -> bool:
        """Revoke a user."""
        for i, user in enumerate(self._data["users"]):
            if user["hash"] == identity_hash:
                del self._data["users"][i]

                old_hash = self._data["_hash_u"]
                self._recalc_hashes()
                new_hash = self._data["_hash_u"]
                self._on_changed("u")
                await self.async_save()

                _LOGGER.info(
                    "MUTATION revoke_user hash=%s: u %s->%s",
                    identity_hash,
                    old_hash,
                    new_hash,
                )
                return True
        return False

    def get_user(self, identity_hash: str) -> dict | None:
        """Get user by hash."""
        for user in self._data["users"]:
            if user["hash"] == identity_hash:
                return user.copy()
        return None

    def is_approved(self, identity_hash: str) -> bool:
        """Check if user is approved."""
        return any(u["hash"] == identity_hash for u in self._data["users"])

    def all_users(self) -> list[dict]:
        """Get all users."""
        return [u.copy() for u in self._data["users"]]

    # Hashes
    def get_hashes(self) -> dict[str, str]:
        """Get section hashes."""
        return {
            "m": self._data["_hash_m"],
            "u": self._data["_hash_u"],
            "a": self._data["_hash_a"],
            "d": self._data["_hash_d"],
        }
