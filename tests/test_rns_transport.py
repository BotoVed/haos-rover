"""Unit tests for RoverTransport — rns_transport.py.

The constructor changed to:
    RoverTransport(hass, config_dir, on_message, tcp_port=4242)

RNS and LXMF are mocked via tests/conftest.py.  Since MagicMock accepts ANY
attribute, tests verify contracts (return values, call arguments) rather than
checking specific method names.
"""
from __future__ import annotations

import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest

import RNS
import LXMF

from custom_components.rover.rns_transport import (
    RoverTransport,
    _OUT_KEY_MAP,
    _to_wire,
)
from custom_components.rover.codec import encode


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset_shared_mocks():
    """Reset shared RNS/LXMF mock call state between tests.

    MagicMock instances are module-level singletons (from conftest).  Call
    counts, side_effects, and return_values leak across tests unless we
    explicitly reset them.
    """
    yield
    RNS.Identity.recall.reset_mock()
    RNS.Identity.recall.return_value = None
    RNS.Identity.recall.side_effect = None
    RNS.Identity.from_file.reset_mock()
    RNS.Identity.from_file.return_value = None
    RNS.Transport.request_path.reset_mock()
    RNS.Transport.request_path.side_effect = None
    RNS.Destination.reset_mock()
    RNS.Reticulum.reset_mock()
    LXMF.LXMRouter.reset_mock()
    LXMF.LXMessage.reset_mock()


def _configure_identity_mock():
    """Set up RNS.Identity mock so .hash.hex() returns a real string.

    Also configures recall() so send() can look up remote identities.
    """
    identity = MagicMock()
    identity.hash = b"\xab" * 16
    RNS.Identity.return_value = identity
    RNS.Identity.from_file.return_value = identity
    RNS.Identity.recall.return_value = identity
    return identity


def _make_transport(
    hass=None,
    config_dir=None,
    on_message=None,
    tcp_port: int = 4242,
):
    """Build a RoverTransport with real constructor args."""
    return RoverTransport(
        hass=hass or MagicMock(),
        config_dir=config_dir or tempfile.mkdtemp(),
        on_message=on_message or MagicMock(),
        tcp_port=tcp_port,
    )


# ---------------------------------------------------------------------------
# _OUT_KEY_MAP — completeness & integrity
# ---------------------------------------------------------------------------

class TestOutKeyMap:
    """Verify the outbound integer-key mapping table."""

    def test_tp_maps_to_0(self):
        assert _OUT_KEY_MAP["tp"] == 0

    def test_section_maps_to_1(self):
        assert _OUT_KEY_MAP["section"] == 1

    def test_h_maps_to_2(self):
        assert _OUT_KEY_MAP["h"] == 2

    def test_data_maps_to_3(self):
        assert _OUT_KEY_MAP["data"] == 3

    def test_v_maps_to_4(self):
        assert _OUT_KEY_MAP["v"] == 4

    def test_s_maps_to_5(self):
        assert _OUT_KEY_MAP["s"] == 5

    def test_b_maps_to_6(self):
        assert _OUT_KEY_MAP["b"] == 6

    def test_ct_maps_to_7(self):
        assert _OUT_KEY_MAP["ct"] == 7

    def test_rgb_maps_to_8(self):
        assert _OUT_KEY_MAP["rgb"] == 8

    def test_ef_maps_to_9(self):
        assert _OUT_KEY_MAP["ef"] == 9

    def test_cv_maps_to_10(self):
        assert _OUT_KEY_MAP["cv"] == 10

    def test_p_maps_to_11(self):
        assert _OUT_KEY_MAP["p"] == 11

    def test_devices_maps_to_56(self):
        assert _OUT_KEY_MAP["devices"] == 56

    def test_users_maps_to_57(self):
        assert _OUT_KEY_MAP["users"] == 57

    def test_hash_maps_to_37(self):
        assert _OUT_KEY_MAP["hash"] == 37

    def test_id_maps_to_35(self):
        assert _OUT_KEY_MAP["id"] == 35

    def test_name_maps_to_36(self):
        assert _OUT_KEY_MAP["name"] == 36

    def test_version_maps_to_45(self):
        assert _OUT_KEY_MAP["version"] == 45

    def test_swing_v_maps_to_20(self):
        assert _OUT_KEY_MAP["swing_v"] == 20

    def test_m_maps_to_30(self):
        assert _OUT_KEY_MAP["m"] == 30

    def test_a_maps_to_31(self):
        assert _OUT_KEY_MAP["a"] == 31

    def test_d_maps_to_32(self):
        assert _OUT_KEY_MAP["d"] == 32

    def test_reason_maps_to_34(self):
        assert _OUT_KEY_MAP["reason"] == 34

    def test_diffs_maps_to_33(self):
        assert _OUT_KEY_MAP["diffs"] == 33

    def test_sections_maps_to_60(self):
        assert _OUT_KEY_MAP["sections"] == 60

    def test_uid_maps_to_49(self):
        assert _OUT_KEY_MAP["uid"] == 49

    def test_dst_maps_to_50(self):
        assert _OUT_KEY_MAP["dst"] == 50

    def test_src_maps_to_51(self):
        assert _OUT_KEY_MAP["src"] == 51

    def test_all_values_are_integers(self):
        for key, val in _OUT_KEY_MAP.items():
            assert isinstance(val, int), f"{key!r} maps to non-int {val!r}"

    def test_no_duplicate_values(self):
        """All keys should map to unique integers (bijective mapping)."""
        values = list(_OUT_KEY_MAP.values())
        assert len(values) == len(set(values)), "Duplicate values found in _OUT_KEY_MAP"


# ---------------------------------------------------------------------------
# _to_wire() — module-level function
# ---------------------------------------------------------------------------

class TestToWire:
    """_to_wire() translates string keys to integer wire keys."""

    def test_known_keys_map_to_integers(self):
        result = _to_wire({"tp": 9, "v": 2, "s": "hello"})
        # tp→0, v→4, s→5
        assert result == {0: 9, 4: 2, 5: "hello"}

    def test_unknown_string_key_raises_value_error(self):
        """Unknown string keys are not in _OUT_KEY_MAP, so int() conversion
        raises ValueError — the code does not support arbitrary string keys."""
        with pytest.raises(ValueError):
            _to_wire({"unknown_key": "value"})

    def test_empty_dict(self):
        assert _to_wire({}) == {}

    def test_non_string_int_keys_pass_through(self):
        """Integer keys that aren't in the map pass through unchanged."""
        result = _to_wire({42: "numeric_key"})
        assert result == {42: "numeric_key"}

    def test_spot_check_10_entries(self):
        """Spot-check at least 10 known mappings end-to-end."""
        fields = {
            "tp": 9, "v": 2, "s": 3, "b": 4, "ct": 5,
            "rgb": 6, "ef": 7, "cv": 8, "p": 9, "ti": 10,
            "fan": 18, "preset": 19, "vol": 23,
        }
        wire = _to_wire(fields)
        for key in fields:
            assert _OUT_KEY_MAP[key] in wire, f"Key {key!r} not found in wire output"
        assert len(wire) == len(fields)

    def test_all_integer_keys_in_wire_output(self):
        """Every key in the wire output dict should be an integer."""
        wire = _to_wire({"tp": 9, "v": 2, 42: "x"})
        for k in wire:
            assert isinstance(k, int), f"Wire key {k!r} is not an int"

    def test_value_preservation(self):
        """Values are passed through without transformation."""
        result = _to_wire({"tp": "string_val", "v": [1, 2, 3]})
        assert result[0] == "string_val"
        assert result[4] == [1, 2, 3]

    def test_none_value_preserved(self):
        result = _to_wire({"tp": None})
        assert result[0] is None

    def test_nested_dict_value_preserved(self):
        nested = {"inner": {"deep": True}}
        result = _to_wire({"data": nested})
        assert result[3] == nested


# ---------------------------------------------------------------------------
# TestWireRoundTrip — round-trip _to_wire() → normalize()
# ---------------------------------------------------------------------------

class TestWireRoundTrip:
    """Verify _to_wire() → normalize() round-trip for all 9 message types."""

    def test_status_roundtrip(self):
        from custom_components.rover.dispatcher import normalize
        wire = _to_wire({"tp": 2, "data": [{"id": 1, "v": "on"}]})
        tp, norm = normalize(wire)
        assert tp == 2
        assert norm["tp"] == 2
        assert norm["data"] == [{"id": 1, "v": "on"}]

    def test_push_roundtrip(self):
        from custom_components.rover.dispatcher import normalize
        wire = _to_wire({"tp": 3, "id": 1, "v": "on"})
        tp, norm = normalize(wire)
        assert tp == 3
        assert norm["tp"] == 3
        assert norm["id"] == 1
        assert norm["v"] == "on"

    def test_config_roundtrip(self):
        from custom_components.rover.dispatcher import normalize
        wire = _to_wire({"tp": 4, "section": "d", "hash": "78ab", "data": [{"id": 1}]})
        tp, norm = normalize(wire)
        assert tp == 4
        assert norm["tp"] == 4
        assert norm["section"] == "d"
        assert norm["hash"] == "78ab"
        assert norm["data"] == [{"id": 1}]

    def test_cmd_roundtrip(self):
        from custom_components.rover.dispatcher import normalize
        wire = _to_wire({"tp": 5, "id": 1, "s": True})
        tp, norm = normalize(wire)
        assert tp == 5
        assert norm["tp"] == 5
        assert norm["id"] == 1
        assert norm["s"] is True

    def test_ping_roundtrip(self):
        from custom_components.rover.dispatcher import normalize
        wire = _to_wire({"tp": 6, "m": "ab12", "u": "ef34", "a": "cd56", "d": "78ab"})
        tp, norm = normalize(wire)
        assert tp == 6
        assert norm["tp"] == 6
        assert norm["m"] == "ab12"
        assert norm["u"] == "ef34"
        assert norm["a"] == "cd56"
        assert norm["d"] == "78ab"

    def test_pong_roundtrip(self):
        from custom_components.rover.dispatcher import normalize
        wire = _to_wire({"tp": 6, "m": "ab12", "u": "ef34", "a": "cd56", "d": "78ab", "sections": ["d"]})
        tp, norm = normalize(wire)
        assert tp == 6
        assert norm["sections"] == ["d"]

    def test_forbidden_roundtrip(self):
        from custom_components.rover.dispatcher import normalize
        wire = _to_wire({"tp": 7, "reason": "forbidden"})
        tp, norm = normalize(wire)
        assert tp == 7
        assert norm["tp"] == 7
        assert norm["reason"] == "forbidden"

    def test_req_roundtrip(self):
        from custom_components.rover.dispatcher import normalize
        wire = _to_wire({"tp": 8, "sections": ["m", "a", "d"]})
        tp, norm = normalize(wire)
        assert tp == 8
        assert norm["tp"] == 8
        assert norm["sections"] == ["m", "a", "d"]

    def test_register_roundtrip(self):
        from custom_components.rover.dispatcher import normalize
        wire = _to_wire({"tp": 9, "uid": "a1b2", "dst": "f6be97", "name": "Test Phone"})
        tp, norm = normalize(wire)
        assert tp == 9
        assert norm["tp"] == 9
        assert norm["uid"] == "a1b2"
        assert norm["dst"] == "f6be97"
        assert norm["name"] == "Test Phone"


# ---------------------------------------------------------------------------
# async_start() — identity lifecycle
# ---------------------------------------------------------------------------

class TestAsyncStart:
    """async_start() creates/loads identity, starts RNS, returns hash hex."""

    @pytest.mark.asyncio
    async def test_identity_created_when_file_missing(self):
        _configure_identity_mock()
        tr = _make_transport()
        identity_hash = await tr.async_start()

        assert tr._identity is not None
        assert isinstance(identity_hash, str)
        # Identity hash hex should be 32 chars (16 bytes * 2 hex chars)
        assert len(identity_hash) == 32

    @pytest.mark.asyncio
    async def test_identity_loaded_from_file_when_exists(self, tmp_path):
        # Create an identity file first
        identity_dir = str(tmp_path / "rover_config")
        os.makedirs(identity_dir, exist_ok=True)
        identity_path = os.path.join(identity_dir, "identity")
        with open(identity_path, "wb") as f:
            f.write(b"\x00" * 16)

        identity = _configure_identity_mock()
        tr = _make_transport(config_dir=identity_dir)
        identity_hash = await tr.async_start()

        assert tr._identity is not None
        assert isinstance(identity_hash, str)
        assert len(identity_hash) == 32

    @pytest.mark.asyncio
    async def test_returns_valid_hex_string(self):
        _configure_identity_mock()
        tr = _make_transport()
        identity_hash = await tr.async_start()

        # Should be a valid hex string
        assert all(c in "0123456789abcdef" for c in identity_hash)

    @pytest.mark.asyncio
    async def test_creates_config_dir(self):
        _configure_identity_mock()
        config_dir = tempfile.mkdtemp() + "/subdir"
        tr = _make_transport(config_dir=config_dir)
        await tr.async_start()
        assert os.path.isdir(config_dir)

    @pytest.mark.asyncio
    async def test_creates_reticulum_config_file(self):
        _configure_identity_mock()
        config_dir = tempfile.mkdtemp()
        tr = _make_transport(config_dir=config_dir)
        await tr.async_start()
        # RNS expects a file named "config" (ConfigObj INI format)
        config_path = os.path.join(config_dir, "config")
        assert os.path.exists(config_path)

    @pytest.mark.asyncio
    async def test_router_created(self):
        _configure_identity_mock()
        tr = _make_transport()
        await tr.async_start()
        assert tr._router is not None

    @pytest.mark.asyncio
    async def test_delivery_dest_registered(self):
        _configure_identity_mock()
        tr = _make_transport()
        await tr.async_start()
        assert tr._delivery_dest is not None

    @pytest.mark.asyncio
    async def test_delivery_dest_announced(self):
        _configure_identity_mock()
        tr = _make_transport()
        await tr.async_start()
        tr._delivery_dest.announce.assert_called_once()

    @pytest.mark.asyncio
    async def test_delivery_callback_registered(self):
        _configure_identity_mock()
        tr = _make_transport()
        await tr.async_start()
        tr._router.register_delivery_callback.assert_called_once_with(
            tr._on_lxmf_message
        )

    @pytest.mark.asyncio
    async def test_identity_stored_on_instance(self):
        _configure_identity_mock()
        tr = _make_transport()
        await tr.async_start()
        assert tr._identity is not None
        assert tr._identity is RNS.Identity.return_value


# ---------------------------------------------------------------------------
# _on_lxmf_message() — message handling
# ---------------------------------------------------------------------------

class TestOnLxmfMessage:
    """_on_lxmf_message() dispatches fields to the callback."""

    def test_fields_as_dict_passed_to_callback(self):
        cb = MagicMock()
        tr = _make_transport(on_message=cb)

        message = MagicMock()
        message.fields = {"tp": 5, "v": 1}
        message.source_hash = b"\xab" * 16

        tr._on_lxmf_message(message)
        cb.assert_called_once_with(b"\xab" * 16, {"tp": 5, "v": 1})

    def test_fields_as_bytes_decoded_via_codec(self):
        cb = MagicMock()
        tr = _make_transport(on_message=cb)

        # Encode fields as bytes using codec
        original_fields = {"tp": 2, "v": 42}
        encoded = encode(original_fields)

        message = MagicMock()
        message.fields = encoded
        message.source_hash = b"\xcd" * 16

        tr._on_lxmf_message(message)
        cb.assert_called_once_with(b"\xcd" * 16, original_fields)

    def test_no_message_when_shutdown(self):
        cb = MagicMock()
        tr = _make_transport(on_message=cb)
        tr._shutdown = True

        message = MagicMock()
        message.fields = {"tp": 5}
        message.source_hash = b"\x00" * 16

        tr._on_lxmf_message(message)
        cb.assert_not_called()

    def test_empty_fields(self):
        cb = MagicMock()
        tr = _make_transport(on_message=cb)

        message = MagicMock()
        message.fields = {}
        message.source_hash = b"\x00" * 16

        tr._on_lxmf_message(message)
        cb.assert_called_once_with(b"\x00" * 16, {})

    def test_callback_receives_source_hash(self):
        cb = MagicMock()
        tr = _make_transport(on_message=cb)

        source = b"\xef" * 16
        message = MagicMock()
        message.fields = {"tp": 5}
        message.source_hash = source

        tr._on_lxmf_message(message)
        args = cb.call_args[0]
        assert args[0] is source

    def test_dict_fields_not_decoded(self):
        """When fields is already a dict, codec.decode should NOT be called.

        decode is imported locally inside _on_lxmf_message via
        ``from .codec import decode``, so we patch at the codec module.
        """
        cb = MagicMock()
        tr = _make_transport(on_message=cb)

        message = MagicMock()
        message.fields = {"tp": 5}
        message.source_hash = b"\x00" * 16

        with patch("custom_components.rover.codec.decode") as mock_decode:
            tr._on_lxmf_message(message)
            mock_decode.assert_not_called()

    def test_bytes_fields_decoded(self):
        """When fields is bytes, codec.decode IS called."""
        cb = MagicMock()
        tr = _make_transport(on_message=cb)

        message = MagicMock()
        message.fields = b"\x01\x02\x03"
        message.source_hash = b"\x00" * 16

        with patch("custom_components.rover.codec.decode", return_value={"tp": 5}) as mock_decode:
            tr._on_lxmf_message(message)
            mock_decode.assert_called_once_with(b"\x01\x02\x03")


# ---------------------------------------------------------------------------
# send() — sending messages
# ---------------------------------------------------------------------------

class TestSend:
    """send() recalls identity, creates destination, encodes, sends."""

    @pytest.mark.asyncio
    async def test_returns_true_on_success(self):
        _configure_identity_mock()
        tr = _make_transport()
        await tr.async_start()

        result = await tr.send("ab" * 16, {"tp": 5, "v": 1})
        assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_when_identity_not_cached(self):
        _configure_identity_mock()
        tr = _make_transport()
        await tr.async_start()

        # recall returns None by default (from fixture reset)
        RNS.Identity.recall.return_value = None

        result = await tr.send("ab" * 16, {"tp": 5})
        assert result is False

    @pytest.mark.asyncio
    async def test_requests_path_when_identity_not_cached(self):
        _configure_identity_mock()
        tr = _make_transport()
        await tr.async_start()

        RNS.Identity.recall.return_value = None

        await tr.send("ab" * 16, {"tp": 5})
        RNS.Transport.request_path.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_outbound_called(self):
        _configure_identity_mock()
        tr = _make_transport()
        await tr.async_start()

        await tr.send("ab" * 16, {"tp": 5, "v": 1})
        tr._router.handle_outbound.assert_called_once()

    @pytest.mark.asyncio
    async def test_creates_destination(self):
        _configure_identity_mock()
        tr = _make_transport()
        await tr.async_start()

        await tr.send("ab" * 16, {"tp": 5})
        RNS.Destination.assert_called_once()

    @pytest.mark.asyncio
    async def test_lxmessage_created(self):
        _configure_identity_mock()
        tr = _make_transport()
        await tr.async_start()

        await tr.send("ab" * 16, {"tp": 5})
        LXMF.LXMessage.assert_called_once()

    @pytest.mark.asyncio
    async def test_small_payload_uses_opportunistic(self):
        _configure_identity_mock()
        tr = _make_transport()
        await tr.async_start()

        # Set up mock constants
        LXMF.LXMessage.OPPORTUNISTIC = 0
        LXMF.LXMessage.DIRECT = 1

        # Small fields → small payload
        await tr.send("ab" * 16, {"tp": 5, "v": 1})

        # Check desired_method was passed as OPPORTUNISTIC (0)
        call_kwargs = LXMF.LXMessage.call_args
        assert call_kwargs[1]["desired_method"] == 0

    @pytest.mark.asyncio
    async def test_large_payload_uses_direct(self):
        _configure_identity_mock()
        tr = _make_transport()
        await tr.async_start()

        LXMF.LXMessage.OPPORTUNISTIC = 0
        LXMF.LXMessage.DIRECT = 1

        # Large fields → payload > OPPORTUNISTIC_THRESHOLD_BYTES
        large_value = "x" * 500
        await tr.send("ab" * 16, {"tp": 5, "s": large_value})

        call_kwargs = LXMF.LXMessage.call_args
        assert call_kwargs[1]["desired_method"] == 1

    @pytest.mark.asyncio
    async def test_delivery_callbacks_registered(self):
        _configure_identity_mock()
        tr = _make_transport()
        await tr.async_start()

        msg_instance = MagicMock()
        LXMF.LXMessage.return_value = msg_instance

        await tr.send("ab" * 16, {"tp": 5})

        msg_instance.register_delivery_callback.assert_called_once()
        msg_instance.register_failed_callback.assert_called_once()

    @pytest.mark.asyncio
    async def test_fields_converted_to_wire(self):
        _configure_identity_mock()
        tr = _make_transport()
        await tr.async_start()

        msg_instance = MagicMock()
        LXMF.LXMessage.return_value = msg_instance

        await tr.send("ab" * 16, {"tp": 5, "v": 1})

        # msg.fields should be the wire-format dict (integer keys)
        assert msg_instance.fields == {0: 5, 4: 1}

    @pytest.mark.asyncio
    async def test_recall_raises_propagates(self):
        """If recall raises, the exception propagates (source doesn't catch it)."""
        _configure_identity_mock()
        tr = _make_transport()
        await tr.async_start()

        RNS.Identity.recall.side_effect = Exception("recall failed")

        with pytest.raises(Exception, match="recall failed"):
            await tr.send("ab" * 16, {"tp": 5})

    @pytest.mark.asyncio
    async def test_request_path_error_returns_false(self):
        """If request_path raises when recall returns None, send returns False."""
        _configure_identity_mock()
        tr = _make_transport()
        await tr.async_start()

        RNS.Identity.recall.return_value = None
        RNS.Transport.request_path.side_effect = Exception("path failed")

        result = await tr.send("ab" * 16, {"tp": 5})
        assert result is False

    @pytest.mark.asyncio
    async def test_recall_receives_bytes_from_hex(self):
        """recall() is called with bytes decoded from the hex string."""
        _configure_identity_mock()
        tr = _make_transport()
        await tr.async_start()

        hex_hash = "ab" * 16
        expected_bytes = bytes.fromhex(hex_hash)

        await tr.send(hex_hash, {"tp": 5})

        RNS.Identity.recall.assert_called_with(expected_bytes)


# ---------------------------------------------------------------------------
# shutdown() — cleanup
# ---------------------------------------------------------------------------

class TestShutdown:
    """shutdown() stops router and clears state."""

    @pytest.mark.asyncio
    async def test_router_stopped(self):
        _configure_identity_mock()
        tr = _make_transport()
        await tr.async_start()
        router_ref = tr._router  # Save reference before shutdown
        assert router_ref is not None

        await tr.shutdown()
        router_ref.stop.assert_called_once()

    @pytest.mark.asyncio
    async def test_router_cleared(self):
        _configure_identity_mock()
        tr = _make_transport()
        await tr.async_start()
        await tr.shutdown()
        assert tr._router is None

    @pytest.mark.asyncio
    async def test_identity_cleared(self):
        _configure_identity_mock()
        tr = _make_transport()
        await tr.async_start()
        assert tr._identity is not None

        await tr.shutdown()
        assert tr._identity is None

    @pytest.mark.asyncio
    async def test_delivery_dest_cleared(self):
        _configure_identity_mock()
        tr = _make_transport()
        await tr.async_start()
        assert tr._delivery_dest is not None

        await tr.shutdown()
        assert tr._delivery_dest is None

    @pytest.mark.asyncio
    async def test_shutdown_flag_set(self):
        _configure_identity_mock()
        tr = _make_transport()
        await tr.async_start()

        await tr.shutdown()
        assert tr._shutdown is True

    @pytest.mark.asyncio
    async def test_shutdown_without_start_is_safe(self):
        """Calling shutdown before start should not raise."""
        tr = _make_transport()
        await tr.shutdown()
        assert tr._router is None
        assert tr._identity is None

    @pytest.mark.asyncio
    async def test_double_shutdown_is_safe(self):
        _configure_identity_mock()
        tr = _make_transport()
        await tr.async_start()

        await tr.shutdown()
        await tr.shutdown()  # Should not raise


# ---------------------------------------------------------------------------
# set_dispatcher_cb()
# ---------------------------------------------------------------------------

class TestSetDispatcherCb:
    """set_dispatcher_cb() stores and allows calling the callback."""

    def test_callback_is_stored(self):
        tr = _make_transport()
        cb = MagicMock()
        tr.set_dispatcher_cb(cb)
        assert tr._on_message is cb

    def test_callback_is_callable(self):
        tr = _make_transport()
        cb = MagicMock()
        tr.set_dispatcher_cb(cb)

        # Simulate calling the callback
        tr._on_message(b"hash", {"tp": 5})
        cb.assert_called_once_with(b"hash", {"tp": 5})

    def test_replacing_callback(self):
        tr = _make_transport()
        cb1 = MagicMock()
        cb2 = MagicMock()
        tr.set_dispatcher_cb(cb1)
        tr.set_dispatcher_cb(cb2)
        assert tr._on_message is cb2


# ---------------------------------------------------------------------------
# Integration: full lifecycle
# ---------------------------------------------------------------------------

class TestLifecycle:
    """End-to-end lifecycle: start → send → message → shutdown."""

    @pytest.mark.asyncio
    async def test_full_lifecycle(self):
        _configure_identity_mock()
        cb = MagicMock()
        tr = _make_transport(on_message=cb)

        # Start
        identity_hash = await tr.async_start()
        assert tr._identity is not None
        assert tr._router is not None
        assert isinstance(identity_hash, str)
        assert len(identity_hash) == 32

        # Send
        result = await tr.send("ab" * 16, {"tp": 5, "v": 1})
        assert result is True

        # Simulate inbound message
        message = MagicMock()
        message.fields = {"tp": 2, "v": 1}
        message.source_hash = b"\xcd" * 16
        tr._on_lxmf_message(message)
        cb.assert_called_once_with(b"\xcd" * 16, {"tp": 2, "v": 1})

        # Shutdown
        await tr.shutdown()
        assert tr._identity is None
        assert tr._router is None
