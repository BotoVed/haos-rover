"""Unit tests for state_extractor.extract_state."""
from __future__ import annotations

import pytest

from custom_components.rover.state_extractor import extract_state


# ── SW ────────────────────────────────────────────────────────────────────────

class TestSW:
    def test_on(self):
        assert extract_state("on", None, "SW") == {"v": "on"}

    def test_off(self):
        assert extract_state("off", None, "SW") == {"v": "off"}

    def test_with_attrs_ignored(self):
        assert extract_state("on", {"brightness": 100}, "SW") == {"v": "on"}


# ── LT ────────────────────────────────────────────────────────────────────────

class TestLT:
    def test_on_bare(self):
        assert extract_state("on", {}, "LT") == {"v": "on"}

    def test_off_bare(self):
        assert extract_state("off", {}, "LT") == {"v": "off"}

    def test_brightness(self):
        result = extract_state("on", {"brightness": 255}, "LT")
        assert result["v"] == "on"
        assert result["b"] == 100

    def test_brightness_converted_to_100_scale(self):
        """brightness 255 → b 100 (HA 0-255 → Rover 0-100)."""
        result = extract_state("on", {"brightness": 128}, "LT")
        assert result["b"] == round(128 * 100 / 255)

    def test_color_temp(self):
        result = extract_state("on", {"color_temp_kelvin": 4000}, "LT")
        assert result["ct"] == 4000

    def test_rgb_color(self):
        result = extract_state("on", {"rgb_color": [255, 0, 128]}, "LT")
        assert result["rgb"] == [255, 0, 128]

    def test_effect(self):
        result = extract_state("on", {"effect": "rainbow"}, "LT")
        assert result["ef"] == "rainbow"

    def test_all_optional_fields(self):
        attrs = {
            "brightness": 200,
            "color_temp_kelvin": 3500,
            "rgb_color": [10, 20, 30],
            "effect": "colorloop",
        }
        result = extract_state("on", attrs, "LT")
        assert result == {"v": "on", "b": round(200 * 100 / 255), "ct": 3500, "rgb": [10, 20, 30], "ef": "colorloop"}


# ── CV ────────────────────────────────────────────────────────────────────────

class TestCV:
    def test_open(self):
        assert extract_state("open", None, "CV") == {"v": "open"}

    def test_closed(self):
        assert extract_state("closed", None, "CV") == {"v": "closed"}

    def test_position(self):
        result = extract_state("open", {"current_position": 75}, "CV")
        assert result == {"v": "open", "p": 75}

    def test_tilt(self):
        result = extract_state("open", {"current_tilt_position": 45}, "CV")
        assert result == {"v": "open", "ti": 45}

    def test_position_and_tilt(self):
        result = extract_state("open", {"current_position": 80, "current_tilt_position": 20}, "CV")
        assert result == {"v": "open", "p": 80, "ti": 20}


# ── CL ────────────────────────────────────────────────────────────────────────

class TestCL:
    def test_cooling(self):
        assert extract_state("cooling", None, "CL") == {"v": "cooling"}

    def test_temperature(self):
        result = extract_state("cooling", {"temperature": 22.5}, "CL")
        assert result == {"v": "cooling", "t": 22.5}

    def test_current_temperature(self):
        result = extract_state("cooling", {"current_temperature": 24.0}, "CL")
        assert result == {"v": "cooling", "tc": 24.0}

    def test_temp_high_low(self):
        attrs = {"target_temp_high": 26, "target_temp_low": 18}
        result = extract_state("cooling", attrs, "CL")
        assert result == {"v": "cooling", "th": 26, "tl": 18}

    def test_fan_mode(self):
        result = extract_state("cooling", {"fan_mode": "auto"}, "CL")
        assert result == {"v": "cooling", "fan": "auto"}

    def test_preset_mode(self):
        result = extract_state("cooling", {"preset_mode": "eco"}, "CL")
        assert result == {"v": "cooling", "preset": "eco"}

    def test_swing_mode(self):
        result = extract_state("cooling", {"swing_mode": "horizontal"}, "CL")
        assert result == {"v": "cooling", "swing_h": "horizontal"}

    def test_all_fields(self):
        attrs = {
            "temperature": 23,
            "current_temperature": 25,
            "target_temp_high": 28,
            "target_temp_low": 16,
            "fan_mode": "low",
            "preset_mode": "away",
            "swing_mode": "full",
        }
        result = extract_state("heating", attrs, "CL")
        assert result == {
            "v": "heating",
            "t": 23,
            "tc": 25,
            "th": 28,
            "tl": 16,
            "fan": "low",
            "preset": "away",
            "swing_h": "full",
        }


# ── LK ────────────────────────────────────────────────────────────────────────

class TestLK:
    def test_locked(self):
        assert extract_state("locked", None, "LK") == {"v": "locked"}

    def test_unlocked(self):
        assert extract_state("unlocked", None, "LK") == {"v": "unlocked"}


# ── MS ────────────────────────────────────────────────────────────────────────

class TestMS:
    def test_playing(self):
        assert extract_state("playing", None, "MS") == {"v": "playing"}

    def test_volume_level(self):
        result = extract_state("playing", {"volume_level": 0.5}, "MS")
        assert result == {"v": "playing", "vol": 50}

    def test_volume_100(self):
        result = extract_state("playing", {"volume_level": 1.0}, "MS")
        assert result == {"v": "playing", "vol": 100}

    def test_metadata(self):
        attrs = {
            "media_title": "Song",
            "media_artist": "Artist",
            "media_album": "Album",
        }
        result = extract_state("playing", attrs, "MS")
        assert result["title"] == "Song"
        assert result["artist"] == "Artist"
        assert result["album"] == "Album"

    def test_duration_and_position(self):
        attrs = {"media_duration": 300, "media_position": 120}
        result = extract_state("playing", attrs, "MS")
        assert result["dur"] == 300
        assert result["pos"] == 120

    def test_muted(self):
        result = extract_state("playing", {"is_volume_muted": True}, "MS")
        assert result["muted"] is True

    def test_all_fields(self):
        attrs = {
            "volume_level": 0.75,
            "media_title": "Track",
            "media_artist": "Art",
            "media_album": "Alb",
            "media_duration": 240,
            "media_position": 60,
            "is_volume_muted": False,
        }
        result = extract_state("playing", attrs, "MS")
        assert result == {
            "v": "playing",
            "vol": round(0.75 * 100),
            "title": "Track",
            "artist": "Art",
            "album": "Alb",
            "dur": 240,
            "pos": 60,
            "muted": False,
        }


# ── SC ────────────────────────────────────────────────────────────────────────

class TestSC:
    def test_any_state(self):
        assert extract_state("on", None, "SC") == {"v": "on"}

    def test_with_attrs(self):
        assert extract_state("on", {"extra": "data"}, "SC") == {"v": "on"}


# ── AL ────────────────────────────────────────────────────────────────────────

class TestAL:
    def test_armed_home(self):
        assert extract_state("armed_home", None, "AL") == {"v": "armed_home"}

    def test_disarmed(self):
        assert extract_state("disarmed", None, "AL") == {"v": "disarmed"}

    def test_alarmed(self):
        assert extract_state("triggered", None, "AL") == {"v": "triggered"}


# ── SE ────────────────────────────────────────────────────────────────────────

class TestSE:
    def test_numeric_value(self):
        result = extract_state("23.5", None, "SE")
        assert result == {"v": "23.5"}

    def test_with_unit(self):
        result = extract_state("23.5", {"unit_of_measurement": "°C"}, "SE")
        assert result == {"v": "23.5", "u": "°C"}

    def test_without_unit(self):
        result = extract_state("on", None, "SE")
        assert result == {"v": "on"}


# ── FN ────────────────────────────────────────────────────────────────────────

class TestFN:
    def test_on(self):
        assert extract_state("on", None, "FN") == {"v": "on"}

    def test_percentage(self):
        result = extract_state("on", {"percentage": 75}, "FN")
        assert result == {"v": "on", "sp": 75}

    def test_preset_mode(self):
        result = extract_state("on", {"preset_mode": "breeze"}, "FN")
        assert result == {"v": "on", "preset": "breeze"}

    def test_oscillating_true(self):
        result = extract_state("on", {"oscillating": True}, "FN")
        assert result == {"v": "on", "osc": True}

    def test_oscillating_false(self):
        result = extract_state("on", {"oscillating": False}, "FN")
        assert result == {"v": "on", "osc": False}

    def test_direction(self):
        result = extract_state("on", {"direction": "reverse"}, "FN")
        assert result == {"v": "on", "dir": "reverse"}

    def test_all_fields(self):
        attrs = {
            "percentage": 50,
            "preset_mode": "nature",
            "oscillating": True,
            "direction": "forward",
        }
        result = extract_state("on", attrs, "FN")
        assert result == {
            "v": "on",
            "sp": 50,
            "preset": "nature",
            "osc": True,
            "dir": "forward",
        }


# ── BT ────────────────────────────────────────────────────────────────────────

class TestBT:
    def test_any_state(self):
        assert extract_state("pressed", None, "BT") == {"v": "pressed"}


# ── Edge cases ────────────────────────────────────────────────────────────────

class TestEdgeCases:
    def test_unknown_type_raises(self):
        with pytest.raises(ValueError, match="Unknown device type"):
            extract_state("on", None, "ZZ")

    def test_empty_string_type_raises(self):
        with pytest.raises(ValueError, match="Unknown device type"):
            extract_state("on", None, "")

    def test_attributes_none_lt(self):
        result = extract_state("on", None, "LT")
        assert result == {"v": "on"}

    def test_attributes_none_cv(self):
        result = extract_state("open", None, "CV")
        assert result == {"v": "open"}

    def test_attributes_none_cl(self):
        result = extract_state("cooling", None, "CL")
        assert result == {"v": "cooling"}

    def test_attributes_none_ms(self):
        result = extract_state("playing", None, "MS")
        assert result == {"v": "playing"}

    def test_attributes_none_fn(self):
        result = extract_state("on", None, "FN")
        assert result == {"v": "on"}

    def test_attributes_none_se(self):
        result = extract_state("23", None, "SE")
        assert result == {"v": "23"}

    def test_empty_attributes_dict(self):
        """Empty dict is still falsy-free, but the code checks truthiness."""
        result = extract_state("on", {}, "LT")
        assert result == {"v": "on"}

    def test_unrelated_attrs_ignored(self):
        result = extract_state("on", {"unrelated_key": 42}, "SW")
        assert result == {"v": "on"}
