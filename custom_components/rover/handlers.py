"""Message handlers for Rover protocol."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.service import ServiceTarget

from .const import (
    TP_CMD,
    TP_PING_PONG,
    TP_REQ,
    TP_REGISTER,
    TP_FORBIDDEN,
    TP_CONFIG,
    TP_STATUS,
    LOGGER_HND,
)
from .commands import build_service_call
from .state_extractor import extract_state

_LOGGER = logging.getLogger(LOGGER_HND)


class RoverHandlers:
    """Message handlers for Rover protocol."""

    def __init__(
        self,
        hass: HomeAssistant,
        registry: Any,
        transport: Any,
        dispatcher: Any,
    ) -> None:
        """Initialize handlers."""
        self._hass = hass
        self._registry = registry
        self._transport = transport
        self._dispatcher = dispatcher

    def register(self) -> None:
        """Register handlers with dispatcher."""
        self._dispatcher.register_handler(TP_CMD, self._handle_cmd)
        self._dispatcher.register_handler(TP_PING_PONG, self._handle_ping)
        self._dispatcher.register_handler(TP_REQ, self._handle_req)
        self._dispatcher.register_handler(TP_REGISTER, self._handle_register)

    @staticmethod
    def _get_sender_hash(src_bytes: bytes) -> str:
        """Get sender hash from source bytes."""
        return src_bytes.hex()

    def _is_authorized(self, src_hash: str) -> bool:
        """Check if sender is authorized."""
        return self._registry.is_approved(src_hash)

    async def _send_forbidden(self, src_hash: str, reason: str = "forbidden") -> None:
        """Send forbidden message."""
        await self._transport.send(src_hash, {"tp": TP_FORBIDDEN, "reason": reason})

    async def _send_config_section(
        self, src_hash: str, section_key: str
    ) -> None:
        """Send config section data."""
        if section_key == "m":
            data = self._registry.get_meta()
        elif section_key == "u":
            data = {
                "users": self._registry.all_users(),
                "pending": self._registry.all_pending(),
            }
        elif section_key == "a":
            data = self._registry.all_areas()
        elif section_key == "d":
            data = self._registry.all_devices()
        else:
            _LOGGER.error("Unknown section key: %s", section_key)
            return

        hash_val = self._registry.get_hashes().get(section_key, "")
        await self._transport.send(
            src_hash,
            {"tp": TP_CONFIG, "section": section_key, "data": data, "h": hash_val},
        )

    async def _send_status(self, src_hash: str) -> None:
        """Send status for all devices."""
        status_data = []
        for device in self._registry.all_devices():
            entity_id = device["entity_id"]
            device_type = device["type"]
            ha_state = self._hass.states.get(entity_id)

            if ha_state is None:
                continue

            state_data = extract_state(ha_state.state, ha_state.attributes, device_type)
            status_data.append({"id": device["short_id"], **state_data})

        await self._transport.send(src_hash, {"tp": TP_STATUS, "data": status_data})

    async def _handle_cmd(self, src_bytes: bytes, fields: dict) -> None:
        """Handle CMD message."""
        src_hash = self._get_sender_hash(src_bytes)

        if not self._is_authorized(src_hash):
            await self._send_forbidden(src_hash, "unauthorized")
            return

        device_id = fields.get("id")
        device = self._registry.get_device(device_id)
        if device is None:
            await self._send_forbidden(src_hash, "device_not_found")
            return

        try:
            service_calls = build_service_call(device["type"], fields)
            for domain, service, service_data in service_calls:
                await self._hass.services.async_call(
                    domain,
                    service,
                    service_data,
                    blocking=True,
                    target=ServiceTarget(entity_ids=[device["entity_id"]]),
                )
        except Exception as e:
            _LOGGER.error("Error executing command: %s", e)
            await self._send_forbidden(src_hash, "command_failed")

    async def _handle_ping(self, src_bytes: bytes, fields: dict) -> None:
        """Handle PING message."""
        src_hash = self._get_sender_hash(src_bytes)

        if not self._is_authorized(src_hash):
            await self._send_forbidden(src_hash, "unauthorized")
            return

        client_hashes = {
            "m": fields.get("m"),
            "u": fields.get("u"),
            "a": fields.get("a"),
            "d": fields.get("d"),
        }
        registry_hashes = self._registry.get_hashes()

        sections = []
        diffs = []

        for section in ["m", "u", "a", "d"]:
            if client_hashes[section] != registry_hashes[section]:
                sections.append(section)
                diffs.append(section)

        await self._transport.send(src_hash, {"tp": TP_PING_PONG, "sections": sections, "diffs": diffs})

        if "d" in sections or "d" in diffs:
            await self._send_status(src_hash)

    async def _handle_req(self, src_bytes: bytes, fields: dict) -> None:
        """Handle REQ message."""
        src_hash = self._get_sender_hash(src_bytes)

        if not self._is_authorized(src_hash):
            await self._send_forbidden(src_hash, "unauthorized")
            return

        sections = fields.get("sections", [])
        for section in sections:
            await self._send_config_section(src_hash, section)

        if "d" in sections:
            await self._send_status(src_hash)

    async def _handle_register(self, src_bytes: bytes, fields: dict) -> None:
        """Handle REGISTER message."""
        src_hash = self._get_sender_hash(src_bytes)
        uid = fields.get("uid")
        if not self._registry.consume_qr_token(uid):
            await self._send_forbidden(src_hash, "invalid_uid")
            return

        name = fields.get("name")

        if not await self._registry.add_pending(src_hash, name):
            await self._send_forbidden(src_hash, "pending_limit_exceeded")
            return

        if not await self._registry.approve_pending(src_hash):
            await self._send_forbidden(src_hash, "approval_failed")
            return

        for section in ["m", "u", "a", "d"]:
            await self._send_config_section(src_hash, section)

        await self._send_status(src_hash)
