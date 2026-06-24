"""Rover — Remote Over Radio for Home Assistant."""
from __future__ import annotations

__version__ = "0.0.2"

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN
from .codec import encode, decode

_LOGGER = logging.getLogger(f"custom_components.{DOMAIN}")


class RoverRuntimeData:
    """Runtime data for Rover integration."""

    def __init__(self) -> None:
        self.registry = None
        self.transport = None
        self.handlers = None
        self.dispatcher = None
        self.bridge = None
        self.identity_hash = None


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """No YAML setup."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Rover from a config entry."""
    runtime = RoverRuntimeData()

    # Create runtime data and attach to hass
    entry.runtime_data = runtime

    _LOGGER.info("Rover %s setup complete", __version__)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload Rover config entry."""
    runtime = getattr(entry, "runtime_data", None)
    if runtime is None:
        return True

    _LOGGER.info("Rover unloaded")
    return True
