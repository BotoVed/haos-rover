"""Options flow for Rover integration."""
from __future__ import annotations

import json
import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.selector import (
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
)

from .const import (
    DEFAULT_TCP_PORT,
    PONG_BROADCAST_INTERVAL_S,
    QR_FORMAT_VERSION,
    TYPE_DEFS,
)

_LOGGER = logging.getLogger(__name__)


class RoverOptionsFlow(config_entries.OptionsFlowWithConfigEntry):
    """Rover options flow — multi-step menu."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        super().__init__(config_entry)
        self._short_id: int | None = None
        self._pending_hash: str | None = None

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Show main menu."""
        runtime = getattr(self.config_entry, "runtime_data", None)
        if runtime is None or runtime.registry is None:
            return self.async_abort(reason="not_loaded")

        return self.async_show_menu(
            step_id="init",
            menu_options=[
                "general",
                "network",
                "devices",
                "remove_device",
                "test_device",
                "users",
                "pending",
                "config",
            ],
        )

    async def async_step_general(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """General settings: server name, ping interval."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current = self.options
        return self.async_show_form(
            step_id="general",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        "server_name",
                        default=current.get("server_name", "Rover Hub"),
                    ): TextSelector(),
                    vol.Optional(
                        "ping_interval",
                        default=current.get(
                            "ping_interval", PONG_BROADCAST_INTERVAL_S
                        ),
                    ): NumberSelector(
                        NumberSelectorConfig(min=1, max=60, step=1)
                    ),
                }
            ),
        )

    async def async_step_network(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Network settings: TCP port, IP, SSID."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current = self.options
        return self.async_show_form(
            step_id="network",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        "tcp_port",
                        default=current.get("tcp_port", DEFAULT_TCP_PORT),
                    ): NumberSelector(
                        NumberSelectorConfig(min=1024, max=65535, step=1)
                    ),
                    vol.Optional(
                        "local_ip", default=current.get("local_ip", "")
                    ): TextSelector(),
                    vol.Optional(
                        "ssid", default=current.get("ssid", "")
                    ): TextSelector(),
                }
            ),
        )

    async def async_step_devices(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Add devices via entity picker."""
        runtime = getattr(self.config_entry, "runtime_data", None)
        if runtime is None or runtime.registry is None:
            return self.async_abort(reason="not_loaded")

        if user_input is not None:
            entity_ids = user_input.get("entities", [])
            type_str = user_input.get("type", "")
            type_code = type_str.split(" — ")[0].strip() if " — " in type_str else type_str
            area_id = user_input.get("area_id")

            for entity_id in entity_ids:
                try:
                    name = user_input.get("name", entity_id.split(".")[-1])
                    await runtime.registry.add_device(
                        entity_id, name, type_code, area_id
                    )
                except ValueError as err:
                    _LOGGER.warning("Device add skipped %s: %s", entity_id, err)
            return await self.async_step_init()

        # Build device type options for selector
        type_options = [
            f"{k} — {v['name']} ({v['domain']})" for k, v in TYPE_DEFS.items()
        ]

        return self.async_show_form(
            step_id="devices",
            data_schema=vol.Schema(
                {
                    vol.Required("entities"): EntitySelector(
                        EntitySelectorConfig(multiple=True)
                    ),
                    vol.Required("type"): SelectSelector(
                        SelectSelectorConfig(
                            options=type_options,
                            mode=SelectSelectorMode.LIST,
                        )
                    ),
                    vol.Optional("name"): TextSelector(),
                    vol.Optional("area_id"): NumberSelector(
                        NumberSelectorConfig(min=0, max=65535, step=1)
                    ),
                }
            ),
        )

    async def async_step_remove_device(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Remove a device."""
        runtime = getattr(self.config_entry, "runtime_data", None)
        if runtime is None or runtime.registry is None:
            return self.async_abort(reason="not_loaded")

        if user_input is not None:
            id_str = user_input["device_id"]
            short_id = int(id_str.split(" — ")[0].strip() if " — " in id_str else id_str)
            await runtime.registry.remove_device(short_id)
            return await self.async_step_init()

        device_options = [
            f"{d['short_id']} — {d['name']} ({d['type']})"
            for d in runtime.registry.all_devices()
        ]
        if not device_options:
            return self.async_abort(reason="no_devices")

        return self.async_show_form(
            step_id="remove_device",
            data_schema=vol.Schema(
                {
                    vol.Required("device_id"): SelectSelector(
                        SelectSelectorConfig(
                            options=device_options, mode=SelectSelectorMode.LIST
                        )
                    ),
                }
            ),
        )

    async def async_step_test_device(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Select device to test."""
        runtime = getattr(self.config_entry, "runtime_data", None)
        if runtime is None or runtime.registry is None:
            return self.async_abort(reason="not_loaded")

        if user_input is not None:
            id_str = user_input["device_id"]
            self._short_id = int(id_str.split(" — ")[0].strip() if " — " in id_str else id_str)
            return await self.async_step_test_action()

        device_options = [
            f"{d['short_id']} — {d['name']} ({d['type']})"
            for d in runtime.registry.all_devices()
        ]
        if not device_options:
            return self.async_abort(reason="no_devices")

        return self.async_show_form(
            step_id="test_device",
            data_schema=vol.Schema(
                {
                    vol.Required("device_id"): SelectSelector(
                        SelectSelectorConfig(
                            options=device_options, mode=SelectSelectorMode.LIST
                        )
                    ),
                }
            ),
        )

    async def async_step_test_action(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Send test CMD to selected device via direct service call."""
        if user_input is not None:
            runtime = getattr(self.config_entry, "runtime_data", None)
            if runtime and runtime.registry and self._short_id:
                device = runtime.registry.get_device(self._short_id)
                if device:
                    from .commands import build_service_call

                    action = user_input.get("action", "turn_on")
                    calls = build_service_call(
                        device["type"], {"s": action == "turn_on"}
                    )
                    for domain, svc, service_data in calls:
                        await runtime.hass.services.async_call(
                            domain,
                            svc,
                            service_data,
                            target={"entity_id": [device["entity_id"]]},
                            blocking=True,
                        )
            self._short_id = None
            return await self.async_step_init()

        return self.async_show_form(
            step_id="test_action",
            data_schema=vol.Schema(
                {
                    vol.Required("action", default="turn_on"): SelectSelector(
                        SelectSelectorConfig(
                            options=["turn_on", "turn_off"],
                            mode=SelectSelectorMode.LIST,
                        )
                    ),
                }
            ),
        )

    async def async_step_users(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """List and revoke users."""
        runtime = getattr(self.config_entry, "runtime_data", None)
        if runtime is None or runtime.registry is None:
            return self.async_abort(reason="not_loaded")

        if user_input is not None:
            hash_val = user_input.get("user_hash", "")
            if hash_val:
                key = hash_val.split(" — ")[0].strip()
                await runtime.registry.revoke_user(key)
            return await self.async_step_init()

        user_options = [
            f"{u['hash']} — {u['name']} ({u['role']})"
            for u in runtime.registry.all_users()
        ]
        if not user_options:
            return self.async_abort(reason="no_users")

        return self.async_show_form(
            step_id="users",
            data_schema=vol.Schema(
                {
                    vol.Required("user_hash"): SelectSelector(
                        SelectSelectorConfig(
                            options=user_options, mode=SelectSelectorMode.LIST
                        )
                    ),
                }
            ),
        )

    async def async_step_pending(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Approve pending remotes."""
        runtime = getattr(self.config_entry, "runtime_data", None)
        if runtime is None or runtime.registry is None:
            return self.async_abort(reason="not_loaded")

        if user_input is not None:
            hash_val = user_input.get("pending_hash", "")
            if hash_val:
                key = hash_val.split(" — ")[0].strip()
                if user_input.get("action") == "approve":
                    await runtime.registry.approve_pending(key)
                else:
                    await runtime.registry.deny_pending(key)
            return await self.async_step_init()

        pending = runtime.registry.all_pending()
        if not pending:
            return self.async_abort(reason="no_pending")

        pending_options = [f"{p['hash']} — {p['name']}" for p in pending]
        return self.async_show_form(
            step_id="pending",
            data_schema=vol.Schema(
                {
                    vol.Required("pending_hash"): SelectSelector(
                        SelectSelectorConfig(
                            options=pending_options, mode=SelectSelectorMode.LIST
                        )
                    ),
                    vol.Required("action", default="approve"): SelectSelector(
                        SelectSelectorConfig(
                            options=["approve", "revoke"],
                            mode=SelectSelectorMode.LIST,
                        )
                    ),
                }
            ),
        )

    async def async_step_config(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Show config and QR code."""
        runtime = getattr(self.config_entry, "runtime_data", None)
        if runtime is None or runtime.registry is None:
            return self.async_abort(reason="not_loaded")

        if user_input is not None:
            return await self.async_step_init()

        # Generate QR payload
        qr_data = {
            "v": QR_FORMAT_VERSION,
            "dst": runtime.identity_hash,
        }
        qr_json = json.dumps(qr_data, separators=(",", ":"))

        import urllib.parse

        qr_url = (
            f"https://api.qrserver.com/v1/create-qr-code/"
            f"?size=300x300&data={urllib.parse.quote(qr_json)}"
        )

        hashes = runtime.registry.get_hashes()

        return self.async_show_form(
            step_id="config",
            data_schema=vol.Schema({}),
            description_placeholders={
                "qr": f"![QR]({qr_url})",
                "identity": runtime.identity_hash or "unknown",
                "payload": qr_json,
                "hash_m": hashes.get("m", ""),
                "hash_u": hashes.get("u", ""),
                "hash_a": hashes.get("a", ""),
                "hash_d": hashes.get("d", ""),
            },
        )
