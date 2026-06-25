"""Tests for rover.handlers — RoverHandlers message handlers."""
from __future__ import annotations

import sys
import types
from unittest.mock import ANY, AsyncMock, MagicMock, call, patch

import pytest

# ── ServiceTarget stub ─────────────────────────────────────────────────────────
# handlers.py does: from homeassistant.helpers.service import ServiceTarget
# conftest.py already stubs homeassistant.helpers as an empty module, but
# homeassistant.helpers.service is not set up there.  Add it here so the
# import in handlers.py does not fail at collection time.
if "homeassistant.helpers.service" not in sys.modules:
    _service_mod = types.ModuleType("homeassistant.helpers.service")
    _service_mod.ServiceTarget = MagicMock  # class, not instance
    sys.modules["homeassistant.helpers.service"] = _service_mod

from custom_components.rover.const import (
    TP_CMD,
    TP_CONFIG,
    TP_FORBIDDEN,
    TP_PING_PONG,
    TP_REGISTER,
    TP_REQ,
    TP_STATUS,
)
from custom_components.rover.handlers import RoverHandlers


# =========================================================================
# Fixtures
# =========================================================================


@pytest.fixture
def mock_hass():
    """Return a mocked HomeAssistant with services and states."""
    hass = MagicMock()
    hass.states = MagicMock()
    hass.states.get = MagicMock()
    hass.services = MagicMock()
    hass.services.async_call = AsyncMock()
    return hass


@pytest.fixture
def mock_registry():
    """Return a mocked RoverRegistry with async-aware methods."""
    registry = MagicMock()
    # These are awaited in _handle_register after the bug fix
    registry.add_pending = AsyncMock()
    registry.approve_pending = AsyncMock()
    registry.deny_pending = AsyncMock()
    registry.get_hashes.return_value = {
        "m": "0000",
        "u": "0000",
        "a": "0000",
        "d": "0000",
    }
    return registry


@pytest.fixture
def mock_transport():
    """Return a mocked transport (async .send)."""
    transport = MagicMock()
    transport.send = AsyncMock()
    return transport


@pytest.fixture
def mock_dispatcher():
    """Return a mocked RoverDispatcher."""
    return MagicMock()


@pytest.fixture
def handlers(mock_hass, mock_registry, mock_transport, mock_dispatcher):
    """Return a RoverHandlers instance wired to the mocks above."""
    return RoverHandlers(mock_hass, mock_registry, mock_transport, mock_dispatcher)


@pytest.fixture(autouse=True)
def _mock_deps():
    """Mock build_service_call and extract_state for all tests.

    These modules are imported by handlers.py — patching at the module
    level isolates handler logic from the pure-function implementations.
    """
    with patch("custom_components.rover.handlers.build_service_call") as m_bsc:
        with patch("custom_components.rover.handlers.extract_state") as m_es:
            yield {"build_service_call": m_bsc, "extract_state": m_es}


@pytest.fixture
def mock_build_service_call(_mock_deps):
    """Convenience accessor for the mocked build_service_call."""
    return _mock_deps["build_service_call"]


@pytest.fixture
def mock_extract_state(_mock_deps):
    """Convenience accessor for the mocked extract_state."""
    return _mock_deps["extract_state"]


# =========================================================================
# 1. register()
# =========================================================================


class TestRegister:
    """RoverHandlers.register() registers all four message-type handlers."""

    def test_registers_all_four_handlers(self, handlers, mock_dispatcher):
        handlers.register()

        assert mock_dispatcher.register_handler.call_count == 4

        expected = [
            call(TP_CMD, handlers._handle_cmd),
            call(TP_PING_PONG, handlers._handle_ping),
            call(TP_REQ, handlers._handle_req),
            call(TP_REGISTER, handlers._handle_register),
        ]
        mock_dispatcher.register_handler.assert_has_calls(expected, any_order=False)

    def test_registers_correct_handler_types(self, handlers, mock_dispatcher):
        handlers.register()

        registered_tps = {
            c[0][0] for c in mock_dispatcher.register_handler.call_args_list
        }
        assert registered_tps == {TP_CMD, TP_PING_PONG, TP_REQ, TP_REGISTER}


# =========================================================================
# 2. CMD handler
# =========================================================================


class TestCmd:
    """_handle_cmd — device command execution."""

    SRC = b"\xab\xcd"
    SRC_HASH = "abcd"

    async def test_unauthorized_sends_forbidden(
        self, handlers, mock_registry, mock_transport
    ):
        mock_registry.is_approved.return_value = False

        await handlers._handle_cmd(self.SRC, {"id": 1})

        mock_registry.is_approved.assert_called_once_with(self.SRC_HASH)
        mock_transport.send.assert_called_once_with(
            self.SRC_HASH, {"tp": TP_FORBIDDEN, "reason": "unauthorized"}
        )

    async def test_authorized_but_device_not_found(
        self, handlers, mock_registry, mock_transport
    ):
        mock_registry.is_approved.return_value = True
        mock_registry.get_device.return_value = None

        await handlers._handle_cmd(self.SRC, {"id": 999})

        mock_registry.get_device.assert_called_once_with(999)
        mock_transport.send.assert_called_once_with(
            self.SRC_HASH, {"tp": TP_FORBIDDEN, "reason": "device_not_found"}
        )

    async def test_authorized_device_found_executes_service(
        self,
        handlers,
        mock_hass,
        mock_registry,
        mock_transport,
        mock_build_service_call,
    ):
        mock_registry.is_approved.return_value = True
        mock_registry.get_device.return_value = {
            "short_id": 1,
            "entity_id": "switch.test",
            "type": "SW",
            "name": "Test Switch",
            "area_id": None,
            "enabled": True,
        }
        mock_build_service_call.return_value = [("switch", "turn_on", {})]

        await handlers._handle_cmd(self.SRC, {"id": 1, "s": True})

        mock_registry.get_device.assert_called_once_with(1)
        mock_build_service_call.assert_called_once_with(
            "SW", {"id": 1, "s": True}
        )
        mock_hass.services.async_call.assert_awaited_once()
        args, kwargs = mock_hass.services.async_call.call_args
        assert args == ("switch", "turn_on", {})
        assert kwargs["blocking"] is True
        # target is a dict with entity_id list
        assert kwargs["target"] == {"entity_id": ["switch.test"]}
        mock_transport.send.assert_not_called()

    async def test_multiple_service_calls(
        self,
        handlers,
        mock_hass,
        mock_registry,
        mock_transport,
        mock_build_service_call,
    ):
        """A CMD that produces multiple service tuples runs them sequentially."""
        mock_registry.is_approved.return_value = True
        mock_registry.get_device.return_value = {
            "short_id": 2,
            "entity_id": "fan.test",
            "type": "FN",
            "name": "Test Fan",
            "area_id": None,
            "enabled": True,
        }
        mock_build_service_call.return_value = [
            ("fan", "turn_on", {}),
            ("fan", "set_percentage", {"percentage": 50}),
        ]

        await handlers._handle_cmd(self.SRC, {"id": 2, "s": True, "sp": 50})

        assert mock_hass.services.async_call.await_count == 2
        first_args, first_kwargs = mock_hass.services.async_call.await_args_list[0]
        assert first_args == ("fan", "turn_on", {})
        second_args, second_kwargs = mock_hass.services.async_call.await_args_list[1]
        assert second_args == ("fan", "set_percentage", {"percentage": 50})

    async def test_service_call_exception_sends_command_failed(
        self,
        handlers,
        mock_hass,
        mock_registry,
        mock_transport,
        mock_build_service_call,
    ):
        mock_registry.is_approved.return_value = True
        mock_registry.get_device.return_value = {
            "short_id": 1,
            "entity_id": "switch.test",
            "type": "SW",
            "name": "Test",
            "area_id": None,
            "enabled": True,
        }
        mock_build_service_call.return_value = [("switch", "turn_on", {})]
        mock_hass.services.async_call.side_effect = Exception("boom")

        await handlers._handle_cmd(self.SRC, {"id": 1, "s": True})

        mock_transport.send.assert_called_once_with(
            self.SRC_HASH, {"tp": TP_FORBIDDEN, "reason": "command_failed"}
        )

    async def test_missing_device_id_gets_none_returns_device_not_found(
        self, handlers, mock_registry, mock_transport
    ):
        """When fields has no 'id' key, get_device(None) returns None."""
        mock_registry.is_approved.return_value = True
        mock_registry.get_device.return_value = None

        await handlers._handle_cmd(self.SRC, {"s": True})

        mock_registry.get_device.assert_called_once_with(None)
        mock_transport.send.assert_called_once_with(
            self.SRC_HASH, {"tp": TP_FORBIDDEN, "reason": "device_not_found"}
        )


# =========================================================================
# 3. PING handler
# =========================================================================


class TestPing:
    """_handle_ping — heartbeat / hash comparison."""

    SRC = b"\xab\xcd"
    SRC_HASH = "abcd"

    async def test_unauthorized_sends_forbidden(
        self, handlers, mock_registry, mock_transport
    ):
        mock_registry.is_approved.return_value = False

        await handlers._handle_ping(self.SRC, {})

        mock_transport.send.assert_called_once_with(
            self.SRC_HASH, {"tp": TP_FORBIDDEN, "reason": "unauthorized"}
        )

    async def test_matching_hashes_sends_empty_pong(
        self, handlers, mock_registry, mock_transport
    ):
        mock_registry.is_approved.return_value = True
        mock_registry.get_hashes.return_value = {
            "m": "aaa", "u": "bbb", "a": "ccc", "d": "ddd",
        }

        await handlers._handle_ping(
            self.SRC,
            {"m": "aaa", "u": "bbb", "a": "ccc", "d": "ddd"},
        )

        mock_transport.send.assert_called_once_with(
            self.SRC_HASH, {"tp": TP_PING_PONG, "sections": [], "diffs": []}
        )

    async def test_single_section_diff(
        self, handlers, mock_registry, mock_transport
    ):
        """Only the 'u' section differs."""
        mock_registry.is_approved.return_value = True
        mock_registry.get_hashes.return_value = {
            "m": "aaa", "u": "NEWU", "a": "ccc", "d": "ddd",
        }

        await handlers._handle_ping(
            self.SRC,
            {"m": "aaa", "u": "bbb", "a": "ccc", "d": "ddd"},
        )

        mock_transport.send.assert_called_once_with(
            self.SRC_HASH,
            {"tp": TP_PING_PONG, "sections": ["u"], "diffs": ["u"]},
        )

    async def test_all_sections_diff(
        self, handlers, mock_registry, mock_transport
    ):
        """When all sections differ (including 'd'), handler sends PONG then STATUS."""
        mock_registry.is_approved.return_value = True
        mock_registry.get_hashes.return_value = {
            "m": "xxx", "u": "yyy", "a": "zzz", "d": "www",
        }

        await handlers._handle_ping(
            self.SRC,
            {"m": "aaa", "u": "bbb", "a": "ccc", "d": "ddd"},
        )

        # Two sends: PONG + STATUS (because 'd' is in diffs)
        assert mock_transport.send.call_count == 2
        pong_call = mock_transport.send.call_args_list[0]
        assert pong_call == call(
            self.SRC_HASH,
            {"tp": TP_PING_PONG, "sections": ["m", "u", "a", "d"], "diffs": ["m", "u", "a", "d"]},
        )
        # STATUS has empty data by default (no devices in mock)
        status_call = mock_transport.send.call_args_list[1]
        assert status_call[0][1]["tp"] == TP_STATUS

    async def test_diff_d_triggers_status(
        self,
        handlers,
        mock_hass,
        mock_registry,
        mock_transport,
        mock_extract_state,
    ):
        """When 'd' differs, the handler first sends PONG then STATUS."""
        mock_registry.is_approved.return_value = True
        mock_registry.get_hashes.return_value = {
            "m": "aaa", "u": "bbb", "a": "ccc", "d": "NEWD",
        }
        mock_registry.all_devices.return_value = [
            {
                "short_id": 7,
                "entity_id": "light.test",
                "type": "LT",
                "name": "Test Light",
            },
        ]
        mock_hass.states.get.return_value = MagicMock(
            state="on", attributes={"brightness": 128}
        )
        mock_extract_state.return_value = {"v": "on", "b": 50}

        await handlers._handle_ping(
            self.SRC,
            {"m": "aaa", "u": "bbb", "a": "ccc", "d": "ddd"},
        )

        # Two sends: PONG + STATUS
        assert mock_transport.send.call_count == 2

        # First send is PONG with diffs including "d"
        pong_call = mock_transport.send.call_args_list[0]
        assert pong_call == call(
            self.SRC_HASH,
            {"tp": TP_PING_PONG, "sections": ["d"], "diffs": ["d"]},
        )

        # Second send is STATUS
        status_call = mock_transport.send.call_args_list[1]
        assert status_call == call(
            self.SRC_HASH,
            {"tp": TP_STATUS, "data": [{"id": 7, "v": "on", "b": 50}]},
        )

    async def test_diff_non_d_no_status(
        self, handlers, mock_registry, mock_transport
    ):
        """When 'd' does NOT differ, only PONG is sent."""
        mock_registry.is_approved.return_value = True
        mock_registry.get_hashes.return_value = {
            "m": "NEWM", "u": "bbb", "a": "ccc", "d": "ddd",
        }

        await handlers._handle_ping(
            self.SRC,
            {"m": "aaa", "u": "bbb", "a": "ccc", "d": "ddd"},
        )

        # Only PONG — no STATUS
        assert mock_transport.send.call_count == 1
        pong_call = mock_transport.send.call_args
        assert pong_call[0][1]["tp"] == TP_PING_PONG

    async def test_partial_client_hashes_default_to_none(
        self, handlers, mock_registry, mock_transport
    ):
        """If client omits a hash field, fields.get() returns None, which
        will differ from the registry hash (non-None) -> section is a diff.
        Because 'd' differs, STATUS is also sent."""
        mock_registry.is_approved.return_value = True
        mock_registry.get_hashes.return_value = {
            "m": "aaa", "u": "bbb", "a": "ccc", "d": "ddd",
        }

        await handlers._handle_ping(self.SRC, {"m": "aaa", "u": "bbb"})

        # Two sends: PONG + STATUS (because d is in diffs)
        assert mock_transport.send.call_count == 2
        pong_call = mock_transport.send.call_args_list[0]
        assert pong_call == call(
            self.SRC_HASH,
            {"tp": TP_PING_PONG, "sections": ["a", "d"], "diffs": ["a", "d"]},
        )


# =========================================================================
# 4. REQ handler
# =========================================================================


class TestReq:
    """_handle_req — request config sections."""

    SRC = b"\xab\xcd"
    SRC_HASH = "abcd"

    async def test_unauthorized_sends_forbidden(
        self, handlers, mock_registry, mock_transport
    ):
        mock_registry.is_approved.return_value = False

        await handlers._handle_req(self.SRC, {"sections": ["m"]})

        mock_transport.send.assert_called_once_with(
            self.SRC_HASH, {"tp": TP_FORBIDDEN, "reason": "unauthorized"}
        )

    async def test_single_section_m(
        self, handlers, mock_registry, mock_transport
    ):
        mock_registry.is_approved.return_value = True
        mock_registry.get_meta.return_value = {"server_name": "Hub", "_hash": "abcd"}

        await handlers._handle_req(self.SRC, {"sections": ["m"]})

        mock_registry.get_meta.assert_called_once()
        mock_transport.send.assert_called_once_with(
            self.SRC_HASH, {"tp": TP_CONFIG, "section": "m", "data": {"server_name": "Hub", "_hash": "abcd"}, "h": "0000"}
        )

    async def test_section_u_combines_users_and_pending(
        self, handlers, mock_registry, mock_transport
    ):
        mock_registry.is_approved.return_value = True
        mock_registry.all_users.return_value = [{"hash": "aa", "name": "Alice", "role": "owner"}]
        mock_registry.all_pending.return_value = [{"hash": "bb", "name": "Bob", "requested_at": 0}]

        await handlers._handle_req(self.SRC, {"sections": ["u"]})

        mock_registry.all_users.assert_called_once()
        mock_registry.all_pending.assert_called_once()
        mock_transport.send.assert_called_once_with(
            self.SRC_HASH, {"tp": TP_CONFIG,
                "section": "u",
                "h": "0000",
                "data": {
                    "users": [{"hash": "aa", "name": "Alice", "role": "owner"}],
                    "pending": [{"hash": "bb", "name": "Bob", "requested_at": 0}],
                },
            },
        )

    async def test_section_a(
        self, handlers, mock_registry, mock_transport
    ):
        mock_registry.is_approved.return_value = True
        mock_registry.all_areas.return_value = [{"id": 1, "name": "Living Room"}]

        await handlers._handle_req(self.SRC, {"sections": ["a"]})

        mock_transport.send.assert_called_once_with(
            self.SRC_HASH, {"tp": TP_CONFIG,
                "section": "a", "h": "0000", "data": [{"id": 1, "name": "Living Room"}]},
        )

    async def test_section_d(
        self,
        handlers,
        mock_hass,
        mock_registry,
        mock_transport,
        mock_extract_state,
    ):
        """Requesting 'd' sends CONFIG(d) plus STATUS."""
        mock_registry.is_approved.return_value = True
        mock_registry.all_devices.return_value = [
            {"short_id": 1, "entity_id": "sw.test", "type": "SW", "name": "Test"},
        ]
        mock_hass.states.get.return_value = MagicMock(state="on", attributes={})
        mock_extract_state.return_value = {"v": "on"}

        await handlers._handle_req(self.SRC, {"sections": ["d"]})

        # Two sends: CONFIG(d) + STATUS
        assert mock_transport.send.call_count == 2
        config_call = mock_transport.send.call_args_list[0]
        assert config_call == call(
            self.SRC_HASH, {"tp": TP_CONFIG,
                "section": "d", "h": "0000", "data": [{"short_id": 1, "entity_id": "sw.test", "type": "SW", "name": "Test"}]},
        )
        status_call = mock_transport.send.call_args_list[1]
        assert status_call[0][1]["tp"] == TP_STATUS

    async def test_multiple_sections(
        self, handlers, mock_registry, mock_transport
    ):
        mock_registry.is_approved.return_value = True
        mock_registry.get_meta.return_value = {"server_name": "Hub", "_hash": "m001"}
        mock_registry.all_areas.return_value = [{"id": 1, "name": "Kitchen"}]

        await handlers._handle_req(self.SRC, {"sections": ["m", "a"]})

        assert mock_transport.send.call_count == 2
        sections_sent = [c[0][1]["section"] for c in mock_transport.send.call_args_list]
        assert sections_sent == ["m", "a"]

    async def test_section_d_triggers_additional_status(
        self,
        handlers,
        mock_hass,
        mock_registry,
        mock_transport,
        mock_extract_state,
    ):
        """When 'd' is in sections, both CONFIG(d) and STATUS are sent."""
        mock_registry.is_approved.return_value = True
        mock_registry.all_devices.return_value = [
            {"short_id": 1, "entity_id": "sw.test", "type": "SW", "name": "Test"},
        ]
        mock_hass.states.get.return_value = MagicMock(state="on", attributes={})
        mock_extract_state.return_value = {"v": "on"}

        await handlers._handle_req(self.SRC, {"sections": ["m", "d"]})

        # Two sends expected: CONFIG for m, CONFIG for d, then STATUS
        assert mock_transport.send.call_count == 3

        # Verify the STATUS payload
        status_call = mock_transport.send.call_args_list[2]
        assert status_call == call(
            self.SRC_HASH, {"tp": TP_STATUS, "data": [{"id": 1, "v": "on"}]}
        )

    async def test_empty_sections(
        self, handlers, mock_registry, mock_transport
    ):
        """No sections requested -> no sends at all."""
        mock_registry.is_approved.return_value = True

        await handlers._handle_req(self.SRC, {"sections": []})

        mock_transport.send.assert_not_called()

    async def test_missing_sections_key_defaults_empty(
        self, handlers, mock_registry, mock_transport
    ):
        """If 'sections' key is absent, treat as empty list."""
        mock_registry.is_approved.return_value = True

        await handlers._handle_req(self.SRC, {})

        mock_transport.send.assert_not_called()


# =========================================================================
# 5. REGISTER handler
# =========================================================================


class TestRegister:
    """_handle_register — remote registration flow."""

    SRC = b"\xaa\xbb"
    SRC_HASH = "aabb"

    async def test_invalid_uid_sends_forbidden(
        self, handlers, mock_registry, mock_transport
    ):
        mock_registry.consume_qr_token.return_value = False

        await handlers._handle_register(self.SRC, {"uid": "bad", "dst": "x", "name": "n"})

        mock_registry.consume_qr_token.assert_called_once_with("bad")
        mock_transport.send.assert_called_once_with(
            self.SRC_HASH, {"tp": TP_FORBIDDEN, "reason": "invalid_uid"}
        )

    async def test_valid_uid_add_pending_fails_sends_forbidden(
        self, handlers, mock_registry, mock_transport
    ):
        mock_registry.consume_qr_token.return_value = True
        mock_registry.add_pending.return_value = False

        await handlers._handle_register(
            self.SRC, {"uid": "good", "dst": "dest", "name": "Alice"}
        )

        mock_registry.consume_qr_token.assert_called_once_with("good")
        mock_registry.add_pending.assert_called_once_with(self.SRC_HASH, "Alice")
        mock_transport.send.assert_called_once_with(
            self.SRC_HASH, {"tp": TP_FORBIDDEN, "reason": "pending_limit_exceeded"}
        )

    async def test_valid_uid_approval_fails_sends_forbidden(
        self, handlers, mock_registry, mock_transport
    ):
        mock_registry.consume_qr_token.return_value = True
        mock_registry.add_pending.return_value = True
        mock_registry.approve_pending.return_value = False

        await handlers._handle_register(
            self.SRC, {"uid": "good", "dst": "dest", "name": "Alice"}
        )

        mock_registry.add_pending.assert_called_once_with(self.SRC_HASH, "Alice")
        mock_registry.approve_pending.assert_called_once_with(self.SRC_HASH)
        mock_transport.send.assert_called_once_with(
            self.SRC_HASH, {"tp": TP_FORBIDDEN, "reason": "approval_failed"}
        )

    async def test_successful_registration_sends_config_and_status(
        self,
        handlers,
        mock_hass,
        mock_registry,
        mock_transport,
        mock_extract_state,
    ):
        """Full happy path: consume -> add_pending -> approve -> 4x CONFIG + STATUS."""
        mock_registry.consume_qr_token.return_value = True
        mock_registry.add_pending.return_value = True
        mock_registry.approve_pending.return_value = True

        # Section data
        mock_registry.get_meta.return_value = {"server_name": "Hub", "_hash": "m001"}
        mock_registry.all_users.return_value = [
            {"hash": "aa", "name": "Alice", "role": "owner"},
        ]
        mock_registry.all_pending.return_value = []
        mock_registry.all_areas.return_value = [{"id": 1, "name": "Living Room"}]
        mock_registry.all_devices.return_value = [
            {"short_id": 1, "entity_id": "sw.test", "type": "SW", "name": "Test", "area_id": None, "enabled": True},
        ]

        # Status data
        mock_hass.states.get.return_value = MagicMock(state="on", attributes={})
        mock_extract_state.return_value = {"v": "on"}

        await handlers._handle_register(
            self.SRC, {"uid": "good", "dst": "dest", "name": "Alice"}
        )

        # Verify flow
        mock_registry.consume_qr_token.assert_called_once_with("good")
        mock_registry.add_pending.assert_called_once_with(self.SRC_HASH, "Alice")
        mock_registry.approve_pending.assert_called_once_with(self.SRC_HASH)

        # Expect 5 sends: 4x CONFIG (m/u/a/d) + 1x STATUS
        assert mock_transport.send.call_count == 5

        # First four should be CONFIG for sections m, u, a, d
        config_calls = mock_transport.send.call_args_list[:4]
        assert all(c[0][1]["tp"] == TP_CONFIG for c in config_calls)
        sections_sent = [c[0][1]["section"] for c in config_calls]
        assert sections_sent == ["m", "u", "a", "d"]

        # Last call is STATUS
        status_call = mock_transport.send.call_args_list[4]
        assert status_call == call(
            self.SRC_HASH, {"tp": TP_STATUS, "data": [{"id": 1, "v": "on"}]}
        )

    async def test_successful_registration_no_devices(
        self,
        handlers,
        mock_hass,
        mock_registry,
        mock_transport,
        mock_extract_state,
    ):
        """Status send is still called even with zero devices (empty data)."""
        mock_registry.consume_qr_token.return_value = True
        mock_registry.add_pending.return_value = True
        mock_registry.approve_pending.return_value = True

        mock_registry.get_meta.return_value = {"server_name": "Hub", "_hash": "m001"}
        mock_registry.all_users.return_value = []
        mock_registry.all_pending.return_value = []
        mock_registry.all_areas.return_value = []
        mock_registry.all_devices.return_value = []

        await handlers._handle_register(
            self.SRC, {"uid": "good", "dst": "dest", "name": "Alice"}
        )

        assert mock_transport.send.call_count == 5
        status_call = mock_transport.send.call_args_list[4]
        assert status_call == call(
            self.SRC_HASH, {"tp": TP_STATUS, "data": []}
        )

    async def test_register_uses_src_hash_not_raw_bytes(
        self, handlers, mock_registry, mock_transport
    ):
        """Verify src_hash is the hex representation of src_bytes."""
        mock_registry.consume_qr_token.return_value = True
        mock_registry.add_pending.return_value = True
        mock_registry.approve_pending.return_value = True

        mock_registry.get_meta.return_value = {"server_name": "Hub", "_hash": "m001"}
        mock_registry.all_users.return_value = []
        mock_registry.all_pending.return_value = []
        mock_registry.all_areas.return_value = []
        mock_registry.all_devices.return_value = []

        await handlers._handle_register(
            b"\x01\x02\x03\x04",
            {"uid": "good", "dst": "dest", "name": "Alice"},
        )

        mock_registry.add_pending.assert_called_once_with("01020304", "Alice")

    async def test_register_active_limit_sends_forbidden_with_specific_reason(
        self, handlers, mock_registry, mock_transport
    ):
        """When MAX_ACTIVE_REMOTES is reached, REGISTER must respond with
        FORBIDDEN and reason='active_limit_exceeded'."""
        # Pre-populate 5 active users
        mock_registry.all_users.return_value = [
            {"hash": f"hash_{i}", "name": f"user_{i}", "role": "owner"} for i in range(5)
        ]
        
        # Set up a fresh QR token
        mock_registry.consume_qr_token.return_value = True
        
        # add_pending succeeds (pending limit not reached)
        mock_registry.add_pending.return_value = True
        
        # approve_pending fails because active limit reached
        mock_registry.approve_pending.return_value = False
        
        # deny_pending succeeds when cleaning up
        mock_registry.deny_pending.return_value = True

        await handlers._handle_register(
            b"\xaa\xbb\xcc\xdd", {"uid": "test_token_abc", "name": "Sixth Client"}
        )

        # Verify FORBIDDEN was sent with reason="active_limit_exceeded"
        mock_transport.send.assert_called_once_with(
            "aabbccdd", {"tp": TP_FORBIDDEN, "reason": "active_limit_exceeded"}
        )


# =========================================================================
# 6. _send_config_section edge cases (tested via _handle_req)
# =========================================================================


class TestSendConfigSection:
    """_send_config_section — registry section serialisation."""

    SRC = b"\xab\xcd"

    async def test_unknown_section_logs_error_no_send(
        self, handlers, mock_registry, mock_transport, caplog
    ):
        """An unrecognised section key logs and returns without sending."""
        mock_registry.is_approved.return_value = True

        import logging
        with caplog.at_level(logging.ERROR, logger="custom_components.rover.hnd"):
            await handlers._handle_req(self.SRC, {"sections": ["unknown_key"]})

        mock_transport.send.assert_not_called()
        assert "Unknown section key: unknown_key" in caplog.text


# =========================================================================
# 7. _send_status edge cases
# =========================================================================


class TestSendStatus:
    """_send_status — HA state collection and serialisation."""

    SRC = b"\xab\xcd"
    SRC_HASH = "abcd"

    async def test_skip_device_with_no_state(
        self,
        handlers,
        mock_hass,
        mock_registry,
        mock_transport,
        mock_extract_state,
    ):
        """Devices whose entity has no HA state are skipped (not crashed on)."""
        mock_registry.is_approved.return_value = True

        # Two devices, but the first has no state
        mock_registry.all_devices.return_value = [
            {"short_id": 1, "entity_id": "sensor.missing", "type": "SE", "name": "Gone"},
            {"short_id": 2, "entity_id": "switch.present", "type": "SW", "name": "Here"},
        ]

        def _get_state(entity_id):
            if entity_id == "switch.present":
                return MagicMock(state="on", attributes={})
            return None

        mock_hass.states.get.side_effect = _get_state
        mock_extract_state.return_value = {"v": "on"}

        # Trigger _send_status via req with section "d"
        await handlers._handle_req(self.SRC, {"sections": ["d"]})

        # Only the second device appears in status
        status_call = [
            c for c in mock_transport.send.call_args_list if c[0][1]["tp"] == TP_STATUS
        ]
        assert len(status_call) == 1
        assert status_call[0] == call(
            self.SRC_HASH, {"tp": TP_STATUS, "data": [{"id": 2, "v": "on"}]}
        )

    async def test_multiple_devices_all_with_state(
        self,
        handlers,
        mock_hass,
        mock_registry,
        mock_transport,
        mock_extract_state,
    ):
        """Multiple devices with valid states produce a combined status list."""
        mock_registry.is_approved.return_value = True
        mock_registry.all_devices.return_value = [
            {"short_id": 10, "entity_id": "light.a", "type": "LT", "name": "A"},
            {"short_id": 20, "entity_id": "switch.b", "type": "SW", "name": "B"},
        ]

        def _get_state(entity_id):
            states = {
                "light.a": MagicMock(state="on", attributes={"brightness": 200}),
                "switch.b": MagicMock(state="off", attributes={}),
            }
            return states.get(entity_id)

        mock_hass.states.get.side_effect = _get_state

        def _extract(state, attrs, dtype):
            return {"v": state}

        mock_extract_state.side_effect = _extract

        await handlers._handle_req(self.SRC, {"sections": ["d"]})

        status_call = [
            c for c in mock_transport.send.call_args_list if c[0][1]["tp"] == TP_STATUS
        ]
        assert len(status_call) == 1
        data = status_call[0][0][1]["data"]
        assert len(data) == 2
        assert data[0]["id"] == 10
        assert data[1]["id"] == 20
        assert data[0]["v"] == "on"
        assert data[1]["v"] == "off"


# =========================================================================
# 8. _is_authorized and _get_sender_hash
# =========================================================================


class TestAuth:
    """Authorization helper methods."""

    def test_get_sender_hash_returns_hex(self, handlers):
        result = handlers._get_sender_hash(b"\x00\xff\xab")
        assert result == "00ffab"

    def test_get_sender_hash_empty_bytes(self, handlers):
        result = handlers._get_sender_hash(b"")
        assert result == ""

    def test_is_authorized_delegates_to_registry(self, handlers, mock_registry):
        mock_registry.is_approved.return_value = True
        assert handlers._is_authorized("some_hash") is True
        mock_registry.is_approved.assert_called_once_with("some_hash")

    def test_is_authorized_false(self, handlers, mock_registry):
        mock_registry.is_approved.return_value = False
        assert handlers._is_authorized("some_hash") is False
