"""Tests for Rover dispatcher — normalize() and RoverDispatcher."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.rover.dispatcher import RoverDispatcher, normalize


# ---------------------------------------------------------------------------
# normalize()
# ---------------------------------------------------------------------------

class TestNormalize:
    """Tests for the normalize() free function."""

    def test_empty_dict_returns_zero_tp(self) -> None:
        tp, result = normalize({})
        assert tp == 0
        assert result == {}

    def test_already_normalized_passthrough(self) -> None:
        """String-keyed dict passes through unchanged (except copy)."""
        fields = {"tp": 5, "section": 3, "extra": True}
        tp, result = normalize(fields)
        assert tp == 5
        assert result["tp"] == 5
        assert result["section"] == 3
        assert result["extra"] is True

    def test_already_normalized_not_mutated(self) -> None:
        """Original dict must not be mutated."""
        fields = {"tp": 5, "x": 1}
        _, _ = normalize(fields)
        assert fields == {"tp": 5, "x": 1}

    def test_integer_keys_general_map_only(self) -> None:
        """tp not in _TP_MAPS — only general keys are mapped."""
        fields = {0: 99, 1: "sec", 2: "hash_val", 3: "payload"}
        tp, result = normalize(fields)
        assert tp == 99
        assert result == {
            "tp": 99,
            "section": "sec",
            "h": "hash_val",
            "data": "payload",
        }

    def test_tp2_status_keys(self) -> None:
        """tp=2 (STATUS) applies per-tp map: v, s, b, ct, rgb."""
        fields = {0: 2, 4: "v", 5: "s", 6: "b", 7: "ct", 8: "rgb"}
        tp, result = normalize(fields)
        assert tp == 2
        assert result["v"] == "v"
        assert result["s"] == "s"
        assert result["b"] == "b"
        assert result["ct"] == "ct"
        assert result["rgb"] == "rgb"
        assert result["tp"] == 2
        assert result.get("v") == "v"  # key 4 → "v" via TP_MAPS[2]

    def test_tp5_cmd_keys(self) -> None:
        """tp=5 (CMD) maps key 35→'id', key 5→'s', key 6→'b', key 7→'ct', key 8→'rgb'."""
        fields = {0: 5, 35: 1001, 5: "on", 6: True, 7: 128}
        tp, result = normalize(fields)
        assert tp == 5
        assert result["id"] == 1001
        assert result["s"] == "on"
        assert result["b"] is True
        assert result["ct"] == 128
        assert result["tp"] == 5
        assert result.get("id") == 1001  # key 35 → "id" via TP_MAPS[5]

    def test_tp9_register_keys(self) -> None:
        """tp=9 (REGISTER) maps uid, dst, name."""
        fields = {0: 9, 49: "uid_val", 50: "dst_val", 36: "name_val"}
        tp, result = normalize(fields)
        assert tp == 9
        assert result["uid"] == "uid_val"
        assert result["dst"] == "dst_val"
        assert result["name"] == "name_val"
        assert result["tp"] == 9

    def test_missing_integer_keys_omitted(self) -> None:
        """Only present integer keys appear in output."""
        fields = {0: 2}  # only tp, no other keys
        tp, result = normalize(fields)
        assert tp == 2
        assert result == {"tp": 2}

    def test_extra_integer_keys_not_in_maps(self) -> None:
        """Unknown integer keys are silently dropped."""
        fields = {0: 2, 42: "surprise"}
        tp, result = normalize(fields)
        assert tp == 2
        assert 42 not in result
        assert "surprise" not in result.values()

    def test_mixed_int_and_string_keys_only_mapped_copied(self) -> None:
        """Integer keys present → only mapped keys are copied; extra string keys are not carried through."""
        fields = {0: 5, 1: 42, "custom": "val"}
        tp, result = normalize(fields)
        assert tp == 5
        assert result["section"] == 42  # key 1 → "section" via GENERAL_MAP
        # "custom" is an unmapped string key — not copied when integer keys are present
        assert "custom" not in result

    def test_tp_not_in_tp_maps_uses_only_general(self) -> None:
        """Unknown tp (not in _TP_MAPS) still gets general keys."""
        fields = {0: 999, 1: "x", 3: "y"}
        tp, result = normalize(fields)
        assert tp == 999
        assert result == {"tp": 999, "section": "x", "data": "y"}

    def test_no_tp_returns_zero(self) -> None:
        """Dict with neither string 'tp' nor int key 0 → tp=0, empty."""
        fields = {5: "val", 6: "other"}
        tp, result = normalize(fields)
        assert tp == 0
        assert result == {}


# ---------------------------------------------------------------------------
# RoverDispatcher
# ---------------------------------------------------------------------------

class TestRoverDispatcher:
    """Tests for the RoverDispatcher class."""

    @pytest.fixture
    def dispatcher(self) -> RoverDispatcher:
        registry = MagicMock()
        return RoverDispatcher(registry)

    @pytest.mark.asyncio
    async def test_dispatch_calls_handler_for_registered_tp(
        self, dispatcher: RoverDispatcher
    ) -> None:
        handler = AsyncMock()
        dispatcher.register_handler(5, handler)

        fields = {0: 5, 35: 42, 5: "on"}
        src = b"\x00" * 16

        await dispatcher.dispatch(src, fields)

        handler.assert_awaited_once()
        call_args = handler.call_args[0]
        assert call_args[0] == src
        assert call_args[1]["tp"] == 5
        assert call_args[1]["id"] == 42
        assert call_args[1]["s"] == "on"

    @pytest.mark.asyncio
    async def test_dispatch_no_handler_calls_default(
        self, dispatcher: RoverDispatcher
    ) -> None:
        default = AsyncMock()
        dispatcher.set_default_handler(default)

        fields = {0: 99}
        src = b"\xaa" * 16

        await dispatcher.dispatch(src, fields)

        default.assert_awaited_once()
        call_args = default.call_args[0]
        assert call_args[0] == src
        assert call_args[1]["tp"] == 99

    @pytest.mark.asyncio
    async def test_dispatch_no_handler_no_default_does_not_raise(
        self, dispatcher: RoverDispatcher
    ) -> None:
        """Unknown tp with no default handler should not raise."""
        await dispatcher.dispatch(b"\x00" * 16, {0: 42})

    @pytest.mark.asyncio
    async def test_dispatch_handler_takes_priority_over_default(
        self, dispatcher: RoverDispatcher
    ) -> None:
        handler = AsyncMock()
        default = AsyncMock()
        dispatcher.register_handler(3, handler)
        dispatcher.set_default_handler(default)

        fields = {0: 3, 1: "push_data"}
        await dispatcher.dispatch(b"\x01" * 16, fields)

        handler.assert_awaited_once()
        default.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_dispatch_already_normalized_fields(
        self, dispatcher: RoverDispatcher
    ) -> None:
        """Handler receives already-normalized dict as-is (with tp)."""
        handler = AsyncMock()
        dispatcher.register_handler(2, handler)

        fields = {"tp": 2, "v": "value", "s": "state"}
        await dispatcher.dispatch(b"\x02" * 16, fields)

        handler.assert_awaited_once()
        received = handler.call_args[0][1]
        assert received["tp"] == 2
        assert received["v"] == "value"
        assert received["s"] == "state"

    @pytest.mark.asyncio
    async def test_dispatch_empty_fields_uses_default(
        self, dispatcher: RoverDispatcher
    ) -> None:
        default = AsyncMock()
        dispatcher.set_default_handler(default)

        await dispatcher.dispatch(b"\x00" * 16, {})

        default.assert_awaited_once()
        # Empty dict → normalize returns (0, {}), so handler gets empty fields
        assert default.call_args[0][1] == {}

    @pytest.mark.asyncio
    async def test_register_handler_overwrites_previous(
        self, dispatcher: RoverDispatcher
    ) -> None:
        first = AsyncMock()
        second = AsyncMock()
        dispatcher.register_handler(5, first)
        dispatcher.register_handler(5, second)

        await dispatcher.dispatch(b"\x00" * 16, {0: 5})

        first.assert_not_awaited()
        second.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_multiple_handlers_dispatched_correctly(
        self, dispatcher: RoverDispatcher
    ) -> None:
        h2 = AsyncMock()
        h3 = AsyncMock()
        h5 = AsyncMock()
        dispatcher.register_handler(2, h2)
        dispatcher.register_handler(3, h3)
        dispatcher.register_handler(5, h5)

        await dispatcher.dispatch(b"\x10" * 16, {0: 2})
        await dispatcher.dispatch(b"\x11" * 16, {0: 3})
        await dispatcher.dispatch(b"\x12" * 16, {0: 5})

        h2.assert_awaited_once()
        h3.assert_awaited_once()
        h5.assert_awaited_once()
        assert h2.call_args[0][1]["tp"] == 2
        assert h3.call_args[0][1]["tp"] == 3
        assert h5.call_args[0][1]["tp"] == 5
