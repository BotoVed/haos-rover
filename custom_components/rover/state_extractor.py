"""State extractor module for Rover integration."""
from __future__ import annotations

from .const import TYPE_TO_DOMAIN


def extract_state(state: str, attributes: dict | None, device_type: str) -> dict:
    """Extract protocol state fields from HA entity state.

    Args:
        state: The entity state (e.g., "on", "off", "open", "closed")
        attributes: The entity attributes dict (can be None)
        device_type: The device type code (e.g., "SW", "LT", "CV")

    Returns:
        Dict with short protocol keys for the device's current state

    Raises:
        ValueError: If device_type is unknown
    """
    if device_type not in TYPE_TO_DOMAIN:
        raise ValueError(f"Unknown device type: {device_type}")

    result: dict = {"v": state}

    if device_type == "SW":
        pass

    elif device_type == "LT":
        if attributes:
            if "brightness" in attributes:
                result["b"] = round(attributes["brightness"] * 100 / 255)
            if "color_temp_kelvin" in attributes:
                result["ct"] = attributes["color_temp_kelvin"]
            if "rgb_color" in attributes:
                result["rgb"] = attributes["rgb_color"]
            if "effect" in attributes:
                result["ef"] = attributes["effect"]

    elif device_type == "CV":
        if attributes:
            if "current_position" in attributes:
                result["p"] = attributes["current_position"]
            if "current_tilt_position" in attributes:
                result["ti"] = attributes["current_tilt_position"]

    elif device_type == "CL":
        if attributes:
            if "temperature" in attributes:
                result["t"] = attributes["temperature"]
            if "current_temperature" in attributes:
                result["tc"] = attributes["current_temperature"]
            if "target_temp_high" in attributes:
                result["th"] = attributes["target_temp_high"]
            if "target_temp_low" in attributes:
                result["tl"] = attributes["target_temp_low"]
            if "fan_mode" in attributes:
                result["fan"] = attributes["fan_mode"]
            if "preset_mode" in attributes:
                result["preset"] = attributes["preset_mode"]
            if "swing_mode" in attributes:
                result["swing_h"] = attributes["swing_mode"]

    elif device_type == "LK":
        pass

    elif device_type == "MS":
        if attributes:
            if "volume_level" in attributes:
                result["vol"] = round(attributes["volume_level"] * 100)
            if "media_title" in attributes:
                result["title"] = attributes["media_title"]
            if "media_artist" in attributes:
                result["artist"] = attributes["media_artist"]
            if "media_album" in attributes:
                result["album"] = attributes["media_album"]
            if "media_duration" in attributes:
                result["dur"] = attributes["media_duration"]
            if "media_position" in attributes:
                result["pos"] = attributes["media_position"]
            if "is_volume_muted" in attributes:
                result["muted"] = attributes["is_volume_muted"]

    elif device_type == "SC":
        pass

    elif device_type == "AL":
        pass

    elif device_type == "SE":
        if attributes:
            if "unit_of_measurement" in attributes:
                result["u"] = attributes["unit_of_measurement"]

    elif device_type == "FN":
        if attributes:
            if "percentage" in attributes:
                result["sp"] = attributes["percentage"]
            if "preset_mode" in attributes:
                result["preset"] = attributes["preset_mode"]
            if "oscillating" in attributes:
                result["osc"] = attributes["oscillating"]
            if "direction" in attributes:
                result["dir"] = attributes["direction"]

    elif device_type == "BT":
        pass

    return result