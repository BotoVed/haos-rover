"""Tests for rover.const — all constants."""
from __future__ import annotations

from rover.const import (
    DOMAIN,
    TP_STATUS,
    TP_PUSH,
    TP_CONFIG,
    TP_CMD,
    TP_PING_PONG,
    TP_FORBIDDEN,
    TP_REQ,
    TP_REGISTER,
    TYPE_DEFS,
    DOMAIN_TO_TYPE,
    ROLE_OWNER,
    ROLE_REGULAR,
    MAX_ACTIVE_REMOTES,
    MAX_PENDING_REMOTES,
    SHORT_ID_MAX,
    SHORT_ID_MIN,
    TYPE_NAMES,
    TYPE_TO_DOMAIN,
    IDENTITY_HASH_LEN,
    DISPLAY_NAME_MAX_LEN,
    SECTION_HASH_LEN,
    PUSH_THROTTLE_MS,
    QR_FORMAT_VERSION,
    DEFAULT_TCP_PORT,
    QR_TOKEN_LEN,
    LOGGER_ROOT,
    LOGGER_RNS,
    LOGGER_REG,
    LOGGER_TRN,
    LOGGER_HAB,
    LOGGER_HND,
    STORAGE_KEY,
    STORAGE_VERSION,
    PONG_BROADCAST_INTERVAL_S,
    WATCHDOG_INTERVAL_S,
    AWAIT_PATH_TIMEOUT_S,
    OPPORTUNISTIC_THRESHOLD_BYTES,
    SENSOR_PUSH_INTERVAL,
    BRIGHTNESS_RANGE,
    VOLUME_RANGE,
)


class TestDomain:
    def test_domain_value(self) -> None:
        assert DOMAIN == "rover"


class TestMessageTypes:
    def test_tp_status(self) -> None:
        assert TP_STATUS == 2

    def test_tp_push(self) -> None:
        assert TP_PUSH == 3

    def test_tp_config(self) -> None:
        assert TP_CONFIG == 4

    def test_tp_cmd(self) -> None:
        assert TP_CMD == 5

    def test_tp_ping_pong(self) -> None:
        assert TP_PING_PONG == 6

    def test_tp_forbidden(self) -> None:
        assert TP_FORBIDDEN == 7

    def test_tp_req(self) -> None:
        assert TP_REQ == 8

    def test_tp_register(self) -> None:
        assert TP_REGISTER == 9

    def test_all_tp_values_unique(self) -> None:
        tp_values = [TP_STATUS, TP_PUSH, TP_CONFIG, TP_CMD, TP_PING_PONG, TP_FORBIDDEN, TP_REQ, TP_REGISTER]
        assert len(tp_values) == len(set(tp_values))

    def test_tp_values_are_consecutive(self) -> None:
        tp_values = sorted([TP_STATUS, TP_PUSH, TP_CONFIG, TP_CMD, TP_PING_PONG, TP_FORBIDDEN, TP_REQ, TP_REGISTER])
        assert tp_values == [2, 3, 4, 5, 6, 7, 8, 9]


class TestTypeDefs:
    def test_all_11_device_types(self) -> None:
        assert len(TYPE_DEFS) == 11

    def test_switch_domain(self) -> None:
        assert TYPE_DEFS["SW"] == {"domain": "switch", "name": "Switch"}

    def test_light_domain(self) -> None:
        assert TYPE_DEFS["LT"] == {"domain": "light", "name": "Light"}

    def test_cover_domain(self) -> None:
        assert TYPE_DEFS["CV"] == {"domain": "cover", "name": "Cover"}

    def test_climate_domain(self) -> None:
        assert TYPE_DEFS["CL"] == {"domain": "climate", "name": "Climate"}

    def test_lock_domain(self) -> None:
        assert TYPE_DEFS["LK"] == {"domain": "lock", "name": "Lock"}

    def test_media_player_domain(self) -> None:
        assert TYPE_DEFS["MS"] == {"domain": "media_player", "name": "Media Player"}

    def test_scene_domain(self) -> None:
        assert TYPE_DEFS["SC"] == {"domain": "scene", "name": "Scene"}

    def test_alarm_domain(self) -> None:
        assert TYPE_DEFS["AL"] == {"domain": "alarm_control_panel", "name": "Alarm Panel"}

    def test_sensor_domain(self) -> None:
        assert TYPE_DEFS["SE"] == {"domain": "sensor", "name": "Sensor"}

    def test_fan_domain(self) -> None:
        assert TYPE_DEFS["FN"] == {"domain": "fan", "name": "Fan"}

    def test_button_domain(self) -> None:
        assert TYPE_DEFS["BT"] == {"domain": "button", "name": "Button"}

    def test_each_entry_has_domain_and_name(self) -> None:
        for code, entry in TYPE_DEFS.items():
            assert "domain" in entry, f"{code} missing 'domain'"
            assert "name" in entry, f"{code} missing 'name'"

    def test_all_domains_unique(self) -> None:
        domains = [v["domain"] for v in TYPE_DEFS.values()]
        assert len(domains) == len(set(domains))


class TestDomainToType:
    def test_binary_sensor_maps_to_se(self) -> None:
        assert DOMAIN_TO_TYPE["binary_sensor"] == "SE"

    def test_sensor_maps_to_se(self) -> None:
        assert DOMAIN_TO_TYPE["sensor"] == "SE"

    def test_switch_maps_to_sw(self) -> None:
        assert DOMAIN_TO_TYPE["switch"] == "SW"

    def test_light_maps_to_lt(self) -> None:
        assert DOMAIN_TO_TYPE["light"] == "LT"

    def test_cover_maps_to_cv(self) -> None:
        assert DOMAIN_TO_TYPE["cover"] == "CV"

    def test_climate_maps_to_cl(self) -> None:
        assert DOMAIN_TO_TYPE["climate"] == "CL"

    def test_lock_maps_to_lk(self) -> None:
        assert DOMAIN_TO_TYPE["lock"] == "LK"

    def test_media_player_maps_to_ms(self) -> None:
        assert DOMAIN_TO_TYPE["media_player"] == "MS"

    def test_scene_maps_to_sc(self) -> None:
        assert DOMAIN_TO_TYPE["scene"] == "SC"

    def test_alarm_maps_to_al(self) -> None:
        assert DOMAIN_TO_TYPE["alarm_control_panel"] == "AL"

    def test_fan_maps_to_fn(self) -> None:
        assert DOMAIN_TO_TYPE["fan"] == "FN"

    def test_button_maps_to_bt(self) -> None:
        assert DOMAIN_TO_TYPE["button"] == "BT"

    def test_domain_to_type_has_12_entries(self) -> None:
        # 11 from TYPE_DEFS + 1 explicit binary_sensor
        assert len(DOMAIN_TO_TYPE) == 12


class TestRoles:
    def test_role_owner(self) -> None:
        assert ROLE_OWNER == "owner"

    def test_role_regular(self) -> None:
        assert ROLE_REGULAR == "regular"


class TestLimits:
    def test_max_active_remotes(self) -> None:
        assert MAX_ACTIVE_REMOTES == 5

    def test_max_pending_remotes(self) -> None:
        assert MAX_PENDING_REMOTES == 10

    def test_short_id_max(self) -> None:
        assert SHORT_ID_MAX == 0xFFFF

    def test_short_id_min(self) -> None:
        assert SHORT_ID_MIN == 1


class TestOtherConstants:
    def test_identity_hash_len(self) -> None:
        assert IDENTITY_HASH_LEN == 16

    def test_display_name_max_len(self) -> None:
        assert DISPLAY_NAME_MAX_LEN == 32

    def test_section_hash_len(self) -> None:
        assert SECTION_HASH_LEN == 4

    def test_push_throttle_ms(self) -> None:
        assert PUSH_THROTTLE_MS == 500

    def test_qr_format_version(self) -> None:
        assert QR_FORMAT_VERSION == 2

    def test_default_tcp_port(self) -> None:
        assert DEFAULT_TCP_PORT == 4242

    def test_qr_token_len(self) -> None:
        assert QR_TOKEN_LEN == 4


class TestTypeNames:
    def test_type_names_length(self) -> None:
        assert len(TYPE_NAMES) == 11

    def test_type_names_values(self) -> None:
        assert TYPE_NAMES["SW"] == "Switch"
        assert TYPE_NAMES["BT"] == "Button"


class TestTypeToDomain:
    def test_type_to_domain_length(self) -> None:
        assert len(TYPE_TO_DOMAIN) == 11

    def test_type_to_domain_matches_type_defs(self) -> None:
        for code, entry in TYPE_DEFS.items():
            assert TYPE_TO_DOMAIN[code] == entry["domain"]


class TestLoggerHierarchy:
    def test_logger_root(self) -> None:
        assert LOGGER_ROOT == "custom_components.rover"

    def test_logger_rns(self) -> None:
        assert LOGGER_RNS == "custom_components.rover.rns"

    def test_logger_reg(self) -> None:
        assert LOGGER_REG == "custom_components.rover.reg"

    def test_logger_trn(self) -> None:
        assert LOGGER_TRN == "custom_components.rover.trn"

    def test_logger_hab(self) -> None:
        assert LOGGER_HAB == "custom_components.rover.hab"

    def test_logger_hnd(self) -> None:
        assert LOGGER_HND == "custom_components.rover.hnd"


class TestStorage:
    def test_storage_key(self) -> None:
        assert STORAGE_KEY == "rover_registry"

    def test_storage_version(self) -> None:
        assert STORAGE_VERSION == 1


class TestAdditionalConstants:
    def test_pong_broadcast_interval(self) -> None:
        assert PONG_BROADCAST_INTERVAL_S == 8

    def test_watchdog_interval(self) -> None:
        assert WATCHDOG_INTERVAL_S == 30

    def test_await_path_timeout(self) -> None:
        assert AWAIT_PATH_TIMEOUT_S == 15

    def test_opportunistic_threshold(self) -> None:
        assert OPPORTUNISTIC_THRESHOLD_BYTES == 350

    def test_sensor_push_interval(self) -> None:
        assert SENSOR_PUSH_INTERVAL == 5.0

    def test_brightness_range(self) -> None:
        assert BRIGHTNESS_RANGE == (0, 100)

    def test_volume_range(self) -> None:
        assert VOLUME_RANGE == (0, 100)
