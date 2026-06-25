"""RNS/LXMF transport module for Rover."""
from __future__ import annotations

import asyncio
import logging
import os
import signal
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

_RNS_INITIALIZED = False

# Module-level singleton to survive RoverTransport instance re-creation on reload
_LXMF_STATE: dict[str, Any] | None = None
_RNS_INSTANCE_HASH: str | None = None  # Track which Reticulum instance this belongs to

_OUT_KEY_MAP: dict[str, int] = {
    # Message envelope — spec v0.5.0 §3.8: envelope starts at key 0
    "tp": 0, "section": 1, "h": 2, "data": 3,
    # State/command fields (4..29)
    "v": 4, "s": 5, "b": 6, "ct": 7, "rgb": 8, "ef": 9,
    "cv": 10, "p": 11, "ti": 12,
    "hvac": 13, "t": 14, "th": 15, "tl": 16, "fan": 17,
    "preset": 18, "swing_h": 19, "swing_v": 20,
    "ms": 21, "vol": 22, "seek": 23,
    "al": 24, "sp": 25, "osc": 26, "dir": 27,
    "u": 28, "tc": 29,
    # PING/PONG hashes (30..33) — formerly on inbound only
    "m": 30, "a": 31, "d": 32, "diffs": 33,
    # FORBIDDEN/REQ (34)
    "reason": 34,
    # Config section fields (35..46)
    "id": 35, "name": 36, "hash": 37, "role": 38,
    "type": 39, "entity_id": 40, "short_id": 41,
    "area_id": 42, "enabled": 43,
    "server_name": 44, "version": 45, "tcp_port": 46,
    "local_ip": 47, "ssid": 48,
    # QR/registration (49..58)
    "uid": 49, "dst": 50, "src": 51,
    "qr_host": 52, "qr_port": 53, "qr_identity": 54, "qr_version": 55,
    # Config section containers (56..61)
    "devices": 56, "users": 57, "areas": 58, "meta": 59,
    "sections": 60, "pending": 61, "requested_at": 62,
    # Media (63..68)
    "title": 63, "artist": 64, "album": 65, "dur": 66, "pos": 67, "muted": 68,
    # Status (69..74)
    "identity_hash": 69, "dt": 70, "st": 71, "br": 72, "co": 73, "md": 74,
    # Misc (75..76)
    "device_type": 75, "msg": 76,
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
        """Initialize RNS/LXMF transport. Cleanly restarts if already running."""

        def _init() -> str:
            import signal as signal_module
            global _LXMF_STATE, _RNS_INSTANCE_HASH
            
            existing = getattr(RNS.Reticulum, "_Reticulum__instance", None)
            identity_path = os.path.join(self._config_dir, "identity")
            
            if existing is not None:
                self._logger.info("RNS already initialized on reload — reusing instance")
            else:
                try:
                    if hasattr(RNS.Transport, 'interfaces') and RNS.Transport.interfaces:
                        RNS.Transport.detach_interfaces()
                except Exception:
                    pass
            
            _orig_signal = signal_module.signal
            signal_module.signal = lambda signum, handler: None
            try:
                os.makedirs(self._config_dir, exist_ok=True)
                
                if os.path.exists(identity_path):
                    self._identity = RNS.Identity.from_file(identity_path)
                else:
                    self._identity = RNS.Identity()
                    self._identity.to_file(identity_path)
                
                identity_hash_hex = self._identity.hash.hex()
                
                # Write RNS config (idempotent)
                config_path = os.path.join(self._config_dir, "config")
                with open(config_path, "w") as f:
                    f.write("[reticulum]\n")
                    f.write("enable_transport = True\n")
                    f.write("share_instance = Yes\n\n")
                    f.write("[logging]\n")
                    f.write("loglevel = 3\n")
                    if self._tcp_port > 0:
                        f.write("\n[interfaces]\n")
                        f.write("  [[Rover TCP]]\n")
                        f.write("    type = TCPServerInterface\n")
                        f.write("    enabled = Yes\n")
                        f.write("    listen_ip = 0.0.0.0\n")
                        f.write(f"    listen_port = {self._tcp_port}\n")
                
                if existing is None:
                    RNS.Reticulum(configdir=self._config_dir)
                    RNS.loglevel = RNS.LOG_EXTREME
                    RNS.logdest = RNS.LOG_STDOUT
                
                # Try to reuse existing LXMF router (RELOAD case)
                if _LXMF_STATE is not None and _LXMF_STATE.get("identity_hash") == identity_hash_hex:
                    self._router = _LXMF_STATE["router"]
                    self._delivery_dest = _LXMF_STATE["delivery_dest"]
                    self._logger.info("Reusing existing LXMF router (identity=%s...)", identity_hash_hex[:16])
                    # Re-register callback (old one points to dead RoverTransport)
                    self._router.register_delivery_callback(self._on_lxmf_message)
                    # Re-announce so peers refresh paths
                    try:
                        self._delivery_dest.announce()
                    except Exception:
                        pass
                else:
                    # First-time init OR identity changed → create new router
                    storage_path = os.path.join(self._config_dir, "lxmf_storage")
                    os.makedirs(storage_path, exist_ok=True)
                    
                    # If old _LXMF_STATE exists with different identity, tear it down first
                    if _LXMF_STATE is not None:
                        old_dest = _LXMF_STATE.get("delivery_dest")
                        old_router = _LXMF_STATE.get("router")
                        if old_dest is not None:
                            try:
                                RNS.Transport.deregister_destination(old_dest)
                            except Exception:
                                pass
                        if old_router is not None:
                            try:
                                old_router.stop()
                            except Exception:
                                pass
                        _LXMF_STATE = None
                    
                    self._router = LXMF.LXMRouter(
                        identity=self._identity, storagepath=storage_path
                    )
                    self._delivery_dest = self._router.register_delivery_identity(
                        self._identity, "Rover", None
                    )
                    self._delivery_dest.announce()
                    self._router.register_delivery_callback(self._on_lxmf_message)
                    
                    _LXMF_STATE = {
                        "router": self._router,
                        "delivery_dest": self._delivery_dest,
                        "identity_hash": identity_hash_hex,
                    }
                    self._logger.info("Created new LXMF router (identity=%s...)", identity_hash_hex[:16])
                
                return identity_hash_hex
            finally:
                signal_module.signal = _orig_signal

        # Run synchronous init in executor (with signal patch)
        identity_hash = await self._hass.async_add_executor_job(_init)
        self._identity_hash = identity_hash
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

    async def shutdown(self, full_teardown: bool = False) -> None:
        """Shutdown transport. full_teardown=True for HA stop; False for reload."""
        self._shutdown = True

        def _do_shutdown() -> None:
            if full_teardown:
                global _LXMF_STATE
                # Stop router
                if self._router:
                    try:
                        self._router.stop()
                    except Exception:
                        pass
                # Deregister delivery destination from RNS
                if self._delivery_dest is not None:
                    try:
                        RNS.Transport.deregister_destination(self._delivery_dest)
                    except Exception:
                        pass
                # Detach Reticulum interfaces
                try:
                    if hasattr(RNS.Transport, 'interfaces') and RNS.Transport.interfaces:
                        RNS.Transport.detach_interfaces()
                except Exception:
                    pass
                _LXMF_STATE = None
                self._logger.info("Transport full teardown complete")
            # else: reload — keep _LXMF_STATE alive for next setup

        await self._hass.async_add_executor_job(_do_shutdown)
        self._identity = None
        self._delivery_dest = None
        self._router = None
        self._logger.info("Transport shutdown complete (full_teardown=%s)", full_teardown)

    def set_dispatcher_cb(self, callback: Callable[[bytes, dict], None]) -> None:
        self._on_message = callback

    def get_public_key_base64(self) -> str:
        """Return the Reticulum identity's public key as base64 string.
        
        Used for embedding in QR codes per spec v0.5.0 §4.2.
        Returns empty string if identity not yet initialized.
        """
        if self._identity is None:
            return ""
        import base64
        # RNS Identity has .get_public_key() returning bytes
        pk_bytes = self._identity.get_public_key()
        return base64.b64encode(pk_bytes).decode("ascii")
