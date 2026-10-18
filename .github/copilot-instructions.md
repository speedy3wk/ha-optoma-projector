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
- Optimistic UI updates are handled centrally in the coordinator (async_set_value, async_toggle, async_power_on/off) when the optimistic option is enabled; failures roll back and raise translated HomeAssistantError.
- Toggles are never retried on connection errors and their (pre-toggle) responses are ignored; a follow-up refresh reads the new state. Idempotency (skip if already in target state, incl. unconfirmed pending toggles) lives in OptomaCoordinator.async_toggle.
- Entities that need the projector to be on derive from OptomaPoweredEntity (entity.py).
- Unique IDs are `<entry_id>_<key>`; the device identifier is (DOMAIN, entry_id).
- PARALLEL_UPDATES = 1 for platforms that send commands; 0 for read-only sensors.

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
- Lint: `.venv/bin/ruff check custom_components tests` and `.venv/bin/ruff format custom_components tests`.
- Tests: `.venv/bin/pytest` (pytest-homeassistant-custom-component, see requirements_test.txt; Python 3.14). tests/conftest.py contains a FakeProjector emulating the CGI.
- For supported models and protocol notes, see README.md.
