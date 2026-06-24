"""Tests for rover.ha_bridge — RoverHABridge HA event broker."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from custom_components.rover.const import (
    PONG_BROADCAST_INTERVAL_S,
    PUSH_THROTTLE_MS,
    SENSOR_PUSH_INTERVAL,
    TP_PING_PONG,
    TP_PUSH,
)
from custom_components.rover.ha_bridge import RoverHABridge


# =========================================================================
# Fixtures
# =========================================================================


@pytest.fixture
def mock_hass():
    """Return a mocked HomeAssistant with bus, loop, and task creation."""
    hass = MagicMock()
    hass.bus = MagicMock()
    hass.bus.async_listen = MagicMock(return_value=lambda: None)
    hass.loop = MagicMock()
    timer_handle = MagicMock()
    timer_handle.cancel = MagicMock()
    hass.loop.call_later = MagicMock(return_value=timer_handle)
    hass.async_create_task = MagicMock()
    return hass


@pytest.fixture
def mock_registry():
    """Return a mocked RoverRegistry with realistic callback storage.

    set_on_changed/get_on_changed use a closure so that the stored
    callback is retrievable, mirroring the real Registry behaviour.
    """
    registry = MagicMock()
    registry.get_device_by_entity_id = MagicMock(return_value=None)
    registry.all_users = MagicMock(return_value=[])
    registry.get_hashes = MagicMock(
        return_value={"m": "abcd", "u": "ef01", "a": "2345", "d": "6789"}
    )

    _callback = None

    def _set_on_changed(cb):
        nonlocal _callback
        _callback = cb

    def _get_on_changed():
        return _callback

    registry.set_on_changed.side_effect = _set_on_changed
    registry.get_on_changed.side_effect = _get_on_changed

    return registry


@pytest.fixture
def mock_transport():
    """Return a mocked RoverTransport with async send."""
    transport = MagicMock()
    transport.send = AsyncMock()
    return transport


@pytest.fixture
def bridge(mock_hass, mock_registry, mock_transport):
    """Return a RoverHABridge wired to the mocks above."""
    return RoverHABridge(mock_hass, mock_registry, mock_transport)


# =========================================================================
# 1. async_start
# =========================================================================


class TestAsyncStart:
    """async_start — subscribes to state_changed, starts PONG, sets callback."""

    async def test_subscribes_to_state_changed(self, bridge, mock_hass):
        """Should register _on_state_change as state_changed listener."""
        await bridge.async_start()

        mock_hass.bus.async_listen.assert_called_once_with(
            "state_changed", bridge._on_state_change
        )

    async def test_starts_pong_broadcast(self, bridge, mock_hass):
        """Should schedule first PONG broadcast."""
        await bridge.async_start()

        mock_hass.loop.call_later.assert_called_once_with(
            PONG_BROADCAST_INTERVAL_S, bridge._broadcast_pong
        )

    async def test_sets_registry_change_callback(self, bridge, mock_registry):
        """Should register _on_registry_changed with registry."""
        await bridge.async_start()

        mock_registry.set_on_changed.assert_called_once_with(
            bridge._on_registry_changed
        )


# =========================================================================
# 2. _on_state_change
# =========================================================================


class TestOnStateChange:
    """_on_state_change — HA state change -> PUSH message."""

    async def test_no_entity_id_ignored(self, bridge, mock_registry, mock_transport):
        """Event without entity_id is silently ignored (no registry lookup)."""
        event = MagicMock(spec_set=["data"])
        event.data = {}

        await bridge._on_state_change(event)

        mock_registry.get_device_by_entity_id.assert_not_called()
        mock_transport.send.assert_not_called()

    async def test_unregistered_entity_ignored(
        self, bridge, mock_registry, mock_transport
    ):
        """Event for non-registered entity is ignored."""
        mock_registry.get_device_by_entity_id.return_value = None
        event = MagicMock()
        event.data = {"entity_id": "switch.unregistered"}

        await bridge._on_state_change(event)

        mock_registry.get_device_by_entity_id.assert_called_once_with(
            "switch.unregistered"
        )
        mock_transport.send.assert_not_called()

    async def test_registered_switch_sends_push_to_all_users(
        self, bridge, mock_registry, mock_transport
    ):
        """Registered switch entity triggers PUSH to every active user."""
        device = {
            "short_id": 1,
            "type": "SW",
            "entity_id": "switch.test",
        }
        mock_registry.get_device_by_entity_id.return_value = device
        mock_registry.all_users.return_value = [
            {"hash": "user1", "name": "Alice", "role": "owner"},
            {"hash": "user2", "name": "Bob", "role": "regular"},
        ]

        new_state = MagicMock()
        new_state.state = "on"
        new_state.attributes = {}

        event = MagicMock()
        event.data = {"entity_id": "switch.test", "new_state": new_state}

        with (
            patch("custom_components.rover.ha_bridge.time.monotonic", return_value=100.0),
            patch(
                "custom_components.rover.ha_bridge.extract_state",
                return_value={"v": "on"},
            ) as mock_extract,
        ):
            await bridge._on_state_change(event)

        mock_extract.assert_called_once_with("on", {}, "SW")
        assert mock_transport.send.call_count == 2
        mock_transport.send.assert_has_awaits([
            call("user1", {"tp": TP_PUSH, "id": 1, "v": "on"}),
            call("user2", {"tp": TP_PUSH, "id": 1, "v": "on"}),
        ])

    async def test_registered_sensor_sends_push_with_unit(
        self, bridge, mock_registry, mock_transport
    ):
        """Registered sensor entity triggers PUSH with measurement unit."""
        device = {
            "short_id": 5,
            "type": "SE",
            "entity_id": "sensor.temperature",
        }
        mock_registry.get_device_by_entity_id.return_value = device
        mock_registry.all_users.return_value = [
            {"hash": "user1", "name": "Alice", "role": "owner"}
        ]

        new_state = MagicMock()
        new_state.state = "22.5"
        new_state.attributes = {"unit_of_measurement": "°C"}

        event = MagicMock()
        event.data = {"entity_id": "sensor.temperature", "new_state": new_state}

        with (
            patch("custom_components.rover.ha_bridge.time.monotonic", return_value=100.0),
            patch(
                "custom_components.rover.ha_bridge.extract_state",
                return_value={"v": "22.5", "u": "°C"},
            ) as mock_extract,
        ):
            await bridge._on_state_change(event)

        mock_extract.assert_called_once_with(
            "22.5", {"unit_of_measurement": "°C"}, "SE"
        )
        mock_transport.send.assert_awaited_once_with(
            "user1", {"tp": TP_PUSH, "id": 5, "v": "22.5", "u": "°C"}
        )

    async def test_new_state_none_skipped(
        self, bridge, mock_registry, mock_transport
    ):
        """Event with new_state=None is silently ignored after throttle check."""
        device = {"short_id": 1, "type": "SW", "entity_id": "switch.test"}
        mock_registry.get_device_by_entity_id.return_value = device

        event = MagicMock()
        event.data = {"entity_id": "switch.test", "new_state": None}

        with patch("custom_components.rover.ha_bridge.time.monotonic", return_value=100.0):
            await bridge._on_state_change(event)

        mock_transport.send.assert_not_called()

    # -- Throttle: sensor (SE, 5s) ------------------------------------------

    async def test_sensor_throttle_within_cooldown_ignored(
        self, bridge, mock_registry, mock_transport
    ):
        """SE device: second event within SENSOR_PUSH_INTERVAL (5s) is throttled."""
        device = {"short_id": 5, "type": "SE", "entity_id": "sensor.temp"}
        mock_registry.get_device_by_entity_id.return_value = device
        mock_registry.all_users.return_value = [
            {"hash": "u1", "name": "A", "role": "owner"}
        ]

        ns = MagicMock(state="25", attributes={})
        event = MagicMock()
        event.data = {"entity_id": "sensor.temp", "new_state": ns}

        with (
            patch("custom_components.rover.ha_bridge.time.monotonic", return_value=100.0),
            patch(
                "custom_components.rover.ha_bridge.extract_state",
                return_value={"v": "25"},
            ),
        ):
            await bridge._on_state_change(event)
        assert mock_transport.send.call_count == 1

        # t=104: only 4 s later, still < 5 s -> throttled
        with patch("custom_components.rover.ha_bridge.time.monotonic", return_value=104.0):
            await bridge._on_state_change(event)
        assert mock_transport.send.call_count == 1

    async def test_sensor_after_cooldown_sends(
        self, bridge, mock_registry, mock_transport
    ):
        """SE device: event after SENSOR_PUSH_INTERVAL (5s) passes sends."""
        device = {"short_id": 5, "type": "SE", "entity_id": "sensor.temp"}
        mock_registry.get_device_by_entity_id.return_value = device
        mock_registry.all_users.return_value = [
            {"hash": "u1", "name": "A", "role": "owner"}
        ]

        ns = MagicMock(state="25", attributes={})
        event = MagicMock()
        event.data = {"entity_id": "sensor.temp", "new_state": ns}

        with (
            patch("custom_components.rover.ha_bridge.time.monotonic", return_value=100.0),
            patch(
                "custom_components.rover.ha_bridge.extract_state",
                return_value={"v": "25"},
            ),
        ):
            await bridge._on_state_change(event)
        assert mock_transport.send.call_count == 1

        # t=106: 6 s later, > 5 s -> sends
        with (
            patch("custom_components.rover.ha_bridge.time.monotonic", return_value=106.0),
            patch(
                "custom_components.rover.ha_bridge.extract_state",
                return_value={"v": "26"},
            ),
        ):
            await bridge._on_state_change(event)
        assert mock_transport.send.call_count == 2

    # -- Throttle: non-sensor (500 ms) -------------------------------------

    async def test_non_sensor_throttle_within_cooldown_ignored(
        self, bridge, mock_registry, mock_transport
    ):
        """Non-SE device: second event within PUSH_THROTTLE_MS (500ms) is throttled."""
        device = {"short_id": 1, "type": "SW", "entity_id": "switch.test"}
        mock_registry.get_device_by_entity_id.return_value = device
        mock_registry.all_users.return_value = [
            {"hash": "u1", "name": "A", "role": "owner"}
        ]

        ns = MagicMock(state="on", attributes={})
        event = MagicMock()
        event.data = {"entity_id": "switch.test", "new_state": ns}

        with (
            patch("custom_components.rover.ha_bridge.time.monotonic", return_value=100.0),
            patch(
                "custom_components.rover.ha_bridge.extract_state",
                return_value={"v": "on"},
            ),
        ):
            await bridge._on_state_change(event)
        assert mock_transport.send.call_count == 1

        # t=100.3: 300 ms later, < 500 ms -> throttled
        with patch("custom_components.rover.ha_bridge.time.monotonic", return_value=100.3):
            await bridge._on_state_change(event)
        assert mock_transport.send.call_count == 1

    async def test_non_sensor_after_cooldown_sends(
        self, bridge, mock_registry, mock_transport
    ):
        """Non-SE device: event after PUSH_THROTTLE_MS (500ms) passes sends."""
        device = {"short_id": 1, "type": "SW", "entity_id": "switch.test"}
        mock_registry.get_device_by_entity_id.return_value = device
        mock_registry.all_users.return_value = [
            {"hash": "u1", "name": "A", "role": "owner"}
        ]

        ns = MagicMock(state="off", attributes={})
        event = MagicMock()
        event.data = {"entity_id": "switch.test", "new_state": ns}

        with (
            patch("custom_components.rover.ha_bridge.time.monotonic", return_value=100.0),
            patch(
                "custom_components.rover.ha_bridge.extract_state",
                return_value={"v": "off"},
            ),
        ):
            await bridge._on_state_change(event)
        assert mock_transport.send.call_count == 1

        # t=101.0: 1 s later, > 500 ms -> sends
        with (
            patch("custom_components.rover.ha_bridge.time.monotonic", return_value=101.0),
            patch(
                "custom_components.rover.ha_bridge.extract_state",
                return_value={"v": "on"},
            ),
        ):
            await bridge._on_state_change(event)
        assert mock_transport.send.call_count == 2

    # -- Throttle: per-entity independence --------------------------------

    async def test_different_entity_ids_independent_throttle(
        self, bridge, mock_registry, mock_transport
    ):
        """Each entity_id has its own independent throttle counter."""
        device_a = {"short_id": 1, "type": "SW", "entity_id": "switch.a"}
        device_b = {"short_id": 2, "type": "SW", "entity_id": "switch.b"}

        def _lookup(eid):
            if eid == "switch.a":
                return device_a
            if eid == "switch.b":
                return device_b
            return None

        mock_registry.get_device_by_entity_id.side_effect = _lookup
        mock_registry.all_users.return_value = [
            {"hash": "u1", "name": "A", "role": "owner"}
        ]

        ns_a = MagicMock(state="on", attributes={})
        ns_b = MagicMock(state="off", attributes={})
        ev_a = MagicMock()
        ev_a.data = {"entity_id": "switch.a", "new_state": ns_a}
        ev_b = MagicMock()
        ev_b.data = {"entity_id": "switch.b", "new_state": ns_b}

        with (
            patch("custom_components.rover.ha_bridge.time.monotonic", return_value=100.0),
            patch(
                "custom_components.rover.ha_bridge.extract_state",
                side_effect=lambda s, a, d: {"v": s},
            ),
        ):
            await bridge._on_state_change(ev_a)
            await bridge._on_state_change(ev_b)

        # Both sent (different entity ids, no throttle collision)
        assert mock_transport.send.call_count == 2

        # t=100.3 — both within their own cooldown -> both throttled
        with patch("custom_components.rover.ha_bridge.time.monotonic", return_value=100.3):
            await bridge._on_state_change(ev_a)
            await bridge._on_state_change(ev_b)

        assert mock_transport.send.call_count == 2  # unchanged

    # -- Error path --------------------------------------------------------

    async def test_extract_state_value_error_logged(
        self, bridge, mock_registry, mock_transport, caplog
    ):
        """ValueError from extract_state is caught and logged; no PUSH sent."""
        device = {"short_id": 1, "type": "BAD", "entity_id": "switch.bad"}
        mock_registry.get_device_by_entity_id.return_value = device
        mock_registry.all_users.return_value = [
            {"hash": "u1", "name": "A", "role": "owner"}
        ]

        ns = MagicMock(state="on", attributes={})
        event = MagicMock()
        event.data = {"entity_id": "switch.bad", "new_state": ns}

        with (
            patch("custom_components.rover.ha_bridge.time.monotonic", return_value=100.0),
            patch(
                "custom_components.rover.ha_bridge.extract_state",
                side_effect=ValueError("bad type"),
            ),
        ):
            await bridge._on_state_change(event)

        mock_transport.send.assert_not_called()
        assert "Failed to extract state for switch.bad" in caplog.text


# =========================================================================
# 3. _broadcast_pong
# =========================================================================


class TestBroadcastPong:
    """_broadcast_pong — periodic PONG broadcast to all users."""

    def test_sends_pong_to_all_users(self, bridge, mock_registry, mock_hass):
        """PONG is scheduled for every active user via async_create_task."""
        mock_registry.all_users.return_value = [
            {"hash": "user1", "name": "Alice", "role": "owner"},
            {"hash": "user2", "name": "Bob", "role": "regular"},
        ]

        bridge._broadcast_pong()

        mock_registry.get_hashes.assert_called_once()
        assert mock_hass.async_create_task.call_count == 2

    def test_no_users_no_tasks(self, bridge, mock_registry, mock_hass):
        """With no active users, no async tasks are created."""
        bridge._broadcast_pong()

        mock_hass.async_create_task.assert_not_called()

    def test_reschedules_itself(self, bridge, mock_hass):
        """After broadcast, call_later schedules the next PONG round."""
        bridge._broadcast_pong()

        mock_hass.loop.call_later.assert_called_with(
            PONG_BROADCAST_INTERVAL_S, bridge._broadcast_pong
        )

    def test_updates_pong_unsub(self, bridge, mock_hass):
        """_pong_unsub is updated with the new timer handle."""
        timer_handle = MagicMock()
        mock_hass.loop.call_later.return_value = timer_handle
        old_unsub = bridge._pong_unsub

        bridge._broadcast_pong()

        assert bridge._pong_unsub is timer_handle
        assert bridge._pong_unsub is not old_unsub


# =========================================================================
# 4. _on_registry_changed
# =========================================================================


class TestOnRegistryChanged:
    """_on_registry_changed — proactive PONG on hash changes."""

    def test_sends_pong_to_all_users(self, bridge, mock_registry, mock_hass):
        """PONG is sent to every active user when registry changes."""
        mock_registry.all_users.return_value = [
            {"hash": "u1", "name": "Alice", "role": "owner"},
            {"hash": "u2", "name": "Bob", "role": "regular"},
        ]

        bridge._on_registry_changed("d")

        mock_registry.get_hashes.assert_called_once()
        assert mock_hass.async_create_task.call_count == 2

    def test_no_users_no_tasks(self, bridge, mock_registry, mock_hass):
        """With no users, no async tasks are created."""
        bridge._on_registry_changed("d")

        mock_hass.async_create_task.assert_not_called()


# =========================================================================
# 5. async_stop
# =========================================================================


class TestAsyncStop:
    """async_stop — clean up subscriptions and timers."""

    async def test_removes_state_change_listener(
        self, bridge, mock_hass
    ):
        """Listener unsubscriber is called and reference cleared."""
        unsub = MagicMock(name="unsub")
        mock_hass.bus.async_listen.return_value = unsub

        await bridge.async_start()
        assert bridge._unsub_listener is not None

        await bridge.async_stop()

        unsub.assert_called_once()
        assert bridge._unsub_listener is None

    async def test_cancels_pong_timer(
        self, bridge, mock_hass
    ):
        """PONG timer is cancelled and reference cleared."""
        pong_timer = MagicMock(name="pong_timer")
        mock_hass.loop.call_later.return_value = pong_timer

        await bridge.async_start()
        assert bridge._pong_unsub is not None

        await bridge.async_stop()

        pong_timer.cancel.assert_called_once()
        assert bridge._pong_unsub is None

    async def test_clears_registry_callback(
        self, bridge, mock_registry
    ):
        """Registry callback is replaced with noop if it points at bridge."""
        await bridge.async_start()

        # Before stop, callback should be the bridge's bound method
        assert mock_registry.get_on_changed() == bridge._on_registry_changed

        await bridge.async_stop()

        # After stop, callback should be a noop, not the bridge's method
        current_cb = mock_registry.get_on_changed()
        assert current_cb is not None
        assert current_cb != bridge._on_registry_changed

    async def test_idempotent_when_not_started(
        self, bridge, mock_registry
    ):
        """Calling stop before start does not crash or touch registry."""
        await bridge.async_stop()

        assert bridge._unsub_listener is None
        assert bridge._pong_unsub is None
        mock_registry.set_on_changed.assert_not_called()

    async def test_preserves_external_registry_callback(
        self, bridge, mock_registry
    ):
        """If registry callback was replaced externally, stop does not overwrite."""
        await bridge.async_start()

        # External code replaced the callback
        external_cb = lambda s: None
        mock_registry.set_on_changed(external_cb)

        await bridge.async_stop()

        # External callback should be left intact
        assert mock_registry.get_on_changed() is external_cb
        assert mock_registry.set_on_changed.call_count == 2  # start + external set
