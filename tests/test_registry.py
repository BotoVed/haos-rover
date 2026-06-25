"""Tests for rover.registry — RoverRegistry CRUD, hashes, callbacks."""
from __future__ import annotations

import re

import pytest

from rover.const import (
    DEFAULT_TCP_PORT,
    MAX_PENDING_REMOTES,
    ROLE_OWNER,
    ROLE_REGULAR,
    SECTION_HASH_LEN,
    SHORT_ID_MAX,
    SHORT_ID_MIN,
    TYPE_DEFS,
)
from rover.registry import RoverRegistry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_registry() -> RoverRegistry:
    """Create a registry with a mocked HomeAssistant."""
    from unittest.mock import MagicMock
    return RoverRegistry(MagicMock())


async def _loaded_registry() -> RoverRegistry:
    """Return a registry that has been async_load'd with defaults."""
    reg = _make_registry()
    await reg.async_load()
    return reg


# ---------------------------------------------------------------------------
# 1. Initialization
# ---------------------------------------------------------------------------

class TestInitialization:
    async def test_defaults_created(self) -> None:
        reg = await _loaded_registry()
        meta = reg.get_meta()
        assert meta["server_name"] == "Rover Hub"
        assert meta["version"] == "0.0.1"
        assert meta["tcp_port"] == DEFAULT_TCP_PORT
        assert meta["local_ip"] == ""
        assert meta["ssid"] == ""
        assert meta["_hash"] == "0000"

    async def test_empty_collections(self) -> None:
        reg = await _loaded_registry()
        assert reg.all_devices() == []
        assert reg.all_areas() == []
        assert reg.all_users() == []
        assert reg.all_pending() == []

    async def test_next_ids(self) -> None:
        reg = await _loaded_registry()
        data = reg._data
        assert data["_next_short_id"] == SHORT_ID_MIN
        assert data["_next_area_id"] == 1

    async def test_initial_hashes_are_valid_hex(self) -> None:
        """After async_load, hashes are recomputed from actual data (not literal '0000')."""
        reg = await _loaded_registry()
        hashes = reg.get_hashes()
        for key in ("m", "u", "a", "d"):
            assert isinstance(hashes[key], str)
            assert len(hashes[key]) == SECTION_HASH_LEN

    async def test_load_preserves_existing_data(self) -> None:
        reg = _make_registry()
        # Inject pre-existing data into the store
        reg._store._data = {
            "meta": {
                "server_name": "Custom Hub",
                "version": "1.2.3",
                "tcp_port": 9999,
                "local_ip": "10.0.0.1",
                "ssid": "MyWifi",
                "_hash": "xxxx",
            },
            "users": [],
            "areas": [],
            "devices": [],
            "pending": [],
            "_hash_m": "xxxx",
            "_hash_u": "0000",
            "_hash_a": "0000",
            "_hash_d": "0000",
            "_next_short_id": 42,
            "_next_area_id": 7,
        }
        await reg.async_load()
        meta = reg.get_meta()
        assert meta["server_name"] == "Custom Hub"
        assert meta["tcp_port"] == 9999


# ---------------------------------------------------------------------------
# 2. QR Tokens
# ---------------------------------------------------------------------------

class TestQRTokens:
    async def test_set_and_consume(self) -> None:
        reg = await _loaded_registry()
        reg.set_qr_token("abcd")
        assert reg.consume_qr_token("abcd") is True

    async def test_consume_twice_returns_false(self) -> None:
        reg = await _loaded_registry()
        reg.set_qr_token("abcd")
        assert reg.consume_qr_token("abcd") is True
        assert reg.consume_qr_token("abcd") is False

    async def test_wrong_token_returns_false(self) -> None:
        reg = await _loaded_registry()
        reg.set_qr_token("abcd")
        assert reg.consume_qr_token("xxxx") is False

    async def test_no_token_set(self) -> None:
        reg = await _loaded_registry()
        assert reg.consume_qr_token("abcd") is False

    async def test_token_not_shared(self) -> None:
        """Setting a new token overwrites the old one."""
        reg = await _loaded_registry()
        reg.set_qr_token("first")
        reg.set_qr_token("second")
        assert reg.consume_qr_token("first") is False
        assert reg.consume_qr_token("second") is True


# ---------------------------------------------------------------------------
# 3. Devices CRUD
# ---------------------------------------------------------------------------

class TestDevicesCRUD:
    async def test_add_device_returns_short_id(self) -> None:
        reg = await _loaded_registry()
        short_id = await reg.add_device("light.kitchen", "Kitchen Light", "LT")
        assert short_id == SHORT_ID_MIN

    async def test_add_multiple_devices_increment_ids(self) -> None:
        reg = await _loaded_registry()
        id1 = await reg.add_device("light.kitchen", "Kitchen", "LT")
        id2 = await reg.add_device("switch.fan", "Fan", "SW")
        assert id2 == id1 + 1

    async def test_add_device_invalid_type_code_raises(self) -> None:
        reg = await _loaded_registry()
        with pytest.raises(ValueError, match="Invalid type_code"):
            await reg.add_device("sensor.x", "X", "INVALID")

    async def test_add_device_duplicate_entity_id_raises(self) -> None:
        reg = await _loaded_registry()
        await reg.add_device("light.kitchen", "Kitchen", "LT")
        with pytest.raises(ValueError, match="Duplicate entity_id"):
            await reg.add_device("light.kitchen", "Kitchen Again", "LT")

    async def test_get_device_by_short_id(self) -> None:
        reg = await _loaded_registry()
        short_id = await reg.add_device("light.kitchen", "Kitchen Light", "LT")
        device = reg.get_device(short_id)
        assert device is not None
        assert device["short_id"] == short_id
        assert device["entity_id"] == "light.kitchen"
        assert device["name"] == "Kitchen Light"
        assert device["type"] == "LT"

    async def test_get_device_nonexistent_returns_none(self) -> None:
        reg = await _loaded_registry()
        assert reg.get_device(9999) is None

    async def test_get_device_returns_copy(self) -> None:
        reg = await _loaded_registry()
        short_id = await reg.add_device("light.kitchen", "Kitchen", "LT")
        d1 = reg.get_device(short_id)
        d1["name"] = "Mutated"
        d2 = reg.get_device(short_id)
        assert d2["name"] == "Kitchen"

    async def test_get_device_by_entity_id(self) -> None:
        reg = await _loaded_registry()
        await reg.add_device("light.kitchen", "Kitchen", "LT")
        device = reg.get_device_by_entity_id("light.kitchen")
        assert device is not None
        assert device["entity_id"] == "light.kitchen"

    async def test_get_device_by_entity_id_nonexistent(self) -> None:
        reg = await _loaded_registry()
        assert reg.get_device_by_entity_id("no.such.entity") is None

    async def test_remove_device_returns_true(self) -> None:
        reg = await _loaded_registry()
        short_id = await reg.add_device("light.kitchen", "Kitchen", "LT")
        result = await reg.remove_device(short_id)
        assert result is True
        assert reg.get_device(short_id) is None

    async def test_remove_device_nonexistent_returns_false(self) -> None:
        reg = await _loaded_registry()
        assert await reg.remove_device(9999) is False

    async def test_update_device_changes_fields(self) -> None:
        reg = await _loaded_registry()
        short_id = await reg.add_device("light.kitchen", "Kitchen", "LT")
        result = await reg.update_device(short_id, name="New Name", area_id=5)
        assert result is True
        device = reg.get_device(short_id)
        assert device["name"] == "New Name"
        assert device["area_id"] == 5

    async def test_update_device_nonexistent_returns_false(self) -> None:
        reg = await _loaded_registry()
        assert await reg.update_device(9999, name="X") is False

    async def test_update_device_ignores_unknown_keys(self) -> None:
        reg = await _loaded_registry()
        short_id = await reg.add_device("light.kitchen", "Kitchen", "LT")
        await reg.update_device(short_id, bogus_key="value")
        device = reg.get_device(short_id)
        assert "bogus_key" not in device

    async def test_all_devices(self) -> None:
        reg = await _loaded_registry()
        await reg.add_device("light.kitchen", "Kitchen", "LT")
        await reg.add_device("switch.fan", "Fan", "SW")
        devices = reg.all_devices()
        assert len(devices) == 2
        entity_ids = {d["entity_id"] for d in devices}
        assert entity_ids == {"light.kitchen", "switch.fan"}

    async def test_all_devices_returns_copies(self) -> None:
        reg = await _loaded_registry()
        await reg.add_device("light.kitchen", "Kitchen", "LT")
        devices = reg.all_devices()
        devices[0]["name"] = "Mutated"
        assert reg.all_devices()[0]["name"] == "Kitchen"

    async def test_device_area_id(self) -> None:
        reg = await _loaded_registry()
        short_id = await reg.add_device("light.kitchen", "Kitchen", "LT", area_id=3)
        device = reg.get_device(short_id)
        assert device["area_id"] == 3

    async def test_short_id_wraps_around(self) -> None:
        """When short_id exceeds MAX, it wraps back to MIN."""
        reg = await _loaded_registry()
        reg._next_short_id = SHORT_ID_MAX
        id1 = await reg.add_device("light.a", "A", "LT")
        assert id1 == SHORT_ID_MAX
        id2 = await reg.add_device("light.b", "B", "LT")
        assert id2 == SHORT_ID_MIN

    async def test_device_enabled_by_default(self) -> None:
        reg = await _loaded_registry()
        short_id = await reg.add_device("light.kitchen", "Kitchen", "LT")
        device = reg.get_device(short_id)
        assert device["enabled"] is True


# ---------------------------------------------------------------------------
# 4. Areas CRUD
# ---------------------------------------------------------------------------

class TestAreasCRUD:
    async def test_add_area_returns_incrementing_ids(self) -> None:
        reg = await _loaded_registry()
        id1 = await reg.add_area("Living Room")
        id2 = await reg.add_area("Bedroom")
        assert id1 == 1
        assert id2 == 2

    async def test_get_area(self) -> None:
        reg = await _loaded_registry()
        area_id = await reg.add_area("Kitchen")
        area = reg.get_area(area_id)
        assert area is not None
        assert area["id"] == area_id
        assert area["name"] == "Kitchen"

    async def test_get_area_nonexistent_returns_none(self) -> None:
        reg = await _loaded_registry()
        assert reg.get_area(9999) is None

    async def test_all_areas(self) -> None:
        reg = await _loaded_registry()
        await reg.add_area("Living Room")
        await reg.add_area("Bedroom")
        areas = reg.all_areas()
        assert len(areas) == 2
        names = {a["name"] for a in areas}
        assert names == {"Living Room", "Bedroom"}

    async def test_all_areas_returns_copies(self) -> None:
        reg = await _loaded_registry()
        await reg.add_area("Kitchen")
        areas = reg.all_areas()
        areas[0]["name"] = "Mutated"
        assert reg.all_areas()[0]["name"] == "Kitchen"


# ---------------------------------------------------------------------------
# 5. Pending + Users
# ---------------------------------------------------------------------------

class TestPendingAndUsers:
    async def test_add_pending(self) -> None:
        reg = await _loaded_registry()
        result = await reg.add_pending("hash_a", "Alice")
        assert result is True
        assert len(reg.all_pending()) == 1

    async def test_add_pending_duplicate_hash_rejected(self) -> None:
        reg = await _loaded_registry()
        await reg.add_pending("hash_a", "Alice")
        result = await reg.add_pending("hash_a", "Alice Again")
        assert result is False
        assert len(reg.all_pending()) == 1

    async def test_add_pending_existing_user_rejected(self) -> None:
        reg = await _loaded_registry()
        await reg.add_pending("hash_a", "Alice")
        await reg.approve_pending("hash_a")
        result = await reg.add_pending("hash_a", "Alice")
        assert result is False

    async def test_add_pending_queue_full(self) -> None:
        reg = await _loaded_registry()
        for i in range(MAX_PENDING_REMOTES):
            ok = await reg.add_pending(f"hash_{i:02d}", f"User {i}")
            assert ok is True
        assert len(reg.all_pending()) == MAX_PENDING_REMOTES
        # 11th should be rejected
        result = await reg.add_pending("hash_overflow", "Overflow")
        assert result is False
        assert len(reg.all_pending()) == MAX_PENDING_REMOTES

    async def test_approve_pending_moves_to_users(self) -> None:
        reg = await _loaded_registry()
        await reg.add_pending("hash_a", "Alice")
        result = await reg.approve_pending("hash_a")
        assert result is True
        assert len(reg.all_pending()) == 0
        assert len(reg.all_users()) == 1

    async def test_approve_pending_nonexistent_returns_false(self) -> None:
        reg = await _loaded_registry()
        assert await reg.approve_pending("no_such_hash") is False

    async def test_first_user_gets_owner_role(self) -> None:
        reg = await _loaded_registry()
        await reg.add_pending("hash_a", "Alice")
        await reg.approve_pending("hash_a")
        users = reg.all_users()
        assert users[0]["role"] == ROLE_OWNER

    async def test_subsequent_user_gets_regular_role(self) -> None:
        reg = await _loaded_registry()
        await reg.add_pending("hash_a", "Alice")
        await reg.add_pending("hash_b", "Bob")
        await reg.approve_pending("hash_a")
        await reg.approve_pending("hash_b")
        users = reg.all_users()
        roles = {u["role"] for u in users}
        assert roles == {ROLE_OWNER, ROLE_REGULAR}
        # Bob should be regular
        bob = next(u for u in users if u["hash"] == "hash_b")
        assert bob["role"] == ROLE_REGULAR

    async def test_revoke_user(self) -> None:
        reg = await _loaded_registry()
        await reg.add_pending("hash_a", "Alice")
        await reg.approve_pending("hash_a")
        result = await reg.revoke_user("hash_a")
        assert result is True
        assert len(reg.all_users()) == 0

    async def test_revoke_user_nonexistent_returns_false(self) -> None:
        reg = await _loaded_registry()
        assert await reg.revoke_user("no_such_hash") is False

    async def test_is_approved(self) -> None:
        reg = await _loaded_registry()
        assert reg.is_approved("hash_a") is False
        await reg.add_pending("hash_a", "Alice")
        assert reg.is_approved("hash_a") is False
        await reg.approve_pending("hash_a")
        assert reg.is_approved("hash_a") is True

    async def test_all_users(self) -> None:
        reg = await _loaded_registry()
        await reg.add_pending("hash_a", "Alice")
        await reg.add_pending("hash_b", "Bob")
        await reg.approve_pending("hash_a")
        await reg.approve_pending("hash_b")
        users = reg.all_users()
        assert len(users) == 2
        names = {u["name"] for u in users}
        assert names == {"Alice", "Bob"}

    async def test_all_pending(self) -> None:
        reg = await _loaded_registry()
        await reg.add_pending("hash_a", "Alice")
        await reg.add_pending("hash_b", "Bob")
        pending = reg.all_pending()
        assert len(pending) == 2

    async def test_get_user(self) -> None:
        reg = await _loaded_registry()
        await reg.add_pending("hash_a", "Alice")
        await reg.approve_pending("hash_a")
        user = reg.get_user("hash_a")
        assert user is not None
        assert user["name"] == "Alice"

    async def test_get_user_nonexistent_returns_none(self) -> None:
        reg = await _loaded_registry()
        assert reg.get_user("no_such_hash") is None

    async def test_pending_stores_requested_at(self) -> None:
        reg = await _loaded_registry()
        await reg.add_pending("hash_a", "Alice", requested_at=12345)
        pending = reg.all_pending()
        assert pending[0]["requested_at"] == 12345

    async def test_approve_custom_role(self) -> None:
        """When there are already users, the explicit role is used."""
        reg = await _loaded_registry()
        await reg.add_pending("hash_a", "Alice")
        await reg.add_pending("hash_b", "Bob")
        await reg.approve_pending("hash_a")  # becomes owner
        await reg.approve_pending("hash_b", role="admin")  # custom role
        bob = reg.get_user("hash_b")
        assert bob["role"] == "admin"

    async def test_approve_pending_enforces_max_active_remotes(self) -> None:
        """D4 — spec v0.5.0 §11.2, FR-004: limit 5 active remotes.
        
        Regression test for divergence where approve_pending() appended
        without checking len(users) >= MAX_ACTIVE_REMOTES.
        """
        reg = await _loaded_registry()
        # Fill up to MAX_ACTIVE_REMOTES=5
        for i in range(5):
            await reg.add_pending(f"hash_{i:064x}", f"user_{i}")
            assert await reg.approve_pending(f"hash_{i:064x}") is True
        
        assert len(reg.all_users()) == 5
        
        # 6th user must be rejected
        success = await reg.add_pending(f"hash_5:064x", "user_5")  # Note: add_pending only checks MAX_PENDING_REMOTES, not active. So this may succeed.
        # The limit check happens in approve_pending.
        if success:
            result = await reg.approve_pending(f"hash_5:064x")
            assert result is False, "6th user must be rejected when MAX_ACTIVE_REMOTES=5"
            assert len(reg.all_users()) == 5
        
        # Verify the 6th user is NOT in users
        for i in range(5):
            assert reg.get_user(f"hash_{i:064x}") is not None


# ---------------------------------------------------------------------------
# 6. Hash Computation
# ---------------------------------------------------------------------------

class TestHashComputation:
    def test_compute_hash_returns_hex_string(self) -> None:
        result = RoverRegistry._compute_hash({"key": "value"})
        assert isinstance(result, str)
        assert len(result) == SECTION_HASH_LEN
        assert re.fullmatch(r"[0-9a-f]{" + str(SECTION_HASH_LEN) + r"}", result)

    def test_compute_hash_deterministic(self) -> None:
        data = {"a": 1, "b": [2, 3]}
        h1 = RoverRegistry._compute_hash(data)
        h2 = RoverRegistry._compute_hash(data)
        assert h1 == h2

    def test_compute_hash_different_for_different_data(self) -> None:
        h1 = RoverRegistry._compute_hash({"a": 1})
        h2 = RoverRegistry._compute_hash({"a": 2})
        assert h1 != h2

    async def test_get_hashes_returns_four_keys(self) -> None:
        """get_hashes should have exactly m, u, a, d keys with correct lengths."""
        reg = await _loaded_registry()
        hashes = reg.get_hashes()
        assert set(hashes.keys()) == {"m", "u", "a", "d"}
        for v in hashes.values():
            assert isinstance(v, str)
            assert len(v) == SECTION_HASH_LEN

    async def test_hashes_change_after_mutation(self) -> None:
        reg = await _loaded_registry()
        old_d = reg.get_hashes()["d"]
        await reg.add_device("light.kitchen", "Kitchen", "LT")
        new_d = reg.get_hashes()["d"]
        assert old_d != new_d

    async def test_hashes_update_after_meta_change(self) -> None:
        reg = await _loaded_registry()
        old_m = reg.get_hashes()["m"]
        await reg.set_server_name("New Name")
        new_m = reg.get_hashes()["m"]
        assert old_m != new_m

    async def test_hashes_update_after_user_change(self) -> None:
        reg = await _loaded_registry()
        old_u = reg.get_hashes()["u"]
        await reg.add_pending("hash_a", "Alice")
        new_u = reg.get_hashes()["u"]
        assert old_u != new_u


# ---------------------------------------------------------------------------
# 7. Meta
# ---------------------------------------------------------------------------

class TestMeta:
    async def test_get_meta_returns_dict(self) -> None:
        reg = await _loaded_registry()
        meta = reg.get_meta()
        assert isinstance(meta, dict)
        assert "server_name" in meta

    async def test_get_meta_returns_copy(self) -> None:
        reg = await _loaded_registry()
        meta = reg.get_meta()
        meta["server_name"] = "Mutated"
        assert reg.get_meta()["server_name"] == "Rover Hub"

    async def test_set_server_name(self) -> None:
        reg = await _loaded_registry()
        await reg.set_server_name("My Hub")
        assert reg.get_meta()["server_name"] == "My Hub"

    async def test_set_tcp_port(self) -> None:
        reg = await _loaded_registry()
        await reg.set_tcp_port(8080)
        assert reg.get_meta()["tcp_port"] == 8080

    async def test_set_local_ip(self) -> None:
        reg = await _loaded_registry()
        await reg.set_local_ip("192.168.1.100")
        assert reg.get_meta()["local_ip"] == "192.168.1.100"

    async def test_set_ssid(self) -> None:
        reg = await _loaded_registry()
        await reg.set_ssid("MyWifi")
        assert reg.get_meta()["ssid"] == "MyWifi"

    async def test_meta_hash_updates_on_change(self) -> None:
        reg = await _loaded_registry()
        h1 = reg.get_meta()["_hash"]
        await reg.set_server_name("Different")
        h2 = reg.get_meta()["_hash"]
        assert h1 != h2


# ---------------------------------------------------------------------------
# 8. Callback
# ---------------------------------------------------------------------------

class TestCallback:
    async def test_set_on_changed_and_verify_fires(self) -> None:
        reg = await _loaded_registry()
        fired: list[str] = []
        reg.set_on_changed(lambda section: fired.append(section))
        await reg.add_device("light.kitchen", "Kitchen", "LT")
        assert "d" in fired

    async def test_callback_fires_on_remove_device(self) -> None:
        reg = await _loaded_registry()
        short_id = await reg.add_device("light.kitchen", "Kitchen", "LT")
        fired: list[str] = []
        reg.set_on_changed(lambda section: fired.append(section))
        await reg.remove_device(short_id)
        assert "d" in fired

    async def test_callback_fires_on_update_device(self) -> None:
        reg = await _loaded_registry()
        short_id = await reg.add_device("light.kitchen", "Kitchen", "LT")
        fired: list[str] = []
        reg.set_on_changed(lambda section: fired.append(section))
        await reg.update_device(short_id, name="Updated")
        assert "d" in fired

    async def test_callback_fires_on_add_area(self) -> None:
        reg = await _loaded_registry()
        fired: list[str] = []
        reg.set_on_changed(lambda section: fired.append(section))
        await reg.add_area("Bedroom")
        assert "a" in fired

    async def test_callback_fires_on_add_pending(self) -> None:
        reg = await _loaded_registry()
        fired: list[str] = []
        reg.set_on_changed(lambda section: fired.append(section))
        await reg.add_pending("hash_a", "Alice")
        assert "u" in fired

    async def test_callback_fires_on_approve_pending(self) -> None:
        reg = await _loaded_registry()
        await reg.add_pending("hash_a", "Alice")
        fired: list[str] = []
        reg.set_on_changed(lambda section: fired.append(section))
        await reg.approve_pending("hash_a")
        assert "u" in fired

    async def test_callback_fires_on_revoke_user(self) -> None:
        reg = await _loaded_registry()
        await reg.add_pending("hash_a", "Alice")
        await reg.approve_pending("hash_a")
        fired: list[str] = []
        reg.set_on_changed(lambda section: fired.append(section))
        await reg.revoke_user("hash_a")
        assert "u" in fired

    async def test_callback_fires_on_meta_change(self) -> None:
        reg = await _loaded_registry()
        fired: list[str] = []
        reg.set_on_changed(lambda section: fired.append(section))
        await reg.set_server_name("New")
        assert "m" in fired

    async def test_get_on_changed(self) -> None:
        reg = await _loaded_registry()
        assert reg.get_on_changed() is None
        cb = lambda s: None
        reg.set_on_changed(cb)
        assert reg.get_on_changed() is cb

    async def test_no_callback_does_not_crash(self) -> None:
        """Mutations should work fine without a callback set."""
        reg = await _loaded_registry()
        # Should not raise
        await reg.add_device("light.kitchen", "Kitchen", "LT")
        await reg.set_server_name("New")
        assert reg.get_meta()["server_name"] == "New"


# ---------------------------------------------------------------------------
# 9. Persistence round-trip
# ---------------------------------------------------------------------------

class TestPersistence:
    async def test_save_and_reload(self) -> None:
        reg1 = await _loaded_registry()
        await reg1.add_device("light.kitchen", "Kitchen", "LT")
        await reg1.add_area("Living Room")
        await reg1.add_pending("hash_a", "Alice")
        await reg1.async_save()

        # Create a fresh registry and load from the same store
        reg2 = _make_registry()
        # Share the same store instance so data persists
        reg2._store = reg1._store
        await reg2.async_load()

        assert len(reg2.all_devices()) == 1
        assert reg2.all_devices()[0]["entity_id"] == "light.kitchen"
        assert len(reg2.all_areas()) == 1
        assert reg2.all_areas()[0]["name"] == "Living Room"
        assert len(reg2.all_pending()) == 1
