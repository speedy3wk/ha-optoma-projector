# Changelog

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
