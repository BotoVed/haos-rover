"""Commands module for Rover integration."""
from __future__ import annotations

from .const import TYPE_TO_DOMAIN


def build_service_call(device_type: str, cmd_fields: dict) -> list[tuple[str, str, dict]]:
    """Build HA service call tuples from Rover CMD message fields by device type.

    Args:
        device_type: The device type code (e.g., "SW", "LT", "CV")
        cmd_fields: The command fields from the Rover CMD message

    Returns:
        List of (domain, service, service_data) tuples for sequential service calls

    Raises:
        ValueError: If device_type is unknown
    """
    domain = TYPE_TO_DOMAIN.get(device_type)
    if domain is None:
        raise ValueError(f"Unknown device type: {device_type}")

    result: list[tuple[str, str, dict]] = []

    if device_type == "SW":
        s = cmd_fields.get("s", False)
        service = "turn_on" if s else "turn_off"
        result.append((domain, service, {}))

    elif device_type == "LT":
        s = cmd_fields.get("s", False)
        if not s:
            result.append((domain, "turn_off", {}))
        else:
            service_data = {}
            if "b" in cmd_fields:
                service_data["brightness"] = round(cmd_fields["b"] * 255 / 100)
            if "ct" in cmd_fields:
                service_data["color_temp_kelvin"] = cmd_fields["ct"]
            if "rgb" in cmd_fields:
                service_data["rgb_color"] = cmd_fields["rgb"]
            if "ef" in cmd_fields:
                service_data["effect"] = cmd_fields["ef"]
            result.append((domain, "turn_on", service_data))

    elif device_type == "CV":
        cv = cmd_fields.get("cv")
        if cv == "open":
            result.append((domain, "open_cover", {}))
        elif cv == "close":
            result.append((domain, "close_cover", {}))
        elif cv == "stop":
            result.append((domain, "stop_cover", {}))
        elif cv == "set":
            service_data = {}
            if "p" in cmd_fields:
                service_data["position"] = cmd_fields["p"]
            result.append((domain, "set_cover_position", service_data))
            if "ti" in cmd_fields:
                result.append((domain, "set_cover_tilt_position", {"tilt_position": cmd_fields["ti"]}))

    elif device_type == "CL":
        hvac = cmd_fields.get("hvac")
        if hvac:
            result.append((domain, "set_hvac_mode", {"hvac_mode": hvac}))
        if "t" in cmd_fields:
            result.append((domain, "set_temperature", {"temperature": cmd_fields["t"]}))
        if "th" in cmd_fields or "tl" in cmd_fields:
            service_data = {}
            if "th" in cmd_fields:
                service_data["target_temp_high"] = cmd_fields["th"]
            if "tl" in cmd_fields:
                service_data["target_temp_low"] = cmd_fields["tl"]
            result.append((domain, "set_temperature", service_data))
        fan = cmd_fields.get("fan")
        if fan:
            result.append((domain, "set_fan_mode", {"fan_mode": fan}))
        preset = cmd_fields.get("preset")
        if preset:
            result.append((domain, "set_preset_mode", {"preset_mode": preset}))
        swing_h = cmd_fields.get("swing_h")
        if swing_h:
            result.append((domain, "set_swing_mode", {"swing_mode": swing_h}))
        swing_v = cmd_fields.get("swing_v")
        if swing_v:
            result.append((domain, "set_swing_mode", {"swing_mode": swing_v}))

    elif device_type == "LK":
        s = cmd_fields.get("s", False)
        service = "lock" if s else "unlock"
        result.append((domain, service, {}))

    elif device_type == "MS":
        ms = cmd_fields.get("ms")
        if ms == "play":
            result.append((domain, "media_play", {}))
        elif ms == "pause":
            result.append((domain, "media_pause", {}))
        elif ms == "stop":
            result.append((domain, "media_stop", {}))
        elif ms == "next":
            result.append((domain, "next_track", {}))
        elif ms == "prev":
            result.append((domain, "previous_track", {}))
        elif ms == "vol":
            result.append((domain, "volume_set", {"volume": cmd_fields.get("vol", 0) / 100}))
        elif ms == "mute":
            result.append((domain, "volume_mute", {"is_volume_muted": True}))
        elif ms == "unmute":
            result.append((domain, "volume_mute", {"is_volume_muted": False}))
        elif ms == "seek":
            result.append((domain, "media_seek", {"seek_position": cmd_fields.get("seek")}))

    elif device_type == "SC":
        result.append((domain, "turn_on", {}))

    elif device_type == "AL":
        al = cmd_fields.get("al")
        if al == "arm_home":
            result.append((domain, "alarm_arm_home", {}))
        elif al == "arm_away":
            result.append((domain, "alarm_arm_away", {}))
        elif al == "arm_night":
            result.append((domain, "alarm_arm_night", {}))
        elif al == "disarm":
            result.append((domain, "alarm_disarm", {}))

    elif device_type == "SE":
        pass

    elif device_type == "FN":
        s = cmd_fields.get("s", False)
        if s:
            result.append((domain, "turn_on", {}))
        else:
            result.append((domain, "turn_off", {}))
        if "sp" in cmd_fields:
            result.append((domain, "set_percentage", {"percentage": cmd_fields["sp"]}))
        if "preset" in cmd_fields:
            result.append((domain, "set_preset_mode", {"preset_mode": cmd_fields["preset"]}))
        if "osc" in cmd_fields:
            result.append((domain, "oscillate", {"oscillating": cmd_fields["osc"]}))
        if "dir" in cmd_fields:
            result.append((domain, "set_direction", {"direction": cmd_fields["dir"]}))

    elif device_type == "BT":
        result.append((domain, "press", {}))

    return result