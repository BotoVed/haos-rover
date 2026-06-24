"""Root conftest — stub out homeassistant before any rover imports."""
from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock, AsyncMock


def _install_ha_stubs() -> None:
    """Insert minimal homeassistant stubs into sys.modules."""
    if "homeassistant" in sys.modules:
        return

    # homeassistant
    ha = types.ModuleType("homeassistant")
    sys.modules["homeassistant"] = ha

    # homeassistant.config_entries
    ce = types.ModuleType("homeassistant.config_entries")
    ce.ConfigEntry = MagicMock
    sys.modules["homeassistant.config_entries"] = ce

    # homeassistant.core
    core = types.ModuleType("homeassistant.core")
    core.HomeAssistant = MagicMock
    sys.modules["homeassistant.core"] = core

    # homeassistant.helpers
    helpers = types.ModuleType("homeassistant.helpers")
    sys.modules["homeassistant.helpers"] = helpers

    # homeassistant.helpers.storage
    storage = types.ModuleType("homeassistant.helpers.storage")

    class _MockStore:
        """Dict-backed mock Store — no real HA required."""

        def __init__(self, hass, version, key):
            self._data = None

        async def async_load(self):
            return self._data

        async def async_save(self, data):
            self._data = data

    storage.Store = _MockStore  # type: ignore[attr-defined]
    sys.modules["homeassistant.helpers.storage"] = storage

    # homeassistant.helpers.typing
    typing_mod = types.ModuleType("homeassistant.helpers.typing")
    typing_mod.ConfigType = dict
    sys.modules["homeassistant.helpers.typing"] = typing_mod

    # homeassistant.helpers.config_validation
    cv_mod = types.ModuleType("homeassistant.helpers.config_validation")
    cv_mod.config_entry_only_config_schema = MagicMock(return_value={})
    cv_mod.positive_int = MagicMock(return_value=None)
    sys.modules["homeassistant.helpers.config_validation"] = cv_mod


def _install_rns_lxmf_stubs() -> None:
    """Mock RNS and LXMF modules before any rover imports."""
    # RNS mock
    RNSMock = MagicMock()
    RNSMock.Identity.recall = MagicMock(return_value=None)
    RNSMock.Transport.request_path = MagicMock()
    RNSMock.Destination.OUT = 0  # enum value
    RNSMock.Destination.SINGLE = 0  # enum value
    sys.modules["RNS"] = RNSMock

    # LXMF mock
    LXMFMock = MagicMock()
    LXMFMock.LXMRouter = MagicMock()
    LXMFMock.LXMessage = MagicMock()
    LXMFMock.LXMessage.DIRECT = 0  # enum value
    sys.modules["LXMF"] = LXMFMock


def _install_voluptuous_stubs() -> None:
    """Mock voluptuous module (not installed in test env)."""
    vol_mock = MagicMock()
    vol_mock.Schema = MagicMock(return_value=None)
    vol_mock.In = MagicMock(return_value=MagicMock())
    vol_mock.All = MagicMock(return_value=MagicMock())
    vol_mock.Range = MagicMock(return_value=MagicMock())
    vol_mock.Optional = MagicMock(return_value="optional-key")
    vol_mock.Required = MagicMock(return_value="required-key")
    vol_mock.Any = MagicMock(return_value=MagicMock())
    sys.modules["voluptuous"] = vol_mock
    sys.modules["voluptuous.schema_builder"] = vol_mock
    sys.modules["voluptuous.validators"] = vol_mock


# Install all stubs before any test module collects
_install_ha_stubs()
_install_rns_lxmf_stubs()
_install_voluptuous_stubs()

import pytest


@pytest.fixture
def mock_hass():
    """Return a mock HomeAssistant."""
    from homeassistant.core import HomeAssistant
    
    hass = MagicMock(spec=HomeAssistant)
    hass.config.config_dir = "/config"
    hass.async_add_executor_job = AsyncMock(side_effect=lambda f, *args: f(*args))
    return hass


@pytest.fixture
def mock_store():
    """Patch homeassistant.helpers.storage.Store for tests."""
    from unittest.mock import patch
    from homeassistant.helpers.storage import Store
    
    with patch("custom_components.rover.registry.Store") as MockStore:
        store_instance = AsyncMock(spec=Store)
        store_instance.async_load = AsyncMock(return_value=None)
        store_instance.async_save = AsyncMock(return_value=None)
        MockStore.return_value = store_instance
        yield MockStore, store_instance
