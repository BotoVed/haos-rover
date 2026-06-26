"""Options flow for Rover integration."""
from __future__ import annotations

import base64
import io
import json
import logging
import os
import urllib.parse
from pathlib import Path
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
    DOMAIN_TO_TYPE,
)

_LOGGER = logging.getLogger(__name__)


def _detect_usb_devices() -> list[dict[str, str]]:
    """Detect connected USB serial devices (RNode candidates)."""
    try:
        import serial.tools.list_ports  # noqa: PLC0415
    except ImportError:
        _LOGGER.warning("pyserial not installed — USB device detection unavailable")
        return []

    devices = []
    try:
        ports = serial.tools.list_ports.comports()
        for port in ports:
            desc = (port.description or "").lower()
            if any(keyword in desc for keyword in ["usb serial", "rnode", "cp210", "ch340", "ftdi", "usb-to-serial"]):
                devices.append({
                    "value": port.device,
                    "label": f"{port.device} — {port.description}",
                })
    except Exception as err:
        _LOGGER.warning("USB device detection failed: %s", err)
    return devices


def _build_qr_image_url(payload: str, size: int = 300) -> str:
    """Build a QR code image URL using the qrserver.com API."""
    encoded = urllib.parse.quote(payload)
    return f"https://api.qrserver.com/v1/create-qr-code/?size={size}x{size}&data={encoded}"


def _generate_qr_png(data: str) -> bytes:
    """Generate QR code PNG bytes locally using segno (no external services)."""
    import segno
    qr = segno.make(data, error="L")
    buffer = io.BytesIO()
    qr.save(buffer, kind="png", scale=10, border=2)
    return buffer.getvalue()


class RoverOptionsFlow(config_entries.OptionsFlowWithConfigEntry):
    """Rover options flow — multi-step menu."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        super().__init__(config_entry)
        self._short_id: int | None = None

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Show main menu."""
        runtime = getattr(self.config_entry, "runtime_data", None)
        if runtime is None or runtime.registry is None:
            return self.async_abort(reason="not_loaded")

        return self.async_show_menu(
            step_id="init",
            menu_options={
                "general": "General Settings",
                "add_devices": "Manage Device",
                "test_device": "Test Device",
                "users": "Manage Users",
                "config": "RC connecting",
            },
        )

    async def async_step_general(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """General settings: server name, ping interval, network."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current = self.options
        usb_devices = await self.hass.async_add_executor_job(_detect_usb_devices)
        if usb_devices:
            usb_selector_options = [
                {"value": d["value"], "label": d["label"]}
                for d in usb_devices
            ]
            default_usb = current.get("usb_device", usb_devices[0]["value"])
        else:
            usb_selector_options = [{"value": "none", "label": "No USB devices found"}]
            default_usb = "none"

        return self.async_show_form(
            step_id="general",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        "server_name",
                        default=current.get("server_name", "Rover Hub"),
                    ): TextSelector(),
                    vol.Optional(
                        "usb_device",
                        default=default_usb,
                    ): SelectSelector(
                        SelectSelectorConfig(
                            options=usb_selector_options,
                            mode=SelectSelectorMode.DROPDOWN,
                        )
                    ),
                }
            ),
        )

    

    async def async_step_add_devices(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage device registration via entity picker with diff save."""
        return await self.async_step_device_picker(user_input)

    async def async_step_device_picker(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage device registration via entity picker with diff save."""
        runtime = getattr(self.config_entry, "runtime_data", None)
        if runtime is None or runtime.registry is None:
            return self.async_abort(reason="not_loaded")

        registry = runtime.registry
        existing_devices = registry.all_devices()
        existing_entity_ids = [d["entity_id"] for d in existing_devices]

        if user_input is not None:
            new_entity_ids = set(user_input.get("entities", []))
            old_entity_ids = set(existing_entity_ids)

            # Add new devices
            for entity_id in new_entity_ids - old_entity_ids:
                domain = entity_id.split(".")[0]
                type_code = DOMAIN_TO_TYPE.get(domain)
                if type_code is None:
                    _LOGGER.warning(
                        "Device add skipped %s: unknown domain '%s'",
                        entity_id, domain,
                    )
                    continue
                try:
                    state = self.hass.states.get(entity_id)
                    name = (
                        state.attributes.get(
                            "friendly_name", entity_id.split(".")[-1]
                        )
                        if state
                        else entity_id.split(".")[-1]
                    )
                    await registry.add_device(
                        entity_id, name, type_code, area_id=None
                    )
                except ValueError as err:
                    _LOGGER.warning("Device add skipped %s: %s", entity_id, err)

            # Remove devices that were unchecked
            for entity_id in old_entity_ids - new_entity_ids:
                for d in existing_devices:
                    if d["entity_id"] == entity_id:
                        await registry.remove_device(d["short_id"])
                        _LOGGER.info("Device removed: %s", entity_id)
                        break

            return await self.async_step_init()

        # Pre-fill entities with currently registered devices
        return self.async_show_form(
            step_id="device_picker",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        "entities", default=existing_entity_ids
                    ): EntitySelector(
                        EntitySelectorConfig(multiple=True)
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

    async def async_step_config(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Show QR code for remote registration per spec v0.5.0 §4.2."""
        runtime = getattr(self.config_entry, "runtime_data", None)
        if runtime is None or runtime.registry is None:
            return self.async_abort(reason="not_loaded")

        if user_input is not None:
            return self.async_create_entry(title="", data={})

        # Generate fresh QR token (one-time, one active)
        qr_token = runtime.registry.generate_qr_token()
        meta = runtime.registry.get_meta()
        server_name = meta.get("server_name", "Rover Hub")
        pk_base64 = runtime.transport.get_public_key_base64() if runtime.transport else ""
        tcp_port = meta.get("tcp_port", 4242)
        local_ip = meta.get("local_ip", "")
        tcp_endpoint = f"{local_ip}:{tcp_port}" if local_ip else ""

        qr_data = {
            "rvr": {
                "fmt": QR_FORMAT_VERSION,
                "dst": runtime.identity_hash or "",
                "nm": server_name,
                "pk": pk_base64,
                "tcp": tcp_endpoint,
                "uid": qr_token,
            }
        }
        qr_json = json.dumps(qr_data, separators=(",", ":"))

        # Generate QR PNG and embed as base64 data URI (bypasses CSP)
        qr_url = ""
        try:
            qr_png = _generate_qr_png(qr_json)
            qr_b64 = base64.b64encode(qr_png).decode()
            qr_url = f"data:image/png;base64,{qr_b64}"
            
            # Also save to www/ for direct access
            www_dir = self.hass.config.path("www")
            qr_path = Path(www_dir) / "rover_qr.png"

            def _save_qr() -> None:
                os.makedirs(www_dir, exist_ok=True)
                qr_path.write_bytes(qr_png)

            await self.hass.async_add_executor_job(_save_qr)
        except Exception as err:
            _LOGGER.warning("Failed to generate QR: %s", err)

        hashes = runtime.registry.get_hashes()

        return self.async_show_form(
            step_id="config",
            data_schema=vol.Schema({}),
            description_placeholders={
                "qr_url": qr_url if qr_url else "_(QR generation failed)_",
                "identity": runtime.identity_hash or "unknown",
                "payload": qr_json,
                "server_name": server_name,
                "pk": pk_base64[:32] + "..." if len(pk_base64) > 32 else pk_base64,
                "tcp": tcp_endpoint or "(not set)",
                "uid": qr_token,
                "hash_m": hashes.get("m", ""),
                "hash_u": hashes.get("u", ""),
                "hash_a": hashes.get("a", ""),
                "hash_d": hashes.get("d", ""),
            },
        )
