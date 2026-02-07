# Changelog

## 0.1.2
- Home Assistant 2026.2 compatibility: migrate any existing invalid `entity_id`s (e.g., containing dashes) to the new restricted format (lowercase letters, numbers, underscores only). This may require updating automations that referenced the old entity IDs.

## 0.1.1
- Metadata update for HACS release.

## 0.1.0
- Initial public release.
