"""Tests for rover.__init__ — RoverRuntimeData, version, and setup stubs."""
from __future__ import annotations

import json
import pathlib
from unittest.mock import MagicMock

import pytest

# conftest.py already installs homeassistant stubs in sys.modules before collection.
# Import rover package directly — it IS the __init__ module.
import rover as init_mod


class TestVersion:
    def test_version_value(self) -> None:
        assert init_mod.__version__ == "0.0.1"

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
    @pytest.mark.asyncio
    async def test_async_setup_entry_returns_true(self) -> None:
        mock_hass = MagicMock()
        mock_entry = MagicMock()
        result = await init_mod.async_setup_entry(mock_hass, mock_entry)
        assert result is True

    @pytest.mark.asyncio
    async def test_async_setup_entry_sets_runtime_data(self) -> None:
        mock_hass = MagicMock()
        mock_entry = MagicMock()
        await init_mod.async_setup_entry(mock_hass, mock_entry)
        assert isinstance(mock_entry.runtime_data, init_mod.RoverRuntimeData)


class TestAsyncUnloadEntry:
    @pytest.mark.asyncio
    async def test_unload_returns_true_when_no_runtime(self) -> None:
        mock_hass = MagicMock()
        mock_entry = MagicMock(spec=[])  # no runtime_data attribute
        result = await init_mod.async_unload_entry(mock_hass, mock_entry)
        assert result is True

    @pytest.mark.asyncio
    async def test_unload_returns_true_with_runtime(self) -> None:
        mock_hass = MagicMock()
        mock_entry = MagicMock()
        mock_entry.runtime_data = init_mod.RoverRuntimeData()
        result = await init_mod.async_unload_entry(mock_hass, mock_entry)
        assert result is True


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
        assert manifest["version"] == "0.0.1"

    def test_domain_matches(self) -> None:
        manifest = json.loads(_MANIFEST_PATH.read_text())
        assert manifest["domain"] == "rover"

    def test_config_flow_enabled(self) -> None:
        manifest = json.loads(_MANIFEST_PATH.read_text())
        assert manifest["config_flow"] is True
