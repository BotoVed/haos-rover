"""Rover — Remote Over Radio for Home Assistant."""
from __future__ import annotations

__version__ = "0.2.16"

import logging
from typing import Callable

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN, LOGGER_ROOT, STORAGE_KEY, STORAGE_VERSION
from .dispatcher import RoverDispatcher
from .ha_bridge import RoverHABridge
from .handlers import RoverHandlers
from .registry import RoverRegistry
from .rns_transport import RoverTransport
from .services import async_register_services, async_unregister_services

PLATFORMS: list[str] = []
_LOGGER = logging.getLogger(LOGGER_ROOT)


class RoverRuntimeData:
    """Runtime data for Rover integration."""

    def __init__(self) -> None:
        self.registry: RoverRegistry | None = None
        self.transport: RoverTransport | None = None
        self.handlers: RoverHandlers | None = None
        self.dispatcher: RoverDispatcher | None = None
        self.bridge: RoverHABridge | None = None
        self.identity_hash: str | None = None
        self._store: Store | None = None
        self._unsub_stop: Callable | None = None


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """No YAML setup."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Rover from a config entry."""
    runtime = RoverRuntimeData()

    # 1. Registry
    runtime.registry = RoverRegistry(hass)
    await runtime.registry.async_load()

    # 2. Dispatcher
    runtime.dispatcher = RoverDispatcher(runtime.registry)

    # 3. Transport
    config_dir = hass.config.path("rover")
    runtime.transport = RoverTransport(
        hass, config_dir, runtime.dispatcher.dispatch,
        tcp_port=entry.data.get("tcp_port", 4242),
    )

    # 4. Handlers
    runtime.handlers = RoverHandlers(
        hass, runtime.registry, runtime.transport, runtime.dispatcher,
    )
    await runtime.handlers.register()

    # 5. HA Bridge
    runtime.bridge = RoverHABridge(
        hass, runtime.registry, runtime.transport,
    )

    # Set runtime_data early so async_unload_entry can clean up
    # even if transport start throws
    entry.runtime_data = runtime

    # 6. Start components in dependency order
    identity_hash = await runtime.transport.async_start()
    runtime.identity_hash = identity_hash
    await runtime.bridge.async_start()

    # 7. Register cleanup on HA stop
    async def _shutdown(event):
        if runtime.transport:
            await runtime.transport.shutdown(full_teardown=True)
        if runtime.bridge:
            await runtime.bridge.async_stop()
        async_unregister_services(hass)
        if runtime._unsub_stop:
            runtime._unsub_stop()
        hass.data.setdefault(DOMAIN, {}).pop(entry.entry_id, None)

    runtime._unsub_stop = hass.bus.async_listen_once(
        EVENT_HOMEASSISTANT_STOP, _shutdown
    )

    # 8. Debug services
    await async_register_services(hass, runtime)

    _LOGGER.info("Rover %s setup complete (identity=%s...)", __version__, identity_hash[:16])
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload Rover config entry."""
    runtime: RoverRuntimeData | None = getattr(entry, "runtime_data", None)
    if runtime is None:
        return True

    # 1. Stop bridge (unsubscribes from state_changed, stops PONG)
    if runtime.bridge:
        await runtime.bridge.async_stop()

    # 2. Stop transport (shuts down LXMF router)
    if runtime.transport:
        await runtime.transport.shutdown()

    # 3. Unregister debug services
    async_unregister_services(hass)

    # 4. Remove stop listener
    if runtime._unsub_stop:
        runtime._unsub_stop()

    # 5. Clean up hass.data
    hass.data.setdefault(DOMAIN, {}).pop(entry.entry_id, None)

    _LOGGER.info("Rover unloaded")
    return True
