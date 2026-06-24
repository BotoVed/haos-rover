"""Tests for rover.codec — msgpack encode/decode."""
from __future__ import annotations

from rover.codec import encode, decode


class TestRoundtrip:
    def test_empty_dict_roundtrip(self) -> None:
        original: dict = {}
        decoded = decode(encode(original))
        assert decoded == original

    def test_string_value_roundtrip(self) -> None:
        original = {"key": "hello"}
        decoded = decode(encode(original))
        assert decoded == original

    def test_integer_value_roundtrip(self) -> None:
        original = {"count": 42}
        decoded = decode(encode(original))
        assert decoded == original

    def test_list_value_roundtrip(self) -> None:
        original = {"items": [1, 2, 3]}
        decoded = decode(encode(original))
        assert decoded == original

    def test_nested_dict_roundtrip(self) -> None:
        original = {"outer": {"inner": "deep"}}
        decoded = decode(encode(original))
        assert decoded == original

    def test_mixed_types_roundtrip(self) -> None:
        original = {
            "string": "text",
            "int": 99,
            "float": 3.14,
            "list": [1, "two", 3.0],
            "nested": {"a": 1},
        }
        decoded = decode(encode(original))
        assert decoded == original

    def test_multiple_keys_roundtrip(self) -> None:
        original = {"a": 1, "b": 2, "c": 3, "d": "hello", "e": [4, 5, 6]}
        decoded = decode(encode(original))
        assert decoded == original

    def test_deeply_nested_roundtrip(self) -> None:
        original = {"l1": {"l2": {"l3": {"l4": "deep_value"}}}}
        decoded = decode(encode(original))
        assert decoded == original


class TestEncodeOutput:
    def test_encode_returns_bytes(self) -> None:
        result = encode({"x": 1})
        assert isinstance(result, bytes)

    def test_encode_non_empty(self) -> None:
        result = encode({"x": 1})
        assert len(result) > 0


class TestDecodeInput:
    def test_decode_returns_dict(self) -> None:
        data = encode({"x": 1})
        result = decode(data)
        assert isinstance(result, dict)


class TestEdgeCases:
    def test_large_integer(self) -> None:
        original = {"big": 2**31}
        decoded = decode(encode(original))
        assert decoded == original

    def test_negative_integer(self) -> None:
        original = {"neg": -100}
        decoded = decode(encode(original))
        assert decoded == original

    def test_zero_value(self) -> None:
        original = {"zero": 0}
        decoded = decode(encode(original))
        assert decoded == original

    def test_empty_string(self) -> None:
        original = {"empty": ""}
        decoded = decode(encode(original))
        assert decoded == original

    def test_empty_list(self) -> None:
        original = {"empty_list": []}
        decoded = decode(encode(original))
        assert decoded == original

    def test_unicode_string(self) -> None:
        original = {"emoji": "\u2764\ufe0f", "cjk": "\u4e2d\u6587"}
        decoded = decode(encode(original))
        assert decoded == original

    def test_float_value(self) -> None:
        original = {"pi": 3.14159}
        decoded = decode(encode(original))
        assert decoded == original
