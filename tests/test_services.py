"""Tests for rover.services — debug service registration and handler logic."""
from __future__ import annotations

import logging
from unittest.mock import AsyncMock, MagicMock, call

import pytest

from custom_components.rover.services import (
    DEFAULT_LEVELS,
    LEVEL_MAP,
    SERVICE_DUMP_REGISTRY,
    SERVICE_SEND_TEST_MESSAGE,
    SERVICE_SET_LOGLEVEL,
    SERVICE_SIMULATE_INBOUND,
    _restore_default_levels,
    async_register_services,
    async_unregister_services,
)
from custom_components.rover.const import (
    DOMAIN,
    LOGGER_HAB,
    LOGGER_HND,
    LOGGER_REG,
    LOGGER_RNS,
    LOGGER_ROOT,
    LOGGER_TRN,
)

# Save original levels before any test messes with them
_ORIG_LEVELS = {name: logging.getLogger(name).level for name in DEFAULT_LEVELS}


def _reset_log_levels() -> None:
    """Restore loggers to DEFAULT_LEVELS values."""
    for name, lvl in DEFAULT_LEVELS.items():
        logging.getLogger(name).setLevel(lvl)


@pytest.fixture(autouse=True)
def _reset_logging():
    """Reset logging levels before and after every test."""
    _reset_log_levels()
    yield
    _reset_log_levels()


# ---------------------------------------------------------------------------
# _restore_default_levels
# ---------------------------------------------------------------------------


class TestRestoreDefaultLevels:
    def test_restores_all_loggers_to_default(self) -> None:
        for name in DEFAULT_LEVELS:
            logging.getLogger(name).setLevel(logging.ERROR)
        _restore_default_levels()
        for name, expected in DEFAULT_LEVELS.items():
            assert logging.getLogger(name).level == expected, (
                f"{name} expected {expected}, got {logging.getLogger(name).level}"
            )

    def test_restore_is_idempotent(self) -> None:
        _restore_default_levels()
        _restore_default_levels()
        for name, expected in DEFAULT_LEVELS.items():
            assert logging.getLogger(name).level == expected

    def test_default_has_root_info(self) -> None:
        assert DEFAULT_LEVELS[LOGGER_ROOT] == logging.INFO

    def test_defaults_cover_all_expected_loggers(self) -> None:
        expected_loggers = {LOGGER_ROOT, LOGGER_REG, LOGGER_HND, LOGGER_TRN, LOGGER_HAB, LOGGER_RNS}
        assert set(DEFAULT_LEVELS.keys()) == expected_loggers


# ---------------------------------------------------------------------------
# Shared fixture for service handler capture
# ---------------------------------------------------------------------------


@pytest.fixture
def svc_fixture():
    """Create mock hass + runtime and capture registered handlers.

    Returns dict with keys: hass, runtime, handlers (dict name->callable).
    """
    hass = MagicMock()
    hass.services.has_service = MagicMock(return_value=False)
    hass.services.async_remove = MagicMock()
    hass.loop.call_later = MagicMock(return_value=MagicMock())

    runtime = MagicMock()
    runtime.transport = MagicMock()
    runtime.transport.send = AsyncMock()
    runtime.identity_hash = "ab" * 32
    runtime.dispatcher = MagicMock()
    runtime.dispatcher.dispatch = AsyncMock()
    runtime.registry = MagicMock()
    runtime.registry.is_approved = MagicMock(return_value=False)
    runtime.registry.add_pending = AsyncMock(return_value=True)
    runtime.registry.approve_pending = AsyncMock(return_value=True)
    runtime.registry.revoke_user = AsyncMock(return_value=True)
    runtime.registry.get_hashes = MagicMock(return_value={"m": "abcd", "u": "ef01"})
    runtime.registry.get_meta = MagicMock(return_value={"server_name": "Test Hub"})
    runtime.registry.all_users = MagicMock(return_value=[{"hash": "u1", "name": "Alice"}])
    runtime.registry.all_devices = MagicMock(return_value=[{"short_id": 1}])
    runtime.registry.all_areas = MagicMock(return_value=[{"id": 1, "name": "Living"}])
    runtime.registry.all_pending = MagicMock(return_value=[])

    handlers: dict[str, callable] = {}

    def _capture_register(domain, name, handler, schema=None):
        handlers[name] = handler

    hass.services.async_register = _capture_register

    return {"hass": hass, "runtime": runtime, "handlers": handlers}


@pytest.fixture
async def registered_services(svc_fixture):
    """Call async_register_services and return the populated fixture."""
    await async_register_services(svc_fixture["hass"], svc_fixture["runtime"])
    return svc_fixture


# ---------------------------------------------------------------------------
# async_register_services
# ---------------------------------------------------------------------------


class TestRegisterServices:
    @pytest.mark.asyncio
    async def test_registers_four_services(self, registered_services) -> None:
        assert len(registered_services["handlers"]) == 4

    @pytest.mark.asyncio
    async def test_registers_set_loglevel(self, registered_services) -> None:
        assert SERVICE_SET_LOGLEVEL in registered_services["handlers"]

    @pytest.mark.asyncio
    async def test_registers_send_test_message(self, registered_services) -> None:
        assert SERVICE_SEND_TEST_MESSAGE in registered_services["handlers"]

    @pytest.mark.asyncio
    async def test_registers_simulate_inbound(self, registered_services) -> None:
        assert SERVICE_SIMULATE_INBOUND in registered_services["handlers"]

    @pytest.mark.asyncio
    async def test_registers_dump_registry(self, registered_services) -> None:
        assert SERVICE_DUMP_REGISTRY in registered_services["handlers"]

    @pytest.mark.asyncio
    async def test_skips_already_registered_services(self, svc_fixture) -> None:
        svc_fixture["hass"].services.has_service = MagicMock(return_value=True)
        await async_register_services(svc_fixture["hass"], svc_fixture["runtime"])
        assert len(svc_fixture["handlers"]) == 0

    @pytest.mark.asyncio
    async def test_has_service_checked_per_service(self, registered_services) -> None:
        hass = registered_services["hass"]
        expected_calls = [
            call(DOMAIN, SERVICE_SET_LOGLEVEL),
            call(DOMAIN, SERVICE_SEND_TEST_MESSAGE),
            call(DOMAIN, SERVICE_SIMULATE_INBOUND),
            call(DOMAIN, SERVICE_DUMP_REGISTRY),
        ]
        actual_calls = hass.services.has_service.call_args_list
        for expected in expected_calls:
            assert expected in actual_calls, f"Missing check: {expected}"


# ---------------------------------------------------------------------------
# set_loglevel handler
# ---------------------------------------------------------------------------


def _call(data: dict):
    """Build a mock ServiceCall with given data dict."""
    mock = MagicMock()
    mock.data = data
    return mock


class TestSetLogLevel:
    @pytest.mark.asyncio
    async def test_sets_all_loggers_to_debug(self, registered_services) -> None:
        h = registered_services["handlers"][SERVICE_SET_LOGLEVEL]
        await h(_call({"level": "debug", "duration_minutes": 1}))
        for name in DEFAULT_LEVELS:
            assert logging.getLogger(name).level == logging.DEBUG, (
                f"{name} was {logging.getLogger(name).level}, expected DEBUG"
            )

    @pytest.mark.asyncio
    async def test_sets_all_loggers_to_error(self, registered_services) -> None:
        h = registered_services["handlers"][SERVICE_SET_LOGLEVEL]
        await h(_call({"level": "error", "duration_minutes": 1}))
        for name in DEFAULT_LEVELS:
            assert logging.getLogger(name).level == logging.ERROR

    @pytest.mark.asyncio
    async def test_warns_on_invalid_level(self, registered_services, caplog) -> None:
        h = registered_services["handlers"][SERVICE_SET_LOGLEVEL]
        with caplog.at_level(logging.WARNING):
            await h(_call({"level": "invalid_level", "duration_minutes": 1}))
            assert "invalid level" in caplog.text
            assert "invalid_level" in caplog.text

    @pytest.mark.asyncio
    async def test_no_level_change_on_invalid(self, registered_services) -> None:
        h = registered_services["handlers"][SERVICE_SET_LOGLEVEL]
        await h(_call({"level": "bogus", "duration_minutes": 1}))
        # Should stay at default levels
        for name, expected in DEFAULT_LEVELS.items():
            assert logging.getLogger(name).level == expected

    @pytest.mark.asyncio
    async def test_schedules_timer_restore(self, registered_services) -> None:
        hass = registered_services["hass"]
        h = registered_services["handlers"][SERVICE_SET_LOGLEVEL]
        await h(_call({"level": "debug", "duration_minutes": 5}))
        hass.loop.call_later.assert_called_once_with(
            300, _restore_default_levels
        )

    @pytest.mark.asyncio
    async def test_cancels_previous_timer(self, registered_services) -> None:
        hass = registered_services["hass"]
        h = registered_services["handlers"][SERVICE_SET_LOGLEVEL]

        timer1 = MagicMock()
        hass.loop.call_later.return_value = timer1
        await h(_call({"level": "debug", "duration_minutes": 1}))

        timer2 = MagicMock()
        hass.loop.call_later.return_value = timer2
        await h(_call({"level": "info", "duration_minutes": 2}))

        timer1.cancel.assert_called_once()

    @pytest.mark.asyncio
    async def test_defaults_duration_to_30_minutes(self, registered_services) -> None:
        hass = registered_services["hass"]
        h = registered_services["handlers"][SERVICE_SET_LOGLEVEL]
        await h(_call({"level": "debug"}))
        hass.loop.call_later.assert_called_once_with(
            1800, _restore_default_levels
        )

    @pytest.mark.asyncio
    async def test_defaults_level_to_info(self, registered_services) -> None:
        h = registered_services["handlers"][SERVICE_SET_LOGLEVEL]
        await h(_call({}))
        for name in DEFAULT_LEVELS:
            assert logging.getLogger(name).level == logging.INFO


# ---------------------------------------------------------------------------
# send_test_message handler
# ---------------------------------------------------------------------------


class TestSendTestMessage:
    @pytest.mark.asyncio
    async def test_sends_message_with_destination(self, registered_services) -> None:
        runtime = registered_services["runtime"]
        h = registered_services["handlers"][SERVICE_SEND_TEST_MESSAGE]
        dst = "aa" * 32
        await h(_call({"destination_hash": dst, "tp": 5, "payload": {}}))
        runtime.transport.send.assert_awaited_once_with(dst, {"tp": 5})

    @pytest.mark.asyncio
    async def test_sends_message_with_payload(self, registered_services) -> None:
        runtime = registered_services["runtime"]
        h = registered_services["handlers"][SERVICE_SEND_TEST_MESSAGE]
        dst = "bb" * 32
        await h(_call({"destination_hash": dst, "tp": 6, "payload": {"temp": 25}}))
        runtime.transport.send.assert_awaited_once_with(dst, {"tp": 6, "temp": 25})

    @pytest.mark.asyncio
    async def test_sends_to_self_identity(self, registered_services) -> None:
        runtime = registered_services["runtime"]
        h = registered_services["handlers"][SERVICE_SEND_TEST_MESSAGE]
        await h(_call({"destination_hash": "self", "tp": 5, "payload": {}}))
        runtime.transport.send.assert_awaited_once_with(
            runtime.identity_hash, {"tp": 5}
        )

    @pytest.mark.asyncio
    async def test_warns_when_transport_none(self, registered_services, caplog) -> None:
        runtime = registered_services["runtime"]
        h = registered_services["handlers"][SERVICE_SEND_TEST_MESSAGE]
        runtime.transport = None
        with caplog.at_level(logging.WARNING):
            await h(_call({"destination_hash": "aa" * 32, "tp": 5, "payload": {}}))
            assert "transport not initialized" in caplog.text

    @pytest.mark.asyncio
    async def test_warns_when_identity_none_and_self(self, registered_services, caplog) -> None:
        runtime = registered_services["runtime"]
        h = registered_services["handlers"][SERVICE_SEND_TEST_MESSAGE]
        runtime.identity_hash = None
        with caplog.at_level(logging.WARNING):
            await h(_call({"destination_hash": "self", "tp": 5, "payload": {}}))
            assert "identity_hash not set" in caplog.text

    @pytest.mark.asyncio
    async def test_skips_send_when_transport_none(self, registered_services) -> None:
        runtime = registered_services["runtime"]
        h = registered_services["handlers"][SERVICE_SEND_TEST_MESSAGE]
        runtime.transport = None
        await h(_call({"destination_hash": "aa" * 32, "tp": 5, "payload": {}}))
        # No send should happen

    @pytest.mark.asyncio
    async def test_parses_json_payload_string(self, registered_services) -> None:
        runtime = registered_services["runtime"]
        h = registered_services["handlers"][SERVICE_SEND_TEST_MESSAGE]
        dst = "cc" * 32
        await h(_call({"destination_hash": dst, "tp": 5, "payload": '{"on": true}'}))
        runtime.transport.send.assert_awaited_once_with(dst, {"tp": 5, "on": True})

    @pytest.mark.asyncio
    async def test_warns_on_invalid_json_payload(self, registered_services, caplog) -> None:
        runtime = registered_services["runtime"]
        h = registered_services["handlers"][SERVICE_SEND_TEST_MESSAGE]
        with caplog.at_level(logging.WARNING):
            await h(_call(
                {"destination_hash": "dd" * 32, "tp": 5, "payload": "{bad json}"}
            ))
            assert "invalid JSON payload" in caplog.text
        runtime.transport.send.assert_not_called()


# ---------------------------------------------------------------------------
# simulate_inbound handler
# ---------------------------------------------------------------------------


class TestSimulateInbound:
    @pytest.mark.asyncio
    async def test_dispatches_inbound_message(self, registered_services) -> None:
        runtime = registered_services["runtime"]
        h = registered_services["handlers"][SERVICE_SIMULATE_INBOUND]
        src = "ee" * 32
        src_bytes = bytes.fromhex(src)
        await h(_call({"source_hash": src, "tp": 8, "payload": {}}))
        runtime.dispatcher.dispatch.assert_awaited_once_with(
            src_bytes, {"tp": 8}
        )

    @pytest.mark.asyncio
    async def test_authorized_adds_then_cleanups(self, registered_services) -> None:
        runtime = registered_services["runtime"]
        h = registered_services["handlers"][SERVICE_SIMULATE_INBOUND]
        src = "ff" * 32
        src_bytes = bytes.fromhex(src)

        runtime.registry.is_approved = MagicMock(return_value=False)

        await h(_call({
            "source_hash": src, "tp": 8, "payload": {}, "authorized": True,
        }))

        runtime.registry.add_pending.assert_awaited_once_with(src, "_test_sim")
        runtime.registry.approve_pending.assert_awaited_once_with(src)
        runtime.dispatcher.dispatch.assert_awaited_once_with(src_bytes, {"tp": 8})
        runtime.registry.revoke_user.assert_awaited_once_with(src)

    @pytest.mark.asyncio
    async def test_authorized_no_cleanup_when_add_fails(self, registered_services) -> None:
        """If add_pending returns False, skip approve/revoke."""
        runtime = registered_services["runtime"]
        h = registered_services["handlers"][SERVICE_SIMULATE_INBOUND]
        src = "11" * 32

        runtime.registry.is_approved = MagicMock(return_value=False)
        runtime.registry.add_pending = AsyncMock(return_value=False)

        await h(_call({
            "source_hash": src, "tp": 5, "payload": {}, "authorized": True,
        }))

        runtime.registry.add_pending.assert_awaited_once_with(src, "_test_sim")
        runtime.registry.approve_pending.assert_not_called()
        runtime.registry.revoke_user.assert_not_called()
        runtime.dispatcher.dispatch.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_authorized_no_ops_when_already_approved(self, registered_services) -> None:
        runtime = registered_services["runtime"]
        h = registered_services["handlers"][SERVICE_SIMULATE_INBOUND]
        src = "22" * 32

        runtime.registry.is_approved = MagicMock(return_value=True)
        await h(_call({
            "source_hash": src, "tp": 5, "payload": {}, "authorized": True,
        }))

        runtime.registry.add_pending.assert_not_called()
        runtime.registry.approve_pending.assert_not_called()
        runtime.registry.revoke_user.assert_not_called()
        runtime.dispatcher.dispatch.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_returns_early_when_dispatcher_none(self, registered_services) -> None:
        runtime = registered_services["runtime"]
        h = registered_services["handlers"][SERVICE_SIMULATE_INBOUND]
        runtime.dispatcher = None
        await h(_call({"source_hash": "33" * 32, "tp": 5, "payload": {}}))
        # No error

    @pytest.mark.asyncio
    async def test_parses_json_payload(self, registered_services) -> None:
        runtime = registered_services["runtime"]
        h = registered_services["handlers"][SERVICE_SIMULATE_INBOUND]
        src = "44" * 32
        await h(_call({
            "source_hash": src, "tp": 5, "payload": '{"brightness": 50}',
        }))
        runtime.dispatcher.dispatch.assert_awaited_once_with(
            bytes.fromhex(src), {"tp": 5, "brightness": 50}
        )

    @pytest.mark.asyncio
    async def test_silent_on_invalid_json_payload(self, registered_services) -> None:
        runtime = registered_services["runtime"]
        h = registered_services["handlers"][SERVICE_SIMULATE_INBOUND]
        await h(_call({"source_hash": "55" * 32, "tp": 5, "payload": "{bad}"}))
        runtime.dispatcher.dispatch.assert_not_called()

    @pytest.mark.asyncio
    async def test_non_dict_payload_becomes_empty(self, registered_services) -> None:
        runtime = registered_services["runtime"]
        h = registered_services["handlers"][SERVICE_SIMULATE_INBOUND]
        src = "66" * 32
        await h(_call({"source_hash": src, "tp": 5, "payload": 42}))
        runtime.dispatcher.dispatch.assert_awaited_once_with(
            bytes.fromhex(src), {"tp": 5}
        )

    @pytest.mark.asyncio
    async def test_not_authorized_skips_registry_ops(self, registered_services) -> None:
        runtime = registered_services["runtime"]
        h = registered_services["handlers"][SERVICE_SIMULATE_INBOUND]
        await h(_call({"source_hash": "77" * 32, "tp": 5, "payload": {}}))
        runtime.registry.add_pending.assert_not_called()
        runtime.registry.approve_pending.assert_not_called()
        runtime.registry.revoke_user.assert_not_called()
        runtime.dispatcher.dispatch.assert_awaited_once()


# ---------------------------------------------------------------------------
# dump_registry handler
# ---------------------------------------------------------------------------


class TestDumpRegistry:
    @pytest.mark.asyncio
    async def test_logs_registry_info(self, registered_services, caplog) -> None:
        h = registered_services["handlers"][SERVICE_DUMP_REGISTRY]
        with caplog.at_level(logging.INFO):
            await h(_call({}))
            assert "REG DUMP hashes=" in caplog.text
            assert "REG DUMP users=1" in caplog.text
            assert "REG DUMP devices=1" in caplog.text
            assert "REG DUMP areas=1" in caplog.text
            assert "REG DUMP pending=0" in caplog.text
            assert "Test Hub" in caplog.text

    @pytest.mark.asyncio
    async def test_silent_when_registry_none(self, registered_services, caplog) -> None:
        runtime = registered_services["runtime"]
        h = registered_services["handlers"][SERVICE_DUMP_REGISTRY]
        runtime.registry = None
        with caplog.at_level(logging.INFO):
            await h(_call({}))
            assert "REG DUMP" not in caplog.text


# ---------------------------------------------------------------------------
# async_unregister_services
# ---------------------------------------------------------------------------


class TestUnregisterServices:
    def test_removes_all_four_services(self) -> None:
        hass = MagicMock()
        hass.services.has_service = MagicMock(return_value=True)
        async_unregister_services(hass)
        expected_calls = [
            call(DOMAIN, SERVICE_SET_LOGLEVEL),
            call(DOMAIN, SERVICE_SEND_TEST_MESSAGE),
            call(DOMAIN, SERVICE_SIMULATE_INBOUND),
            call(DOMAIN, SERVICE_DUMP_REGISTRY),
        ]
        actual_calls = hass.services.async_remove.call_args_list
        for expected in expected_calls:
            assert expected in actual_calls, f"Missing removal: {expected}"
        assert len(actual_calls) == 4

    def test_skips_unregistered_services(self) -> None:
        hass = MagicMock()
        hass.services.has_service = MagicMock(return_value=False)
        async_unregister_services(hass)
        hass.services.async_remove.assert_not_called()
