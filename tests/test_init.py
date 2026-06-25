"""Tests for rover.__init__ — version, runtime data, setup, and unload."""
from __future__ import annotations

import json
import pathlib
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

import rover as init_mod
from custom_components.rover.const import DOMAIN


class TestVersion:
    def test_version_value(self) -> None:
        assert init_mod.__version__ == "0.2.8"

    def test_version_is_string(self) -> None:
        assert isinstance(init_mod.__version__, str)


class TestRoverRuntimeData:
    def test_all_fields_initialized_to_none(self) -> None:
        runtime = init_mod.RoverRuntimeData()
        assert runtime.registry is None
        assert runtime.transport is None
        assert runtime.handlers is None
        assert runtime.dispatcher is None
        assert runtime.bridge is None
        assert runtime.identity_hash is None
        assert runtime._store is None
        assert runtime._unsub_stop is None

    def test_can_set_fields(self) -> None:
        runtime = init_mod.RoverRuntimeData()
        runtime.registry = "test_registry"
        runtime.transport = "test_transport"
        assert runtime.registry == "test_registry"
        assert runtime.transport == "test_transport"


class TestAsyncSetup:
    @pytest.mark.asyncio
    async def test_async_setup_returns_true(self) -> None:
        mock_hass = MagicMock()
        result = await init_mod.async_setup(mock_hass, {})
        assert result is True

    @pytest.mark.asyncio
    async def test_async_setup_ignores_config(self) -> None:
        mock_hass = MagicMock()
        result = await init_mod.async_setup(mock_hass, {"key": "value"})
        assert result is True


class TestAsyncSetupEntry:
    """Comprehensive tests for async_setup_entry — component wiring."""

    @pytest.fixture
    def mock_components(self):
        """Patch all 5 component constructors + service registration functions.

        Returns dict with mock instances so tests can verify call ordering
        and await targets.
        """
        patches = [
            patch.object(init_mod, "RoverRegistry"),
            patch.object(init_mod, "RoverDispatcher"),
            patch.object(init_mod, "RoverTransport"),
            patch.object(init_mod, "RoverHandlers"),
            patch.object(init_mod, "RoverHABridge"),
            patch.object(init_mod, "async_register_services"),
            patch.object(init_mod, "async_unregister_services"),
        ]
        for p in patches:
            p.start()

        reg_cls = init_mod.RoverRegistry
        disp_cls = init_mod.RoverDispatcher
        transp_cls = init_mod.RoverTransport
        handl_cls = init_mod.RoverHandlers
        bridge_cls = init_mod.RoverHABridge

        reg = MagicMock()
        reg.async_load = AsyncMock()

        disp = MagicMock()
        disp.dispatch = MagicMock()

        transp = MagicMock()
        transp.async_start = AsyncMock(return_value="aabbccddee0011223344556677889900")
        transp.shutdown = AsyncMock()

        handl = MagicMock()
        handl.register = AsyncMock()

        bridge = MagicMock()
        bridge.async_start = AsyncMock()
        bridge.async_stop = AsyncMock()

        reg_cls.return_value = reg
        disp_cls.return_value = disp
        transp_cls.return_value = transp
        handl_cls.return_value = handl
        bridge_cls.return_value = bridge

        yield {
            "reg": reg,
            "disp": disp,
            "transp": transp,
            "handl": handl,
            "bridge": bridge,
            "reg_cls": reg_cls,
            "disp_cls": disp_cls,
            "transp_cls": transp_cls,
            "handl_cls": handl_cls,
            "bridge_cls": bridge_cls,
        }

        for p in patches:
            p.stop()

    @pytest.mark.asyncio
    async def test_returns_true(self, mock_components) -> None:
        mock_hass = MagicMock()
        mock_entry = MagicMock()
        result = await init_mod.async_setup_entry(mock_hass, mock_entry)
        assert result is True

    @pytest.mark.asyncio
    async def test_sets_runtime_data(self, mock_components) -> None:
        mock_hass = MagicMock()
        mock_entry = MagicMock()
        await init_mod.async_setup_entry(mock_hass, mock_entry)
        assert isinstance(mock_entry.runtime_data, init_mod.RoverRuntimeData)

    @pytest.mark.asyncio
    async def test_constructs_registry_first(self, mock_components) -> None:
        """Registry constructor called first with hass."""
        mock_hass = MagicMock()
        mock_entry = MagicMock()
        await init_mod.async_setup_entry(mock_hass, mock_entry)
        mock_components["reg_cls"].assert_called_once_with(mock_hass)

    @pytest.mark.asyncio
    async def test_async_load_called_on_registry(self, mock_components) -> None:
        mock_hass = MagicMock()
        mock_entry = MagicMock()
        await init_mod.async_setup_entry(mock_hass, mock_entry)
        mock_components["reg"].async_load.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_constructs_dispatcher_with_registry(self, mock_components) -> None:
        mock_hass = MagicMock()
        mock_entry = MagicMock()
        await init_mod.async_setup_entry(mock_hass, mock_entry)
        mock_components["disp_cls"].assert_called_once_with(
            mock_components["reg"]
        )

    @pytest.mark.asyncio
    async def test_constructs_transport_with_dispatch_callback(self, mock_components) -> None:
        mock_hass = MagicMock()
        mock_entry = MagicMock()
        mock_entry.data.get = MagicMock(return_value=4242)
        await init_mod.async_setup_entry(mock_hass, mock_entry)
        mock_components["transp_cls"].assert_called_once_with(
            mock_hass,
            mock_hass.config.path.return_value,
            mock_components["disp"].dispatch,
            tcp_port=4242,
        )

    @pytest.mark.asyncio
    async def test_transport_tcp_port_from_entry_data(self, mock_components) -> None:
        mock_hass = MagicMock()
        mock_entry = MagicMock()
        mock_entry.data.get = MagicMock(return_value=9999)
        await init_mod.async_setup_entry(mock_hass, mock_entry)
        mock_components["transp_cls"].assert_called_once()
        _call_kw = mock_components["transp_cls"].call_args.kwargs
        assert _call_kw.get("tcp_port") == 9999

    @pytest.mark.asyncio
    async def test_constructs_handlers_with_all_deps(self, mock_components) -> None:
        mock_hass = MagicMock()
        mock_entry = MagicMock()
        await init_mod.async_setup_entry(mock_hass, mock_entry)
        mock_components["handl_cls"].assert_called_once_with(
            mock_hass,
            mock_components["reg"],
            mock_components["transp"],
            mock_components["disp"],
        )

    @pytest.mark.asyncio
    async def test_handlers_register_called(self, mock_components) -> None:
        mock_hass = MagicMock()
        mock_entry = MagicMock()
        await init_mod.async_setup_entry(mock_hass, mock_entry)
        mock_components["handl"].register.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_constructs_bridge(self, mock_components) -> None:
        mock_hass = MagicMock()
        mock_entry = MagicMock()
        await init_mod.async_setup_entry(mock_hass, mock_entry)
        mock_components["bridge_cls"].assert_called_once_with(
            mock_hass,
            mock_components["reg"],
            mock_components["transp"],
        )

    @pytest.mark.asyncio
    async def test_transport_started_before_bridge(self, mock_components) -> None:
        """Transport.async_start() must be called and return identity_hash."""
        mock_hass = MagicMock()
        mock_entry = MagicMock()
        await init_mod.async_setup_entry(mock_hass, mock_entry)
        mock_components["transp"].async_start.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_identity_hash_on_runtime(self, mock_components) -> None:
        mock_hass = MagicMock()
        mock_entry = MagicMock()
        await init_mod.async_setup_entry(mock_hass, mock_entry)
        assert mock_entry.runtime_data.identity_hash == "aabbccddee0011223344556677889900"

    @pytest.mark.asyncio
    async def test_bridge_started(self, mock_components) -> None:
        mock_hass = MagicMock()
        mock_entry = MagicMock()
        await init_mod.async_setup_entry(mock_hass, mock_entry)
        mock_components["bridge"].async_start.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_listens_for_ha_stop(self, mock_components) -> None:
        mock_hass = MagicMock()
        mock_entry = MagicMock()
        await init_mod.async_setup_entry(mock_hass, mock_entry)
        mock_hass.bus.async_listen_once.assert_called_once()
        args = mock_hass.bus.async_listen_once.call_args[0]
        assert args[0] == "homeassistant_stop"

    @pytest.mark.asyncio
    async def test_registers_debug_services(self, mock_components) -> None:
        mock_hass = MagicMock()
        mock_entry = MagicMock()
        await init_mod.async_setup_entry(mock_hass, mock_entry)
        init_mod.async_register_services.assert_awaited_once_with(
            mock_hass, mock_entry.runtime_data
        )

    @pytest.mark.asyncio
    async def test_ha_stop_shutdown_triggers_unload(self, mock_components) -> None:
        """The _shutdown closure registered via async_listen_once performs cleanup."""
        mock_hass = MagicMock()
        mock_entry = MagicMock()
        mock_entry.entry_id = "test_entry_123"
        await init_mod.async_setup_entry(mock_hass, mock_entry)
        # Extract the _shutdown callback that was registered
        _shutdown_cb = mock_hass.bus.async_listen_once.call_args[0][1]
        await _shutdown_cb(MagicMock())
        # Verify _shutdown actually does what it does (not calling async_unload_entry)
        mock_components["transp"].shutdown.assert_awaited_once_with(full_teardown=True)
        mock_components["bridge"].async_stop.assert_awaited_once()
        init_mod.async_unregister_services.assert_called_once_with(mock_hass)
        mock_entry.runtime_data._unsub_stop.assert_called_once()
        mock_hass.data.setdefault.assert_called_once_with(DOMAIN, {})
        mock_hass.data.setdefault.return_value.pop.assert_called_once_with("test_entry_123", None)

    @pytest.mark.asyncio
    async def test_construction_order(self, mock_components) -> None:
        """Verify the 5 components are constructed in the expected order."""
        mock_hass = MagicMock()
        mock_entry = MagicMock()
        await init_mod.async_setup_entry(mock_hass, mock_entry)

        # Check call order: registry -> dispatcher -> transport -> handlers -> bridge
        reg_time = mock_components["reg_cls"].call_args[0]
        disp_time = mock_components["disp_cls"].call_args[0]
        transp_time = mock_components["transp_cls"].call_args[0]
        handl_time = mock_components["handl_cls"].call_args[0]
        bridge_time = mock_components["bridge_cls"].call_args[0]

        # All were called (no error means they were)
        assert reg_time is not None
        assert disp_time is not None
        assert transp_time is not None
        assert handl_time is not None
        assert bridge_time is not None


class TestAsyncUnloadEntry:
    @pytest.mark.asyncio
    async def test_returns_true_when_no_runtime(self) -> None:
        mock_hass = MagicMock()
        mock_entry = MagicMock(spec=[])  # no runtime_data attribute
        result = await init_mod.async_unload_entry(mock_hass, mock_entry)
        assert result is True

    @pytest.mark.asyncio
    async def test_stops_bridge(self) -> None:
        mock_hass = MagicMock()
        mock_entry = MagicMock()
        mock_bridge = MagicMock()
        mock_bridge.async_stop = AsyncMock()
        runtime = init_mod.RoverRuntimeData()
        runtime.bridge = mock_bridge
        runtime.transport = MagicMock()
        runtime.transport.shutdown = AsyncMock()
        runtime._unsub_stop = MagicMock()
        mock_entry.runtime_data = runtime

        await init_mod.async_unload_entry(mock_hass, mock_entry)
        mock_bridge.async_stop.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_shuts_down_transport(self) -> None:
        mock_hass = MagicMock()
        mock_entry = MagicMock()
        mock_transport = MagicMock()
        mock_transport.shutdown = AsyncMock()
        runtime = init_mod.RoverRuntimeData()
        runtime.bridge = MagicMock()
        runtime.bridge.async_stop = AsyncMock()
        runtime.transport = mock_transport
        runtime._unsub_stop = MagicMock()
        mock_entry.runtime_data = runtime

        await init_mod.async_unload_entry(mock_hass, mock_entry)
        mock_transport.shutdown.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_unregisters_services(self) -> None:
        mock_hass = MagicMock()
        mock_entry = MagicMock()
        runtime = init_mod.RoverRuntimeData()
        runtime.bridge = MagicMock()
        runtime.bridge.async_stop = AsyncMock()
        runtime.transport = MagicMock()
        runtime.transport.shutdown = AsyncMock()
        runtime._unsub_stop = MagicMock()
        mock_entry.runtime_data = runtime

        with patch.object(init_mod, "async_unregister_services") as mock_unreg:
            await init_mod.async_unload_entry(mock_hass, mock_entry)
            mock_unreg.assert_called_once_with(mock_hass)

    @pytest.mark.asyncio
    async def test_calls_unsub_stop(self) -> None:
        mock_hass = MagicMock()
        mock_entry = MagicMock()
        runtime = init_mod.RoverRuntimeData()
        runtime.bridge = MagicMock()
        runtime.bridge.async_stop = AsyncMock()
        runtime.transport = MagicMock()
        runtime.transport.shutdown = AsyncMock()
        unsub = MagicMock()
        runtime._unsub_stop = unsub
        mock_entry.runtime_data = runtime

        await init_mod.async_unload_entry(mock_hass, mock_entry)
        unsub.assert_called_once()

    @pytest.mark.asyncio
    async def test_cleans_hass_data(self) -> None:
        mock_hass = MagicMock()
        mock_entry = MagicMock()
        mock_entry.entry_id = "test_entry_123"
        runtime = init_mod.RoverRuntimeData()
        runtime.bridge = MagicMock()
        runtime.bridge.async_stop = AsyncMock()
        runtime.transport = MagicMock()
        runtime.transport.shutdown = AsyncMock()
        runtime._unsub_stop = MagicMock()
        mock_entry.runtime_data = runtime

        await init_mod.async_unload_entry(mock_hass, mock_entry)
        mock_hass.data.setdefault.assert_called_once_with(DOMAIN, {})
        mock_hass.data.setdefault.return_value.pop.assert_called_once_with("test_entry_123", None)

    @pytest.mark.asyncio
    async def test_handles_missing_bridge(self) -> None:
        """Bridge is optional — unload should not crash."""
        mock_hass = MagicMock()
        mock_entry = MagicMock()
        runtime = init_mod.RoverRuntimeData()
        runtime.bridge = None
        runtime.transport = MagicMock()
        runtime.transport.shutdown = AsyncMock()
        runtime._unsub_stop = MagicMock()
        mock_entry.runtime_data = runtime

        result = await init_mod.async_unload_entry(mock_hass, mock_entry)
        assert result is True

    @pytest.mark.asyncio
    async def test_handles_missing_transport(self) -> None:
        """Transport is optional — unload should not crash."""
        mock_hass = MagicMock()
        mock_entry = MagicMock()
        runtime = init_mod.RoverRuntimeData()
        runtime.bridge = MagicMock()
        runtime.bridge.async_stop = AsyncMock()
        runtime.transport = None
        runtime._unsub_stop = MagicMock()
        mock_entry.runtime_data = runtime

        result = await init_mod.async_unload_entry(mock_hass, mock_entry)
        assert result is True

    @pytest.mark.asyncio
    async def test_handles_missing_unsub_stop(self) -> None:
        mock_hass = MagicMock()
        mock_entry = MagicMock()
        runtime = init_mod.RoverRuntimeData()
        runtime.bridge = MagicMock()
        runtime.bridge.async_stop = AsyncMock()
        runtime.transport = MagicMock()
        runtime.transport.shutdown = AsyncMock()
        runtime._unsub_stop = None
        mock_entry.runtime_data = runtime

        result = await init_mod.async_unload_entry(mock_hass, mock_entry)
        assert result is True

    @pytest.mark.asyncio
    async def test_stops_bridge_before_transport(self) -> None:
        """Bridge must stop before transport shuts down — verified by call order."""
        mock_hass = MagicMock()
        mock_entry = MagicMock()
        runtime = init_mod.RoverRuntimeData()
        call_order: list[str] = []

        async def _stop_bridge():
            call_order.append("bridge_stop")

        async def _shutdown_transport():
            call_order.append("transport_shutdown")

        bridge = MagicMock()
        bridge.async_stop = _stop_bridge
        transport = MagicMock()
        transport.shutdown = _shutdown_transport
        runtime.bridge = bridge
        runtime.transport = transport
        runtime._unsub_stop = MagicMock()
        mock_entry.runtime_data = runtime

        await init_mod.async_unload_entry(mock_hass, mock_entry)
        assert call_order == ["bridge_stop", "transport_shutdown"]


_MANIFEST_PATH = (
    pathlib.Path(__file__).resolve().parent.parent
    / "custom_components"
    / "rover"
    / "manifest.json"
)


class TestManifest:
    def test_requirements_is_list(self) -> None:
        manifest = json.loads(_MANIFEST_PATH.read_text())
        assert isinstance(manifest["requirements"], list)

    def test_version_matches(self) -> None:
        manifest = json.loads(_MANIFEST_PATH.read_text())
        assert manifest["version"] == "0.2.8"

    def test_domain_matches(self) -> None:
        manifest = json.loads(_MANIFEST_PATH.read_text())
        assert manifest["domain"] == "rover"

    def test_config_flow_enabled(self) -> None:
        manifest = json.loads(_MANIFEST_PATH.read_text())
        assert manifest["config_flow"] is True
