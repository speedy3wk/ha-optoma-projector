# Changelog

## 0.2.0
Requires Home Assistant 2026.10 or newer.

Fixes:
- Toggles (switches, mute) are no longer sent twice after a timeout; only idempotent requests are retried.
- Repeated switch/mute calls before the projector confirmed the new state no longer toggle the feature back.
- With Telnet fallback enabled, a single failed HTTP poll no longer makes all setting entities unavailable.
- Toggle responses (which show the state *before* the toggle) are no longer applied, so switches don't flip back briefly.
- The request lock timeout no longer cuts off slow power commands.
- Single failed polls no longer make all entities unavailable; the device is marked unavailable after 3 consecutive failures.
- Hour sensors without data from the projector are now unavailable instead of showing `0`.
- Telnet response parsing is stricter (no false "success" on unrelated output).
- Changing the IP address via reconfigure now updates the entry's unique ID and prevents duplicates.

Changes:
- Entity unique IDs and the device identifier are now based on the config entry instead of the IP address (migrated automatically; entity IDs stay the same).
- Telnet fallback now also reads the power state when the web interface does not answer (deep standby).
- Failed commands raise translated error messages; power commands during warming/cooling show a clear validation error.
- The config flow detects projectors with the newer HTTPS web interface (port 8088) and reports them as unsupported.
- The "Last update" sensor is disabled by default; the power state sensor is now an enum sensor.
- The HTTP session is managed by Home Assistant; a state refresh runs ~1 s after every command.
- Media player uses Home Assistant's built-in volume step (5 %).
- Added diagnostics fields (power state, failure counter, Telnet fallback, last successful update).
- Added a test suite (pytest) and ruff linting in CI.

## 0.1.3
- Fix optimistic UI rollback for power and toggle entities to avoid stale temporary state after failed/blocked commands.
- Use shared power state constants for optimistic power updates.
- Improve unload robustness by shutting down coordinator only after platforms unload successfully.

## 0.1.2
- Home Assistant 2026.2 compatibility: migrate any existing invalid `entity_id`s (e.g., containing dashes) to the new restricted format (lowercase letters, numbers, underscores only). This may require updating automations that referenced the old entity IDs.

## 0.1.1
- Metadata update for HACS release.

## 0.1.0
- Initial public release.
