"""Unit tests for commands.build_service_call."""
from __future__ import annotations

import pytest

from custom_components.rover.commands import build_service_call
from custom_components.rover.const import TYPE_TO_DOMAIN


# ── SW ────────────────────────────────────────────────────────────────────────

class TestSW:
    def test_turn_on(self):
        result = build_service_call("SW", {"s": True})
        assert result == [("switch", "turn_on", {})]

    def test_turn_off(self):
        result = build_service_call("SW", {"s": False})
        assert result == [("switch", "turn_off", {})]

    def test_default_is_off(self):
        result = build_service_call("SW", {})
        assert result == [("switch", "turn_off", {})]


# ── LT ────────────────────────────────────────────────────────────────────────

class TestLT:
    def test_turn_off_default(self):
        result = build_service_call("LT", {})
        assert result == [("light", "turn_off", {})]

    def test_turn_off_explicit(self):
        result = build_service_call("LT", {"s": False})
        assert result == [("light", "turn_off", {})]

    def test_turn_on_bare(self):
        result = build_service_call("LT", {"s": True})
        assert result == [("light", "turn_on", {})]

    def test_brightness(self):
        result = build_service_call("LT", {"s": True, "b": 100})
        assert result == [("light", "turn_on", {"brightness": 255})]

    def test_rgb(self):
        result = build_service_call("LT", {"s": True, "rgb": [255, 0, 128]})
        assert result == [("light", "turn_on", {"rgb_color": [255, 0, 128]})]

    def test_color_temp(self):
        result = build_service_call("LT", {"s": True, "ct": 4000})
        assert result == [("light", "turn_on", {"color_temp_kelvin": 4000})]

    def test_effect(self):
        result = build_service_call("LT", {"s": True, "ef": "rainbow"})
        assert result == [("light", "turn_on", {"effect": "rainbow"})]

    def test_all_fields(self):
        result = build_service_call("LT", {
            "s": True, "b": 128, "ct": 3500, "rgb": [10, 20, 30], "ef": "colorloop"
        })
        expected = [
            ("light", "turn_on", {
                "brightness": round(128 * 255 / 100),
                "color_temp_kelvin": 3500,
                "rgb_color": [10, 20, 30],
                "effect": "colorloop",
            })
        ]
        assert result == expected


# ── CV ────────────────────────────────────────────────────────────────────────

class TestCV:
    def test_open(self):
        result = build_service_call("CV", {"cv": "open"})
        assert result == [("cover", "open_cover", {})]

    def test_close(self):
        result = build_service_call("CV", {"cv": "close"})
        assert result == [("cover", "close_cover", {})]

    def test_stop(self):
        result = build_service_call("CV", {"cv": "stop"})
        assert result == [("cover", "stop_cover", {})]

    def test_set_position(self):
        result = build_service_call("CV", {"cv": "set", "p": 75})
        assert result == [("cover", "set_cover_position", {"position": 75})]

    def test_set_tilt(self):
        result = build_service_call("CV", {"cv": "set", "ti": 45})
        assert result == [
            ("cover", "set_cover_position", {}),
            ("cover", "set_cover_tilt_position", {"tilt_position": 45}),
        ]

    def test_set_position_and_tilt(self):
        result = build_service_call("CV", {"cv": "set", "p": 60, "ti": 30})
        assert result == [
            ("cover", "set_cover_position", {"position": 60}),
            ("cover", "set_cover_tilt_position", {"tilt_position": 30}),
        ]


# ── CL ────────────────────────────────────────────────────────────────────────

class TestCL:
    def test_hvac_mode(self):
        result = build_service_call("CL", {"hvac": "cool"})
        assert result == [("climate", "set_hvac_mode", {"hvac_mode": "cool"})]

    def test_temperature(self):
        result = build_service_call("CL", {"t": 22.5})
        assert result == [("climate", "set_temperature", {"temperature": 22.5})]

    def test_temp_range_both(self):
        result = build_service_call("CL", {"th": 26, "tl": 18})
        assert result == [("climate", "set_temperature", {"target_temp_high": 26, "target_temp_low": 18})]

    def test_temp_range_high_only(self):
        result = build_service_call("CL", {"th": 26})
        assert result == [("climate", "set_temperature", {"target_temp_high": 26})]

    def test_temp_range_low_only(self):
        result = build_service_call("CL", {"tl": 18})
        assert result == [("climate", "set_temperature", {"target_temp_low": 18})]

    def test_fan_mode(self):
        result = build_service_call("CL", {"fan": "auto"})
        assert result == [("climate", "set_fan_mode", {"fan_mode": "auto"})]

    def test_preset_mode(self):
        result = build_service_call("CL", {"preset": "eco"})
        assert result == [("climate", "set_preset_mode", {"preset_mode": "eco"})]

    def test_swing_h(self):
        result = build_service_call("CL", {"swing_h": "horizontal"})
        assert result == [("climate", "set_swing_mode", {"swing_mode": "horizontal"})]

    def test_swing_v(self):
        result = build_service_call("CL", {"swing_v": "vertical"})
        assert result == [("climate", "set_swing_mode", {"swing_mode": "vertical"})]

    def test_multiple_commands(self):
        result = build_service_call("CL", {
            "hvac": "heat", "t": 23, "fan": "low", "preset": "away"
        })
        assert len(result) == 4
        assert result[0] == ("climate", "set_hvac_mode", {"hvac_mode": "heat"})
        assert result[1] == ("climate", "set_temperature", {"temperature": 23})
        assert result[2] == ("climate", "set_fan_mode", {"fan_mode": "low"})
        assert result[3] == ("climate", "set_preset_mode", {"preset_mode": "away"})


# ── LK ────────────────────────────────────────────────────────────────────────

class TestLK:
    def test_lock(self):
        result = build_service_call("LK", {"s": True})
        assert result == [("lock", "lock", {})]

    def test_unlock(self):
        result = build_service_call("LK", {"s": False})
        assert result == [("lock", "unlock", {})]

    def test_default_unlocks(self):
        result = build_service_call("LK", {})
        assert result == [("lock", "unlock", {})]


# ── MS ────────────────────────────────────────────────────────────────────────

class TestMS:
    def test_play(self):
        assert build_service_call("MS", {"ms": "play"}) == [("media_player", "media_play", {})]

    def test_pause(self):
        assert build_service_call("MS", {"ms": "pause"}) == [("media_player", "media_pause", {})]

    def test_stop(self):
        assert build_service_call("MS", {"ms": "stop"}) == [("media_player", "media_stop", {})]

    def test_next(self):
        assert build_service_call("MS", {"ms": "next"}) == [("media_player", "next_track", {})]

    def test_prev(self):
        assert build_service_call("MS", {"ms": "prev"}) == [("media_player", "previous_track", {})]

    def test_volume_set(self):
        assert build_service_call("MS", {"ms": "vol", "vol": 50}) == [
            ("media_player", "volume_set", {"volume": 0.5})
        ]

    def test_mute(self):
        assert build_service_call("MS", {"ms": "mute"}) == [("media_player", "volume_mute", {"is_volume_muted": True})]

    def test_unmute(self):
        assert build_service_call("MS", {"ms": "unmute"}) == [("media_player", "volume_mute", {"is_volume_muted": False})]

    def test_seek(self):
        assert build_service_call("MS", {"ms": "seek", "seek": 120}) == [
            ("media_player", "media_seek", {"seek_position": 120})
        ]


# ── SC ────────────────────────────────────────────────────────────────────────

class TestSC:
    def test_turn_on(self):
        assert build_service_call("SC", {}) == [("scene", "turn_on", {})]

    def test_any_input_turns_on(self):
        assert build_service_call("SC", {"anything": "value"}) == [("scene", "turn_on", {})]


# ── AL ────────────────────────────────────────────────────────────────────────

class TestAL:
    def test_arm_home(self):
        assert build_service_call("AL", {"al": "arm_home"}) == [
            ("alarm_control_panel", "alarm_arm_home", {})
        ]

    def test_arm_away(self):
        assert build_service_call("AL", {"al": "arm_away"}) == [
            ("alarm_control_panel", "alarm_arm_away", {})
        ]

    def test_arm_night(self):
        assert build_service_call("AL", {"al": "arm_night"}) == [
            ("alarm_control_panel", "alarm_arm_night", {})
        ]

    def test_disarm(self):
        assert build_service_call("AL", {"al": "disarm"}) == [
            ("alarm_control_panel", "alarm_disarm", {})
        ]


# ── SE ────────────────────────────────────────────────────────────────────────

class TestSE:
    def test_returns_empty(self):
        assert build_service_call("SE", {}) == []

    def test_returns_empty_with_fields(self):
        assert build_service_call("SE", {"some_field": "value"}) == []


# ── FN ────────────────────────────────────────────────────────────────────────

class TestFN:
    def test_turn_on(self):
        assert build_service_call("FN", {"s": True}) == [("fan", "turn_on", {})]

    def test_turn_off(self):
        assert build_service_call("FN", {"s": False}) == [("fan", "turn_off", {})]

    def test_percentage(self):
        # FN always emits turn_on/off first (s defaults False)
        result = build_service_call("FN", {"sp": 75})
        assert result == [("fan", "turn_off", {}), ("fan", "set_percentage", {"percentage": 75})]

    def test_preset_mode(self):
        result = build_service_call("FN", {"preset": "breeze"})
        assert result == [
            ("fan", "turn_off", {}),
            ("fan", "set_preset_mode", {"preset_mode": "breeze"}),
        ]

    def test_oscillate(self):
        result = build_service_call("FN", {"osc": True})
        assert result == [("fan", "turn_off", {}), ("fan", "oscillate", {"oscillating": True})]

    def test_direction(self):
        result = build_service_call("FN", {"dir": "reverse"})
        assert result == [
            ("fan", "turn_off", {}),
            ("fan", "set_direction", {"direction": "reverse"}),
        ]

    def test_all_fields(self):
        result = build_service_call("FN", {
            "s": True, "sp": 50, "preset": "nature", "osc": False, "dir": "forward"
        })
        assert len(result) == 5
        assert result[0] == ("fan", "turn_on", {})
        assert result[1] == ("fan", "set_percentage", {"percentage": 50})
        assert result[2] == ("fan", "set_preset_mode", {"preset_mode": "nature"})
        assert result[3] == ("fan", "oscillate", {"oscillating": False})
        assert result[4] == ("fan", "set_direction", {"direction": "forward"})


# ── BT ────────────────────────────────────────────────────────────────────────

class TestBT:
    def test_press(self):
        assert build_service_call("BT", {}) == [("button", "press", {})]


# ── Unknown / edge cases ─────────────────────────────────────────────────────

class TestEdgeCases:
    def test_unknown_type_raises(self):
        with pytest.raises(ValueError, match="Unknown device type"):
            build_service_call("ZZ", {})

    def test_completely_invalid_type(self):
        with pytest.raises(ValueError, match="Unknown device type"):
            build_service_call("", {})

    def test_empty_cmd_fields_sw(self):
        result = build_service_call("SW", {})
        assert result == [("switch", "turn_off", {})]

    def test_empty_cmd_fields_cv(self):
        result = build_service_call("CV", {})
        assert result == []

    def test_empty_cmd_fields_cl(self):
        result = build_service_call("CL", {})
        assert result == []

    def test_empty_cmd_fields_ms(self):
        result = build_service_call("MS", {})
        assert result == []

    def test_empty_cmd_fields_fn(self):
        result = build_service_call("FN", {})
        assert result == [("fan", "turn_off", {})]

    def test_empty_cmd_fields_al(self):
        result = build_service_call("AL", {})
        assert result == []
