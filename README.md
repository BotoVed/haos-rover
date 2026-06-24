<<<<<<< HEAD
# Rover — Remote Over Radio for Home Assistant

**Version 0.0.2** — Core Protocol Foundations

Rover is a [Home Assistant](https://www.home-assistant.io) custom component that extends smart home control across [Reticulum](https://reticulum.network) mesh networks. It enables secure, decentralized control of Home Assistant devices from remote locations without relying on cloud infrastructure, internet connectivity, or centralized servers.

Using Reticulum's encrypted mesh networking and LXMF messaging, Rover pairs with a mobile companion app to provide remote control of switches, lights, covers, climate systems, locks, media players, sensors, fans, and more — all over peer-to-peer radio links.

## Features

- **Mesh-Native Control** — Control HA devices over Reticulum mesh networks using encrypted LXMF messaging
- **11 Device Types** — Switch, Light, Cover, Climate, Lock, Media Player, Scene, Alarm Panel, Sensor, Fan, and Button
- **Compact Wire Protocol** — msgpack-encoded messages with integer-keyed fields for minimal bandwidth usage
- **Secure Identity** — Identity-hash-based authentication with QR token pairing and role-based access (owner/regular)
- **Persistent Registry** — HA Store-backed CRUD for users, devices, areas, and pending remote approvals
- **State Synchronization** — Extracts HA entity state into compact protocol format for push updates
- **Section Hash Tracking** — MD5-based section hashes for efficient sync and change detection
- **Offline-First** — Designed for intermittent mesh connectivity with opportunistic transmission and watchdog recovery

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                   Home Assistant                        │
│  ┌───────────────────────────────────────────────────┐  │
│  │               Rover Integration                   │  │
│  │  ┌──────────┐  ┌───────────────┐  ┌───────────────────┐  │  │
│  │  │  Codec   │  │  Command      │  │  State Extractor  │  │  │
│  │  │ (msgpack)│  │  Builder      │  │  (HA→Protocol)    │  │  │
│  │  └──────────┘  └───────────────┘  └───────────────────┘  │  │
│  │  ┌───────────────────────────────────────────────────┐  │  │
│  │  │               Registry (HA Store)                 │  │  │
│  │  │       Meta · Users · Areas · Devices · Pending   │  │  │
│  │  └───────────────────────────────────────────────────┘  │  │
│  │  ┌─────────────────┐  ┌──────────────┐  ┌────────────┐  │  │
│  │  │   Transport     │  │  Dispatcher  │  │  Handlers  │  │  │
│  │  │  (RNS/LXMF)     │  │  (Routing)   │  │ (CMD/PING/ │  │  │
│  │  │                 │  │              │  │ REQ/REG)   │  │  │
│  │  └─────────────────┘  └──────────────┘  └────────────┘  │  │
│  └───────────────────────────────────────────────────┘  │
│                   │ LXMF over Reticulum                  │
│                   ▼                                      │
│            ┌──────────────┐                              │
│            │ Mesh Network │                              │
│            │ (Radio/TCP)  │                              │
│            └──────────────┘                              │
└─────────────────────────────────────────────────────────┘
```

## Protocol

Rover defines a compact wire protocol with 8 message types:

| Code | Message   | Purpose                     |
|------|-----------|-----------------------------|
| 2    | STATUS    | Device state report         |
| 3    | PUSH      | State update push           |
| 4    | CONFIG    | Configuration exchange      |
| 5    | CMD       | Device command              |
| 6    | PING_PONG | Keepalive / path discovery  |
| 7    | FORBIDDEN | Access denied               |
| 8    | REQ       | Data request                |
| 9    | REGISTER  | Remote registration         |

### Device Types

| Code | Domain             | Name         |
|------|--------------------|--------------|
| SW   | switch             | Switch       |
| LT   | light              | Light        |
| CV   | cover              | Cover        |
| CL   | climate            | Climate      |
| LK   | lock               | Lock         |
| MS   | media_player       | Media Player |
| SC   | scene              | Scene        |
| AL   | alarm_control_panel| Alarm Panel  |
| SE   | sensor             | Sensor       |
| FN   | fan                | Fan          |
| BT   | button             | Button       |

## Installation

### Via HACS (recommended)

1. Ensure [HACS](https://hacs.xyz) is installed in your Home Assistant instance
2. Add this repository as a custom repository in HACS:
   - URL: `https://github.com/BotoVed/haos-rover`
   - Category: Integration
3. Search for "Rover" in HACS and install
4. Restart Home Assistant

### Manual

1. Copy the `custom_components/rover/` directory to your Home Assistant `custom_components/` directory
2. Restart Home Assistant

## Configuration

Rover is configured entirely through the Home Assistant UI (Config Flow):

1. Go to **Settings → Devices & Services → Add Integration**
2. Search for "Rover"
3. Follow the setup wizard to configure your Reticulum identity and network settings

> **Note:** Reticulum (`rns>=1.3.0`) and LXMF (`lxmf>=0.9.6`) must be installed in your Home Assistant Python environment. These dependencies are declared in the integration manifest.

## Development Setup

### Prerequisites

- Python 3.12+
- Home Assistant 2024.12+ (for integration testing)

### Getting Started

```bash
# Clone the repository
git clone https://github.com/BotoVed/haos-rover.git
cd haos-rover

# Create a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install with dev dependencies
pip install -e ".[dev]"

# Run tests
pytest
```

### Project Structure

```
custom_components/rover/
├── __init__.py          # Integration setup, RoverRuntimeData
├── manifest.json        # HA integration manifest
├── const.py             # All protocol constants, device type definitions
├── codec.py             # msgpack encode/decode for wire format
├── registry.py          # HA Store-backed persistent CRUD registry
├── commands.py          # CMD → HA service call builder (11 device types)
├── state_extractor.py   # HA entity state → protocol format extraction
├── rns_transport.py     # RNS/LXMF transport (identity, send, shutdown)
├── dispatcher.py        # Message routing by type with wire key normalization
└── handlers.py          # Protocol handlers (CMD, PING, REQ, REGISTER)
```

### Completed Modules

#### Phase 1 — Core Protocol

- **const.py** — All protocol constants: 8 message types, 11 device type definitions, identity/section hash lengths, role permissions, push throttling, QR token format, logger hierarchy, storage keys, and operational timing constants
- **codec.py** — `encode(fields)` / `decode(data)` using msgpack with `use_bin_type=True` for compact wire encoding
- **registry.py** — `RoverRegistry` with HA `Store` persistence, supporting 5 protocol sections (meta, users, areas, devices, pending), section hash computation (canonical JSON → MD5 → 4-char hex), QR token authentication, role enforcement (owner/regular), and mutation callbacks for change propagation
- **commands.py** — `build_service_call(device_type, cmd_fields)` producing `list[tuple[domain, service, service_data]]` for all 11 device types: SW (on/off), LT (brightness/color_temp/rgb/effect), CV (open/close/stop/position/tilt), CL (hvac/temperature/fan/preset/swing), LK (lock/unlock), MS (play/pause/stop/next/prev/volume/mute/seek), SC (turn_on), AL (arm_home/arm_away/arm_night/disarm), SE (read-only), FN (on/off/percentage/preset/oscillate/direction), BT (press)
- **state_extractor.py** — `extract_state(state, attributes, device_type)` converting HA entity states to compact protocol format with per-device-type field mappings

#### Phase 2 — Reticulum Transport & Message Handling

- **rns_transport.py** — `RoverTransport`: Identity loading/creation from HA config directory, LXMF router initialization with delivery identity registration, bimodal `send()` (opportunistic for ≤350 B, direct for larger payloads), incoming message callback dispatch, periodic path announces every 300 s, and graceful `shutdown()` lifecycle
- **dispatcher.py** — `RoverDispatcher`: Normalizes wire integer keys to human-readable string keys via per-type `_TP_MAPS` (STATUS, PUSH, CONFIG, CMD, PING/PONG, FORBIDDEN, REQ, REGISTER). Routes inbound messages to registered handler callbacks by `tp` value, with a fallback default handler for unknown types
- **handlers.py** — `RoverHandlers`: Registers four protocol handlers with the dispatcher. `_handle_cmd` — authorizes sender via registry, builds and executes HA service calls. `_handle_ping` — compares client section hashes against registry, returns PONG with diff sections and STATUS. `_handle_req` — returns requested config sections and STATUS. `_handle_register` — validates QR token, approves remote identity, returns full CONFIG and STATUS

### Upcoming Phases

- **Phase 3:** Config flow — UI-based setup wizard, QR code pairing, device and area management panels
- **Phase 4:** Bridge service — LXMF ↔ HA bridge, connection pool, PUSH broadcast scheduling, opportunistic transmission, watchdog recovery

## Testing

Rover uses pytest with async support. The test suite includes stubs for Home Assistant internals, RNS, LXMF, and voluptuous, so tests run without requiring a real HA instance.

```bash
# Run all tests (300+ tests)
pytest

# Run with coverage
pytest --cov=custom_components.rover

# Run specific test file
pytest tests/test_commands.py -v
```

Test modules:
- `test_codec.py` — msgpack roundtrip and edge cases
- `test_const.py` — all constant values, type definitions, mappings
- `test_commands.py` — service call builder for all 11 device types
- `test_state_extractor.py` — state extraction for all device types
- `test_registry.py` — CRUD operations, hash computation, QR tokens, callbacks, persistence
- `test_rns_transport.py` — transport lifecycle, identity loading, send/encode
- `test_dispatcher.py` — wire key normalization, handler registration, dispatch routing
- `test_handlers.py` — CMD authorization, PING diff comparison, REQ config serving, REGISTER flow
- `test_init.py` — version, `RoverRuntimeData`, setup/unload stubs, manifest validation

## Performance

Rover is designed for low-bandwidth mesh networks:

- **Wire format overhead:** msgpack with integer-keyed field mapping minimizes message size
- **Opportunistic threshold:** Messages under 350 bytes are sent immediately on available paths
- **Push throttle:** State updates are throttled to 500ms intervals to prevent message storms
- **Pong broadcast:** 8-second keepalive interval for path maintenance
- **Watchdog:** 30-second connection health monitoring

## Security

- **Identity-based auth:** Remote identities are verified by cryptographic hash
- **QR token pairing:** One-time tokens for secure initial enrollment
- **Role-based access:** Owner (first user) and regular user roles
- **Configurable limits:** Maximum 5 active remotes, 10 pending approvals
- **Section hashing:** Tamper-evident section hashes for data integrity

## License

MIT

## Disclaimer

Rover is in early development (v0.0.2). The core protocol foundations, Reticulum transport, and message handler layers are complete. The config flow UI and bridge service are under active development. Expect breaking changes before v1.0.0.
=======
# HaOS-Rover

Home Assistant OS Rover — [опишите проект здесь]

## Статус

Проект в начальной стадии.
>>>>>>> e50fcc83bb6a9450762f5e02ae208c9a0932ef1e
