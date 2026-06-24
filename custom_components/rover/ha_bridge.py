"""HA Bridge for Rover — subscribes to state_changed events and sends PUSH messages."""
from __future__ import annotations

import logging
import time
from typing import Any

from homeassistant.core import Event, HomeAssistant

from .const import (
    LOGGER_HAB,
    PONG_BROADCAST_INTERVAL_S,
    PUSH_THROTTLE_MS,
    SENSOR_PUSH_INTERVAL,
    TP_PING_PONG,
    TP_PUSH,
)
from .registry import RoverRegistry
from .rns_transport import RoverTransport
from .state_extractor import extract_state

_LOGGER = logging.getLogger(LOGGER_HAB)


class RoverHABridge:
    """HA Bridge — connects HA state changes to Rover PUSH protocol."""

    def __init__(
        self,
        hass: HomeAssistant,
        registry: RoverRegistry,
        transport: RoverTransport,
    ) -> None:
        """Initialize the HA Bridge.

        Args:
            hass: HomeAssistant instance
            registry: Rover registry for device/user lookups
            transport: Rover transport for sending messages
        """
        self._hass = hass
        self._registry = registry
        self._transport = transport
        self._logger = _LOGGER
        self._unsub_listener: Any = None
        self._last_push: dict[str, float] = {}
        self._pong_unsub: Any = None

    async def async_start(self) -> None:
        """Start the bridge — subscribe to events, start PONG broadcast.

        1. Subscribe to HA state_changed bus events
        2. Schedule periodic PONG broadcast
        3. Subscribe to registry changes
        """
        self._unsub_listener = self._hass.bus.async_listen(
            "state_changed", self._on_state_change
        )
        self._pong_unsub = self._hass.loop.call_later(
            PONG_BROADCAST_INTERVAL_S, self._broadcast_pong
        )
        self._registry.set_on_changed(self._on_registry_changed)

    async def async_stop(self) -> None:
        """Stop the bridge — clean up subscriptions and timers."""
        if self._unsub_listener is not None:
            self._unsub_listener()
            self._unsub_listener = None

        if self._pong_unsub is not None:
            self._pong_unsub.cancel()
            self._pong_unsub = None

        # Clear registry callback if it's still pointing at us
        if self._registry.get_on_changed() == self._on_registry_changed:
            self._registry.set_on_changed(lambda _: None)

    async def _on_state_change(self, event: Event) -> None:
        """Handle state_changed events for registered Rover devices.

        Only processes entities that are registered as Rover devices.
        Applies per-device throttling (500ms default, 5s for sensors).
        """
        entity_id = event.data.get("entity_id")
        if not entity_id:
            return

        device = self._registry.get_device_by_entity_id(entity_id)
        if device is None:
            return

        # Throttle check — per-device cooldown
        now = time.monotonic()
        last = self._last_push.get(entity_id, 0.0)
        device_type = device["type"]

        if device_type == "SE":
            # Sensors have longer cooldown
            if now - last < SENSOR_PUSH_INTERVAL:
                return
        else:
            if now - last < PUSH_THROTTLE_MS / 1000.0:
                return

        new_state = event.data.get("new_state")
        if new_state is None:
            return

        try:
            state_fields = extract_state(
                new_state.state, new_state.attributes, device_type
            )
        except ValueError:
            self._logger.exception(
                "Failed to extract state for %s (type=%s)", entity_id, device_type
            )
            return

        self._last_push[entity_id] = now

        # Build PUSH message and send to all active remotes
        fields: dict[str, Any] = {
            "tp": TP_PUSH,
            "id": device["short_id"],
            **state_fields,
        }

        for user in self._registry.all_users():
            await self._transport.send(user["hash"], fields)

    def _broadcast_pong(self) -> None:
        """Periodic PONG broadcast to all active remotes.

        Sends current section hashes to all users and reschedules itself.
        """
        hashes = self._registry.get_hashes()
        fields: dict[str, Any] = {"tp": TP_PING_PONG, **hashes}

        for user in self._registry.all_users():
            self._hass.async_create_task(
                self._transport.send(user["hash"], fields)
            )

        # Schedule next broadcast
        self._pong_unsub = self._hass.loop.call_later(
            PONG_BROADCAST_INTERVAL_S, self._broadcast_pong
        )

    def _on_registry_changed(self, section: str) -> None:
        """Handle registry changes — broadcast PONG with updated hashes.

        Called synchronously from registry. Creates async tasks for sends.
        """
        hashes = self._registry.get_hashes()
        fields: dict[str, Any] = {"tp": TP_PING_PONG, **hashes}

        for user in self._registry.all_users():
            self._hass.async_create_task(
                self._transport.send(user["hash"], fields)
            )
