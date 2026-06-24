"""Rover debug/test services."""
from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv

from .const import (
    DOMAIN,
    LOGGER_ROOT,
    LOGGER_REG,
    LOGGER_HND,
    LOGGER_RNS,
    LOGGER_TRN,
    LOGGER_HAB,
    TP_CMD,
    TP_PING_PONG,
    TP_REQ,
    TP_REGISTER,
    TP_FORBIDDEN,
    TP_CONFIG,
    TP_STATUS,
    TP_PUSH,
)

if TYPE_CHECKING:
    from . import RoverRuntimeData

_LOGGER = logging.getLogger(LOGGER_ROOT)

SERVICE_SET_LOGLEVEL = "set_loglevel"
SERVICE_SEND_TEST_MESSAGE = "send_test_message"
SERVICE_SIMULATE_INBOUND = "simulate_inbound"
SERVICE_DUMP_REGISTRY = "dump_registry"

LEVEL_MAP = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warning": logging.WARNING,
    "error": logging.ERROR,
}
DEFAULT_LEVELS = {
    LOGGER_ROOT: logging.INFO,
    LOGGER_REG: logging.INFO,
    LOGGER_HND: logging.INFO,
    LOGGER_TRN: logging.DEBUG,
    LOGGER_HAB: logging.DEBUG,
    LOGGER_RNS: logging.WARNING,
}


def _restore_default_levels() -> None:
    for name, lvl in DEFAULT_LEVELS.items():
        logging.getLogger(name).setLevel(lvl)


async def async_register_services(hass: HomeAssistant, runtime: "RoverRuntimeData") -> None:
    """Register Rover debug services."""
    state: dict[str, Any] = {"loglevel_restore_handle": None}

    async def _handle_set_loglevel(call: ServiceCall) -> None:
        level_name = str(call.data.get("level", "info")).lower()
        duration = int(call.data.get("duration_minutes", 30))
        level = LEVEL_MAP.get(level_name)
        if level is None:
            _LOGGER.warning("set_loglevel: invalid level=%r", level_name)
            return

        for name in DEFAULT_LEVELS:
            logging.getLogger(name).setLevel(level)
        _LOGGER.info(
            "Log level set to %s across all Rover loggers for %d min",
            level_name.upper(), duration,
        )

        prev = state.get("loglevel_restore_handle")
        if prev is not None:
            prev.cancel()
        state["loglevel_restore_handle"] = hass.loop.call_later(
            duration * 60, _restore_default_levels,
        )

    async def _handle_send_test(call: ServiceCall) -> None:
        if runtime.transport is None:
            _LOGGER.warning("send_test_message: transport not initialized")
            return
        dst_raw = str(call.data.get("destination_hash", ""))
        if dst_raw == "self":
            if runtime.identity_hash is None:
                _LOGGER.warning("send_test_message: identity_hash not set")
                return
            dst_hex = runtime.identity_hash
        else:
            dst_hex = dst_raw.strip().lower()
        if len(dst_hex) != 64:
            # Allow 32-char input if that's what the transport uses
            pass

        tp = int(call.data["tp"])
        payload = call.data.get("payload", {})
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except json.JSONDecodeError:
                _LOGGER.warning("send_test_message: invalid JSON payload")
                return
        if not isinstance(payload, dict):
            payload = {}

        fields = {"tp": tp, **payload}
        await runtime.transport.send(dst_hex, fields)

    async def _handle_simulate_inbound(call: ServiceCall) -> None:
        if runtime.dispatcher is None:
            return
        src_hex = str(call.data.get("source_hash", "")).strip().lower()
        tp = int(call.data["tp"])
        payload = call.data.get("payload", {})
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except json.JSONDecodeError:
                return
        if not isinstance(payload, dict):
            payload = {}
        authorized = bool(call.data.get("authorized", False))
        fields = {"tp": tp, **payload}
        src_bytes = bytes.fromhex(src_hex)

        needs_cleanup = False
        if authorized and runtime.registry and not runtime.registry.is_approved(src_hex):
            added = await runtime.registry.add_pending(src_hex, "_test_sim")
            if added:
                await runtime.registry.approve_pending(src_hex)
                needs_cleanup = True

        try:
            await runtime.dispatcher.dispatch(src_bytes, fields)
        finally:
            if needs_cleanup and runtime.registry:
                await runtime.registry.revoke_user(src_hex)

    async def _handle_dump_registry(call: ServiceCall) -> None:
        reg = runtime.registry
        if reg is None:
            return
        _LOGGER.info("REG DUMP hashes=%s meta=%s", reg.get_hashes(), reg.get_meta())
        _LOGGER.info("REG DUMP users=%d", len(reg.all_users()))
        _LOGGER.info("REG DUMP devices=%d", len(reg.all_devices()))
        _LOGGER.info("REG DUMP areas=%d", len(reg.all_areas()))
        _LOGGER.info("REG DUMP pending=%d", len(reg.all_pending()))

    if not hass.services.has_service(DOMAIN, SERVICE_SET_LOGLEVEL):
        hass.services.async_register(
            DOMAIN, SERVICE_SET_LOGLEVEL,
            _handle_set_loglevel,
            schema=vol.Schema({
                vol.Required("level"): str,
                vol.Optional("duration_minutes", default=30): cv.positive_int,
            }),
        )
    if not hass.services.has_service(DOMAIN, SERVICE_SEND_TEST_MESSAGE):
        hass.services.async_register(
            DOMAIN, SERVICE_SEND_TEST_MESSAGE,
            _handle_send_test,
            schema=vol.Schema({
                vol.Required("destination_hash"): str,
                vol.Required("tp"): vol.All(int, vol.Range(min=2, max=9)),
                vol.Optional("payload", default={}): vol.Any(dict, str),
            }),
        )
    if not hass.services.has_service(DOMAIN, SERVICE_SIMULATE_INBOUND):
        hass.services.async_register(
            DOMAIN, SERVICE_SIMULATE_INBOUND,
            _handle_simulate_inbound,
            schema=vol.Schema({
                vol.Required("source_hash"): str,
                vol.Required("tp"): vol.All(int, vol.Range(min=2, max=9)),
                vol.Optional("payload", default={}): vol.Any(dict, str),
                vol.Optional("authorized", default=False): bool,
            }),
        )
    if not hass.services.has_service(DOMAIN, SERVICE_DUMP_REGISTRY):
        hass.services.async_register(
            DOMAIN, SERVICE_DUMP_REGISTRY,
            _handle_dump_registry,
        )


def async_unregister_services(hass: HomeAssistant) -> None:
    """Unregister Rover debug services."""
    for name in (
        SERVICE_SET_LOGLEVEL,
        SERVICE_SEND_TEST_MESSAGE,
        SERVICE_SIMULATE_INBOUND,
        SERVICE_DUMP_REGISTRY,
    ):
        if hass.services.has_service(DOMAIN, name):
            hass.services.async_remove(DOMAIN, name)
