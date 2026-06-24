"""Config flow for Rover integration."""
from __future__ import annotations

from homeassistant import config_entries
from homeassistant.helpers import config_validation as cv

from .const import DOMAIN, DEFAULT_TCP_PORT

import voluptuous as vol


STEP_USER_DATA_SCHEMA = vol.Schema({})


class RoverConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Rover."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        if user_input is None:
            return self.async_show_form(
                step_id="user",
                data_schema=STEP_USER_DATA_SCHEMA,
                description_placeholders={
                    "title": "Rover",
                    "description": "Rover will create a Reticulum identity and prepare "
                                   "the mesh transport. You can add devices and manage "
                                   "remotes in the integration options.",
                },
            )

        return self.async_create_entry(title="Rover", data={})
