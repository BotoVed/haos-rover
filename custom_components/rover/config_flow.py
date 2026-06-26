"""Config flow for Rover integration."""
from __future__ import annotations

import voluptuous as vol

from homeassistant import config_entries

from .const import DOMAIN


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
            )

        return self.async_create_entry(title="Rover", data={})

    @staticmethod
    def async_get_options_flow(config_entry):
        from .options_flow import RoverOptionsFlow
        return RoverOptionsFlow(config_entry)
