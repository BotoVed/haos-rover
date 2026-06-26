"""Tests for rover.options_flow — multi-step options flow."""
from __future__ import annotations

import json
import sys
import types
from unittest.mock import ANY, AsyncMock, MagicMock, call, patch

import pytest

# ---------------------------------------------------------------------------
# Stub missing HA sub-modules before importing the module under test
# ---------------------------------------------------------------------------

if "homeassistant.data_entry_flow" not in sys.modules:
    _de_mod = types.ModuleType("homeassistant.data_entry_flow")
    _de_mod.FlowResult = dict
    sys.modules["homeassistant.data_entry_flow"] = _de_mod

if "homeassistant.helpers.service" not in sys.modules:
    _svc_mod = types.ModuleType("homeassistant.helpers.service")

    class _MockServiceTarget:
        """Mock for homeassistant.helpers.service.ServiceTarget."""
        def __init__(self, *, entity_ids=None, device_ids=None, area_ids=None):
            self.entity_ids = entity_ids or []
            self.device_ids = device_ids or []
            self.area_ids = area_ids or []

    _svc_mod.ServiceTarget = _MockServiceTarget
    sys.modules["homeassistant.helpers.service"] = _svc_mod

if "homeassistant.helpers.selector" not in sys.modules:
    _sel_mod = types.ModuleType("homeassistant.helpers.selector")

    class _MockSelector:
        """Simple callable mock for HA selector classes.

        Using a plain class avoids MagicMock's spec-checking which crashes
        when one mock is passed as positional arg to another (InvalidSpecError).
        """

        def __init__(self, *args, **kwargs):
            self._args = args
            self._kwargs = kwargs

    class _MockSelectSelectorMode:
        LIST = "list"
        DROPDOWN = "dropdown"

    _sel_mod.EntitySelector = _MockSelector
    _sel_mod.EntitySelectorConfig = _MockSelector
    _sel_mod.NumberSelector = _MockSelector
    _sel_mod.NumberSelectorConfig = _MockSelector
    _sel_mod.SelectSelector = _MockSelector
    _sel_mod.SelectSelectorConfig = _MockSelector
    _sel_mod.SelectSelectorMode = _MockSelectSelectorMode
    _sel_mod.TextSelector = _MockSelector
    sys.modules["homeassistant.helpers.selector"] = _sel_mod


class MockOptionsFlowWithConfigEntry:
    """Mock for homeassistant.config_entries.OptionsFlowWithConfigEntry.

    Provides the same interface options_flow.py expects from the HA parent
    class: config_entry, options, async_show_menu, async_show_form,
    async_create_entry, async_abort.
    """

    def __init__(self, config_entry):
        self.config_entry = config_entry

    @property
    def options(self) -> dict:
        return self.config_entry.options

    def async_show_menu(self, *, step_id, menu_options):
        return {"type": "menu", "step_id": step_id, "menu_options": menu_options}

    def async_show_form(
        self, *, step_id, data_schema, description_placeholders=None
    ):
        result = {"type": "form", "step_id": step_id, "data_schema": data_schema}
        if description_placeholders:
            result["description_placeholders"] = description_placeholders
        return result

    def async_create_entry(self, *, title, data):
        return {"type": "create_entry", "title": title, "data": data}

    def async_abort(self, *, reason):
        return {"type": "abort", "reason": reason}


# Inject the mock parent class into the stubbed config_entries module
_ce_mod = sys.modules["homeassistant.config_entries"]
_ce_mod.OptionsFlowWithConfigEntry = MockOptionsFlowWithConfigEntry

# Now safe to import the module under test
from custom_components.rover.options_flow import RoverOptionsFlow
from custom_components.rover.const import (
    DEFAULT_TCP_PORT,
    PONG_BROADCAST_INTERVAL_S,
    QR_FORMAT_VERSION,
    TYPE_DEFS,
)


# =========================================================================
# Fixtures
# =========================================================================


@pytest.fixture
def sample_devices():
    """Return a realistic list of devices for testing."""
    return [
        {"short_id": 1, "entity_id": "switch.test", "name": "Test Switch", "type": "SW", "area_id": None, "enabled": True},
        {"short_id": 2, "entity_id": "light.kitchen", "name": "Kitchen Light", "type": "LT", "area_id": 1, "enabled": True},
    ]


@pytest.fixture
def sample_users():
    """Return a realistic list of users for testing."""
    return [
        {"hash": "aa0011", "name": "Alice", "role": "owner"},
        {"hash": "bb0022", "name": "Bob", "role": "regular"},
    ]


@pytest.fixture
def sample_pending():
    """Return a realistic list of pending remotes for testing."""
    return [
        {"hash": "cc0033", "name": "Charlie", "requested_at": 1000},
        {"hash": "dd0044", "name": "Diana", "requested_at": 2000},
    ]


@pytest.fixture
def sample_hashes():
    """Return sample section hashes."""
    return {"m": "abcd", "u": "ef01", "a": "2345", "d": "6789"}


@pytest.fixture
def mock_registry(sample_devices, sample_users, sample_pending, sample_hashes):
    """Create a mock registry with configurable return values."""
    reg = MagicMock()
    reg.all_devices = MagicMock(return_value=sample_devices)
    reg.all_users = MagicMock(return_value=sample_users)
    reg.all_pending = MagicMock(return_value=sample_pending)
    reg.get_hashes = MagicMock(return_value=sample_hashes)
    reg.add_device = AsyncMock(return_value=3)
    reg.remove_device = AsyncMock(return_value=True)
    reg.revoke_user = AsyncMock(return_value=True)
    reg.approve_pending = AsyncMock(return_value=True)
    reg.deny_pending = AsyncMock(return_value=True)
    reg.get_device = MagicMock(
        return_value={
            "short_id": 1,
            "entity_id": "switch.test",
            "name": "Test Device",
            "type": "SW",
        }
    )
    return reg


@pytest.fixture
def mock_handlers():
    """Create a mock handlers object with async _handle_cmd."""
    h = MagicMock()
    h._handle_cmd = AsyncMock()
    return h


@pytest.fixture
def mock_runtime(mock_registry, mock_handlers):
    """Create a mock runtime_data with registry and handlers."""
    runtime = MagicMock()
    runtime.registry = mock_registry
    runtime.identity_hash = "aabbccdd00112233"
    runtime.handlers = mock_handlers
    runtime.hass = MagicMock()
    runtime.hass.services = MagicMock()
    runtime.hass.services.async_call = AsyncMock(return_value=None)
    runtime.hass.states = MagicMock()
    runtime.hass.states.get = MagicMock()
    return runtime


@pytest.fixture
def mock_config_entry(mock_runtime):
    """Create a mock config entry with empty options and runtime_data."""
    entry = MagicMock()
    entry.options = {}
    entry.runtime_data = mock_runtime
    entry.data = {}
    return entry


@pytest.fixture
def flow(mock_config_entry):
    """Create a RoverOptionsFlow instance with a populated config entry."""
    flow_instance = RoverOptionsFlow(mock_config_entry)
    flow_instance.hass = mock_config_entry.runtime_data.hass
    return flow_instance


# =========================================================================
# Tests for async_step_init
# =========================================================================


class TestAsyncStepInit:
    """Main menu."""

    async def test_shows_menu_with_all_options(self, flow) -> None:
        result = await flow.async_step_init()
        assert result["type"] == "menu"
        assert result["step_id"] == "init"
        assert result["menu_options"] == {
            "general": "General Settings",
            "add_devices": "Manage Device",
            "test_device": "Test Device",
            "users": "Manage Users",
            "config": "Configuration Export",
        }

    async def test_aborts_when_runtime_is_none(self, flow) -> None:
        flow.config_entry.runtime_data = None
        result = await flow.async_step_init()
        assert result["type"] == "abort"
        assert result["reason"] == "not_loaded"

    async def test_aborts_when_registry_is_none(self, flow) -> None:
        flow.config_entry.runtime_data.registry = None
        result = await flow.async_step_init()
        assert result["type"] == "abort"
        assert result["reason"] == "not_loaded"

    async def test_aborts_when_runtime_has_no_registry_attr(self, flow) -> None:
        """Runtime_data might not have 'registry' attribute at all.

        Note: The source code does NOT guard against missing 'registry'
        attribute — it will raise AttributeError. This test documents
        the current behavior. If a fix is needed, add hasattr guard.
        """
        flow.config_entry.runtime_data = MagicMock(spec=["not_registry"])
        with pytest.raises(AttributeError):
            await flow.async_step_init()


# =========================================================================
# Tests for async_step_general
# =========================================================================


class TestAsyncStepGeneral:
    """General settings: server_name, ping_interval."""

    async def test_shows_form_with_defaults_when_no_options(self, flow) -> None:
        result = await flow.async_step_general()
        assert result["type"] == "form"
        assert result["step_id"] == "general"

    async def test_shows_form_with_current_options(self, flow) -> None:
        flow.config_entry.options = {
            "server_name": "My Rover",
            "ping_interval": 15,
        }
        result = await flow.async_step_general()
        assert result["type"] == "form"
        assert result["step_id"] == "general"

    async def test_creates_entry_with_user_input(self, flow) -> None:
        user_input = {"server_name": "Custom Hub", "ping_interval": 10}
        result = await flow.async_step_general(user_input)
        assert result["type"] == "create_entry"
        assert result["title"] == ""
        assert result["data"] == user_input

    async def test_accepts_empty_server_name(self, flow) -> None:
        """Empty string is a valid server name value."""
        user_input = {"server_name": "", "ping_interval": 5}
        result = await flow.async_step_general(user_input)
        assert result["type"] == "create_entry"
        assert result["data"]["server_name"] == ""

    async def test_accepts_min_ping_interval(self, flow) -> None:
        user_input = {"server_name": "Test", "ping_interval": 1}
        result = await flow.async_step_general(user_input)
        assert result["type"] == "create_entry"

    async def test_accepts_max_ping_interval(self, flow) -> None:
        user_input = {"server_name": "Test", "ping_interval": 60}
        result = await flow.async_step_general(user_input)
        assert result["type"] == "create_entry"

    async def test_does_not_abort_when_runtime_is_none(self, flow) -> None:
        """general step does NOT check runtime/registry — should not abort."""
        flow.config_entry.runtime_data = None
        # Should still show the form (no crash, no abort)
        result = await flow.async_step_general()
        assert result["type"] == "form"
        assert result["step_id"] == "general"


# =========================================================================
# Tests for async_step_network
# =========================================================================


# =========================================================================
# Tests for async_step_devices
# =========================================================================


class TestAsyncStepDevices:
    """Add devices via entity picker."""

    async def test_shows_form_with_type_options(self, flow) -> None:
        """The form should include type options derived from TYPE_DEFS."""
        result = await flow.async_step_device_picker()
        assert result["type"] == "form"
        assert result["step_id"] == "device_picker"

    async def test_adds_single_device(self, flow, mock_registry) -> None:
        # Mock state with friendly_name
        mock_state = MagicMock()
        mock_state.attributes = {"friendly_name": "Kitchen Light"}
        flow.config_entry.runtime_data.hass.states.get.return_value = mock_state
        
        user_input = {"entities": ["light.bedroom"]}
        result = await flow.async_step_device_picker(user_input)
        
        # DOMAIN_TO_TYPE["light"] = "LT"
        mock_registry.add_device.assert_awaited_once_with(
            "light.bedroom", "Kitchen Light", "LT", area_id=None
        )
        assert result["type"] == "menu"  # returns to init via async_step_init()

    async def test_adds_multiple_devices(self, flow, mock_registry) -> None:
        # Mock states with friendly_name - order doesn't matter due to set iteration
        mock_state_bedroom = MagicMock()
        mock_state_bedroom.attributes = {"friendly_name": "Kitchen Light"}
        mock_state_garage = MagicMock()
        mock_state_garage.attributes = {"friendly_name": "Fan"}
        
        # Create a mock that returns the correct state for each entity_id
        def get_state(entity_id):
            if entity_id == "light.bedroom":
                return mock_state_bedroom
            elif entity_id == "switch.garage":
                return mock_state_garage
            return MagicMock()
        
        flow.config_entry.runtime_data.hass.states.get.side_effect = get_state
        
        user_input = {
            "entities": ["light.bedroom", "switch.garage"],
        }
        result = await flow.async_step_device_picker(user_input)
        assert mock_registry.add_device.call_count == 2
        mock_registry.add_device.assert_has_calls(
            [
                call("light.bedroom", "Kitchen Light", "LT", area_id=None),
                call("switch.garage", "Fan", "SW", area_id=None),
            ],
            any_order=True,
        )
        assert result["type"] == "menu"

    async def test_uses_entity_id_suffix_when_name_not_provided(
        self, flow, mock_registry
    ) -> None:
        # Mock state without friendly_name
        mock_state = MagicMock()
        mock_state.attributes = {}
        flow.config_entry.runtime_data.hass.states.get.return_value = mock_state
        
        user_input = {
            "entities": ["switch.my_switch"],
        }
        await flow.async_step_device_picker(user_input)
        mock_registry.add_device.assert_awaited_once_with(
            "switch.my_switch", "my_switch", "SW", area_id=None
        )

    async def test_handles_entity_id_without_dot(self, flow, mock_registry) -> None:
        """If entity_id has no dot, domain extraction fails and device is skipped."""
        # Mock state with friendly_name
        mock_state = MagicMock()
        mock_state.attributes = {"friendly_name": "Plain"}
        flow.config_entry.runtime_data.hass.states.get.return_value = mock_state
        
        user_input = {
            "entities": ["plain_entity"],
        }
        await flow.async_step_device_picker(user_input)
        # Domain extraction fails (no dot), so device is skipped
        mock_registry.add_device.assert_not_called()

    async def test_handles_value_error_on_add_device(
        self, flow, mock_registry, caplog
    ) -> None:
        """When add_device raises ValueError, it logs a warning and continues."""
        # Mock state with friendly_name
        mock_state = MagicMock()
        mock_state.attributes = {"friendly_name": "Test"}
        flow.config_entry.runtime_data.hass.states.get.return_value = mock_state
        
        mock_registry.add_device = AsyncMock(side_effect=ValueError("Duplicate"))
        user_input = {
            "entities": ["light.bedroom", "switch.garage"],
        }
        # Should not raise
        result = await flow.async_step_device_picker(user_input)
        assert result["type"] == "menu"

    async def test_aborts_when_runtime_is_none(self, flow) -> None:
        flow.config_entry.runtime_data = None
        result = await flow.async_step_device_picker()
        assert result["type"] == "abort"
        assert result["reason"] == "not_loaded"

    async def test_aborts_when_registry_is_none(self, flow) -> None:
        flow.config_entry.runtime_data.registry = None
        result = await flow.async_step_device_picker()
        assert result["type"] == "abort"
        assert result["reason"] == "not_loaded"


# =========================================================================
# Tests for async_step_remove_device
# =========================================================================


class TestAsyncStepRemoveDevice:
    """Remove a device."""

    async def test_shows_form_with_device_options(
        self, flow, mock_registry
    ) -> None:
        result = await flow.async_step_remove_device()
        assert result["type"] == "form"
        assert result["step_id"] == "remove_device"
        mock_registry.all_devices.assert_called_once()

    async def test_aborts_when_no_devices(self, flow, mock_registry) -> None:
        mock_registry.all_devices = MagicMock(return_value=[])
        result = await flow.async_step_remove_device()
        assert result["type"] == "abort"
        assert result["reason"] == "no_devices"

    async def test_removes_device_and_returns_to_menu(
        self, flow, mock_registry
    ) -> None:
        user_input = {"device_id": "1"}
        result = await flow.async_step_remove_device(user_input)
        mock_registry.remove_device.assert_awaited_once_with(1)
        assert result["type"] == "menu"

    async def test_aborts_when_runtime_is_none(self, flow) -> None:
        flow.config_entry.runtime_data = None
        result = await flow.async_step_remove_device()
        assert result["type"] == "abort"
        assert result["reason"] == "not_loaded"

    async def test_aborts_when_registry_is_none(self, flow) -> None:
        flow.config_entry.runtime_data.registry = None
        result = await flow.async_step_remove_device()
        assert result["type"] == "abort"
        assert result["reason"] == "not_loaded"


# =========================================================================
# Tests for async_step_test_device
# =========================================================================


class TestAsyncStepTestDevice:
    """Select device to test."""

    async def test_shows_form_with_device_options(
        self, flow, mock_registry
    ) -> None:
        result = await flow.async_step_test_device()
        assert result["type"] == "form"
        assert result["step_id"] == "test_device"
        mock_registry.all_devices.assert_called_once()

    async def test_aborts_when_no_devices(self, flow, mock_registry) -> None:
        mock_registry.all_devices = MagicMock(return_value=[])
        result = await flow.async_step_test_device()
        assert result["type"] == "abort"
        assert result["reason"] == "no_devices"

    async def test_chains_to_test_action(
        self, flow, mock_registry
    ) -> None:
        """Selecting a device sets _short_id and calls test_action."""
        with patch.object(flow, "async_step_test_action") as mock_test_action:
            mock_test_action.return_value = {"type": "chain"}
            user_input = {"device_id": "2"}
            result = await flow.async_step_test_device(user_input)
            assert flow._short_id == 2
            mock_test_action.assert_awaited_once()
            assert result == {"type": "chain"}

    async def test_aborts_when_runtime_is_none(self, flow) -> None:
        flow.config_entry.runtime_data = None
        result = await flow.async_step_test_device()
        assert result["type"] == "abort"
        assert result["reason"] == "not_loaded"

    async def test_aborts_when_registry_is_none(self, flow) -> None:
        flow.config_entry.runtime_data.registry = None
        result = await flow.async_step_test_device()
        assert result["type"] == "abort"
        assert result["reason"] == "not_loaded"


# =========================================================================
# Tests for async_step_test_action
# =========================================================================


class TestAsyncStepTestAction:
    """Send test CMD to selected device."""

    async def test_shows_form_with_service_options(
        self, flow
    ) -> None:
        result = await flow.async_step_test_action()
        assert result["type"] == "form"
        assert result["step_id"] == "test_action"

    async def test_sends_cmd_and_returns_to_menu(
        self, flow, mock_registry, mock_runtime
    ) -> None:
        flow._short_id = 1
        user_input = {"action": "turn_on"}
        result = await flow.async_step_test_action(user_input)
        # Should call async_call via ServiceTarget
        mock_runtime.hass.services.async_call.assert_awaited_once_with(
            "switch", "turn_on", {},
            target=ANY,
            blocking=True,
        )
        assert flow._short_id is None  # reset after action
        assert result["type"] == "menu"

    async def test_sends_cmd_turn_off(
        self, flow, mock_runtime
    ) -> None:
        flow._short_id = 1
        user_input = {"action": "turn_off"}
        await flow.async_step_test_action(user_input)
        mock_runtime.hass.services.async_call.assert_awaited_once_with(
            "switch", "turn_off", {},
            target=ANY,
            blocking=True,
        )

    async def test_skips_cmd_when_short_id_is_none(
        self, flow, mock_runtime
    ) -> None:
        """_short_id is None — device = None, service call skipped."""
        user_input = {"action": "turn_on"}
        result = await flow.async_step_test_action(user_input)
        mock_runtime.hass.services.async_call.assert_not_called()
        assert result["type"] == "menu"
        assert flow._short_id is None

    async def test_skips_cmd_when_runtime_is_none(
        self, flow, mock_runtime
    ) -> None:
        """When runtime is None, CMD is skipped and init returns abort."""
        flow.config_entry.runtime_data = None
        flow._short_id = 1
        user_input = {"action": "turn_on"}
        result = await flow.async_step_test_action(user_input)
        mock_runtime.hass.services.async_call.assert_not_called()
        assert flow._short_id is None
        # Returns to init which aborts because runtime is None
        assert result["type"] == "abort"
        assert result["reason"] == "not_loaded"

    async def test_executes_call_without_handlers(
        self, flow, mock_runtime
    ) -> None:
        """runtime exists but handlers is None — new code calls hass directly."""
        flow._short_id = 1
        flow.config_entry.runtime_data.handlers = None
        user_input = {"action": "turn_on"}
        result = await flow.async_step_test_action(user_input)
        # New code uses hass.services.async_call directly, not handlers
        mock_runtime.hass.services.async_call.assert_awaited_once()
        assert result["type"] == "menu"

    async def test_skips_cmd_when_device_not_found(
        self, flow, mock_registry, mock_runtime
    ) -> None:
        """get_device returns None — service call is skipped."""
        mock_registry.get_device = MagicMock(return_value=None)
        flow._short_id = 999
        user_input = {"action": "turn_on"}
        result = await flow.async_step_test_action(user_input)
        mock_runtime.hass.services.async_call.assert_not_called()
        assert flow._short_id is None
        assert result["type"] == "menu"


# =========================================================================
# Tests for async_step_users
# =========================================================================


class TestAsyncStepUsers:
    """List and revoke users."""

    async def test_shows_form_with_user_options(
        self, flow, mock_registry
    ) -> None:
        result = await flow.async_step_users()
        assert result["type"] == "form"
        assert result["step_id"] == "users"
        mock_registry.all_users.assert_called_once()

    async def test_aborts_when_no_users(self, flow, mock_registry) -> None:
        mock_registry.all_users = MagicMock(return_value=[])
        result = await flow.async_step_users()
        assert result["type"] == "abort"
        assert result["reason"] == "no_users"

    async def test_revokes_user_and_returns_to_menu(
        self, flow, mock_registry
    ) -> None:
        user_input = {"user_hash": "aa0011 — Alice (owner)"}
        result = await flow.async_step_users(user_input)
        mock_registry.revoke_user.assert_awaited_once_with("aa0011")
        assert result["type"] == "menu"

    async def test_empty_hash_does_not_revoke(
        self, flow, mock_registry
    ) -> None:
        user_input = {"user_hash": ""}
        result = await flow.async_step_users(user_input)
        mock_registry.revoke_user.assert_not_called()
        assert result["type"] == "menu"

    async def test_aborts_when_runtime_is_none(self, flow) -> None:
        flow.config_entry.runtime_data = None
        result = await flow.async_step_users()
        assert result["type"] == "abort"
        assert result["reason"] == "not_loaded"

    async def test_aborts_when_registry_is_none(self, flow) -> None:
        flow.config_entry.runtime_data.registry = None
        result = await flow.async_step_users()
        assert result["type"] == "abort"
        assert result["reason"] == "not_loaded"


