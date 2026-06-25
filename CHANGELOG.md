# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- GPL v3 LICENSE file (D10).
- 9 round-trip wire-format tests for D1 flat key space.
- 30 out-key-map tests verifying all 77 keys in `_OUT_KEY_MAP`.
- Test for `approve_pending` enforcing `MAX_ACTIVE_REMOTES` limit.
- Test for `active_limit_exceeded` reason in FORBIDDEN response.
- Test for QR payload format matching spec v0.5.0 §4.2.

### Changed
- Wire-format (D1): flat key space 0-76 — all 77 keys in `_OUT_KEY_MAP`; `_TP_MAPS` aligned; `_normalize` uses integer keys.
- QR payload format (D3): wrapped in `rvr{}` with 6 fields — `fmt`, `dst`, `nm`, `pk`, `tcp`, `uid` (spec v0.5.0 §4.2).
- `MAX_ACTIVE_REMOTES=5` enforcement (D4): `approve_pending` rejects exceeding limit; FORBIDDEN sent with `reason='active_limit_exceeded'`.
- Climate field collision resolved (D5): `target=t`, `current=tc`, `target_low=tg`.
- Spec updated to v0.5.0 (D8) with D2/D5/D6 notes.
- README cleanup (D9): removed version number, BS compatibility row, broken SPEC.md links.

### Fixed
- Three test_init.py regressions introduced in v0.2.7.
- Broken SPEC.md links in README.

### Removed
- Version number from README heading.
- BS (backward-compatibility) compatibility row from README.

## [0.2.7] - 2026-06-25

### Changed
- Module-level LXMF singleton to survive HA integration reload.

## [0.2.6] - 2026-06-25

### Fixed
- Transport reload crash.
- `brightness=None` crash in light commands.

## [0.2.5] - 2026-06-25

### Fixed
- `__version__` inconsistency for release alignment.
- RNS transport destination collision on integration reload.

## [0.2.4] - 2026-06-25

### Changed
- Clean RNS stop+restart on integration reload.

## [0.2.3] - 2026-06-25

### Fixed
- `signal.signal` called in executor thread — monkey-patched to prevent RuntimeError.

## [0.2.2] - 2026-06-24

### Fixed
- RNS config format — migrated from JSON to INI format.
- Added singleton guard to prevent multiple RNS initializations.

## [0.2.1] - 2026-06-24

### Fixed
- Transport blocking HA event loop — moved RNS/LXMF operations to executor thread.

## [0.2.0] - 2026-06-24

### Added
- Configuration UI: config flow with single-instance setup.
- Options flow: multi-step menu (general/network/devices/remove/test/users/pending/config).
- QR code generation for remote registration.

## [0.1.0] - 2026-06-24

### Added
- HA Bridge: `state_changed` → PUSH with throttle, PONG broadcast.
- Full integration wiring: `RoverRuntimeData`, lifecycle, debug services.

## [0.0.2] - 2026-06-24

### Added
- Core protocol modules: `const.py`, `codec.py`, `registry.py`, `commands.py`, `state_extractor.py`.
- Reticulum/LXMF transport: identity lifecycle, bimodal delivery (OPPORTUNISTIC/DIRECT).
- Message dispatcher: route by type (CMD, PING, REQ, REGISTER).
- Message handlers: CMD, PING, REQ, REGISTER, FORBIDDEN.
- Initial test suite with mock fixtures.
