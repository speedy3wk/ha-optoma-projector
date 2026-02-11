# Copilot instructions for HA Optoma Projector

## Big picture
- Home Assistant integration under custom_components/optoma_projector. All entities share a single OptomaCoordinator that owns IO, throttling, and polling.
- IO is HTTP POST to /form/control_cgi with Cookie: atop=1 and a non-standard JSON response (unquoted keys) parsed in OptomaCoordinator._parse_response.
- Power control has HTTP primary + Telnet fallback; transitions (warming/cooling) change polling cadence and block power commands when unsafe.

## Data flow + architecture
- Config flow validates connection via HTTP POST and creates a config entry (see custom_components/optoma_projector/config_flow.py).
- At setup (custom_components/optoma_projector/__init__.py), coordinator is stored in entry.runtime_data and platforms are forwarded.
- Entities are thin wrappers over coordinator data; availability often depends on projector power state and VALUE_NOT_AVAILABLE ("255").

## Project-specific patterns
- Entity metadata uses translation_key and a shared OptomaEntity base (custom_components/optoma_projector/entity.py). The main media player removes translation_key and uses device name.
- Select/Number/Button/Switch entities are generated from const lists (SELECTS, NUMBERS, BUTTONS, SWITCHES in custom_components/optoma_projector/const.py).
- Optimistic UI updates are used for power/source/volume and switches when the optimistic option is enabled.
- Limit concurrent platform updates with PARALLEL_UPDATES = 1 across entity platforms.

## Integration details to respect
- HTTP session is persistent and refreshed on login redirects; commands are throttled (MIN_COMMAND_INTERVAL) and serialized with an async lock.
- Polling interval adjusts dynamically: fast during warming/cooling, slow in standby, normal otherwise.
- Telnet fallback is optional and only for power commands; status mapping is in coordinator.

## Where to look for examples
- Coordinator behavior and IO: custom_components/optoma_projector/coordinator.py
- Entity base and device info mapping: custom_components/optoma_projector/entity.py
- Entity generation patterns: custom_components/optoma_projector/select.py, number.py, button.py, switch.py
- Config flow + options: custom_components/optoma_projector/config_flow.py
- Diagnostics redaction: custom_components/optoma_projector/diagnostics.py

## Developer workflow hints
- This is a Home Assistant custom integration; no local build/test commands are defined in repo. Validate changes by running HA with the integration loaded.
- For supported models and protocol notes, see README.md.
