"""RNS/LXMF transport module for Rover."""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Callable

import RNS
import LXMF

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .codec import encode
from .const import (
    AWAIT_PATH_TIMEOUT_S,
    IDENTITY_HASH_LEN,
    LOGGER_TRN,
    OPPORTUNISTIC_THRESHOLD_BYTES,
    TP_CMD,
    TP_PING_PONG,
    TP_REGISTER,
    TP_REQ,
)
from .registry import RoverRegistry


_OUT_KEY_MAP: dict[str, int] = {
    # Message envelope
    "tp": 1, "section": 2, "h": 3, "data": 4,
    # State/command fields  
    "v": 5, "s": 6, "b": 7, "ct": 8, "rgb": 9, "ef": 10,
    "cv": 11, "p": 12, "ti": 13,
    "hvac": 14, "t": 15, "th": 16, "tl": 17, "fan": 18,
    "preset": 19, "swing_h": 20, "swing_v": 21,
    "ms": 22, "vol": 23, "seek": 24,
    "al": 25, "sp": 26, "osc": 27, "dir": 28,
    "u": 29, "tc": 30,
    # Config section fields
    "id": 31, "name": 32, "hash": 33, "role": 34,
    "type": 35, "entity_id": 36, "short_id": 37,
    "area_id": 38, "enabled": 39,
    "server_name": 40, "version": 41, "tcp_port": 42,
    "local_ip": 43, "ssid": 44,
    # QR/registration
    "uid": 45, "dst": 46, "src": 47,
    "qr_host": 48, "qr_port": 49, "qr_identity": 50, "qr_version": 51,
    # Config section containers
    "devices": 52, "users": 53, "areas": 54, "meta": 55,
    "sections": 56, "pending": 57, "requested_at": 58,
    # Media
    "title": 59, "artist": 60, "album": 61, "dur": 62, "pos": 63, "muted": 64,
    # Status
    "identity_hash": 65, "dt": 66, "st": 67, "br": 68, "co": 69, "md": 70,
    # Misc
    "device_type": 71, "msg": 72,
}


def _to_wire(fields: dict) -> dict:
    wire: dict = {}
    for k, v in fields.items():
        key = _OUT_KEY_MAP.get(k, k) if isinstance(k, str) else k
        wire[int(key) if not isinstance(key, int) else key] = v
    return wire


class RoverTransport:
    def __init__(
        self,
        hass: HomeAssistant,
        config_dir: str,
        on_message: Callable,
        tcp_port: int = 0,
    ) -> None:
        self._hass = hass
        self._config_dir = config_dir
        self._on_message = on_message
        self._tcp_port = tcp_port
        self._logger = logging.getLogger(LOGGER_TRN)
        self._identity: RNS.Identity | None = None
        self._router: LXMF.LXMRouter | None = None
        self._delivery_dest = None
        self._shutdown = False

    async def async_start(self) -> str:
        """Initialize RNS/LXMF transport in executor thread."""

        def _init() -> str:
            # Create config dir
            os.makedirs(self._config_dir, exist_ok=True)

            # Load/create identity
            identity_path = os.path.join(self._config_dir, "identity")
            if os.path.exists(identity_path):
                self._identity = RNS.Identity.from_file(identity_path)
            else:
                self._identity = RNS.Identity()
                self._identity.to_file(identity_path)

            # Write RNS config
            config_path = os.path.join(self._config_dir, "reticulum.json")
            with open(config_path, "w") as f:
                f.write(
                    '{\n  "interfaces": [\n'
                    '    {\n'
                    f'      "type": "TCPServerInterface",\n'
                f'      "port": {self._tcp_port},\n'
                f'      "enabled": true\n'
                '    }\n'
                '  ]\n'
                '}}'
                )

            # Initialize RNS
            RNS.Reticulum(configdir=self._config_dir)
            RNS.loglevel = RNS.LOG_EXTREME
            RNS.logdest = RNS.LOG_STDOUT

            # Create LXMF router
            storage_path = os.path.join(self._config_dir, "lxmf_storage")
            os.makedirs(storage_path, exist_ok=True)
            self._router = LXMF.LXMRouter(
                identity=self._identity, storagepath=storage_path
            )

            # Register delivery identity
            self._delivery_dest = self._router.register_delivery_identity(
                self._identity, "Rover", None
            )
            self._delivery_dest.announce()

            # Register callback
            self._router.register_delivery_callback(self._on_lxmf_message)

            return self._identity.hash.hex()

        # Run ALL synchronous init in executor thread
        identity_hash = await self._hass.async_add_executor_job(_init)
        self._identity_hash = identity_hash

        # Schedule async periodic announce (this is safe for event loop)
        asyncio.ensure_future(self._periodic_path_announces())

        return identity_hash

    async def _periodic_path_announces(self) -> None:
        while not self._shutdown:
            if self._identity:
                try:
                    await self._hass.async_add_executor_job(
                        RNS.Transport.request_path, self._identity.hash
                    )
                except Exception:
                    pass
            await asyncio.sleep(60)

    def _on_lxmf_message(self, message: LXMF.LXMessage) -> None:
        if self._shutdown:
            return
            
        # Extract fields
        if isinstance(message.fields, dict):
            fields = message.fields
        else:
            # Decode bytes via codec.decode()
            from .codec import decode
            fields = decode(message.fields)
        
        # Call dispatcher callback
        self._on_message(message.source_hash, fields)

    async def send(self, destination_hash_hex: str, fields: dict) -> bool:
        loop = asyncio.get_event_loop()
        
        # Recall remote identity
        dst_bytes = bytes.fromhex(destination_hash_hex)
        remote_identity = RNS.Identity.recall(dst_bytes)
        if remote_identity is None:
            # Request path and return False
            try:
                RNS.Transport.request_path(dst_bytes)
            except Exception as e:
                self._logger.error("Error requesting path: %s", e)
            return False
        
        # Create destination
        destination = RNS.Destination(
            remote_identity, RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery"
        )
        
        # Convert fields to wire format
        wire_fields = _to_wire(fields)
        
        # Encode to bytes
        payload = encode(wire_fields)
        
        # Determine delivery method
        desired_method = (
            LXMF.LXMessage.OPPORTUNISTIC
            if len(payload) <= OPPORTUNISTIC_THRESHOLD_BYTES
            else LXMF.LXMessage.DIRECT
        )
        
        # Create LXMessage
        msg = LXMF.LXMessage(
            destination, self._identity, content=b"", title=b"", desired_method=desired_method
        )
        msg.fields = wire_fields
        
        # Register callbacks
        msg.register_delivery_callback(self._on_delivery)
        msg.register_failed_callback(self._on_failed)
        
        # Send message
        self._router.handle_outbound(msg)
        return True

    def _on_delivery(self, msg: LXMF.LXMessage) -> None:
        self._logger.debug("Message delivered: %s", msg.hash.hex())

    def _on_failed(self, msg: LXMF.LXMessage) -> None:
        self._logger.warning("Message delivery failed: %s", msg.hash.hex())

    async def shutdown(self) -> None:
        self._shutdown = True

        def _do_shutdown() -> None:
            if self._router:
                try:
                    self._router.stop()
                except Exception:
                    pass

        await self._hass.async_add_executor_job(_do_shutdown)
        self._router = None
        self._identity = None
        self._delivery_dest = None
        self._logger.info("Transport shutdown complete")

    def set_dispatcher_cb(self, callback: Callable[[bytes, dict], None]) -> None:
        self._on_message = callback
