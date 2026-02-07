"""Optoma Projector Integration for Home Assistant."""
from __future__ import annotations

import logging
import re
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_SCAN_INTERVAL, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import entity_registry as er
from homeassistant.util import slugify

from .const import (
    CONF_MODEL,
    CONF_OPTIMISTIC,
    CONF_PROJECTOR_ID,
    CONF_TELNET_FALLBACK,
    DEFAULT_MODEL,
    DEFAULT_NAME,
    DEFAULT_OPTIMISTIC,
    DEFAULT_PROJECTOR_ID,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_TELNET_FALLBACK,
    DOMAIN,
)
from .coordinator import OptomaCoordinator

_LOGGER = logging.getLogger(__name__)

_VALID_OBJECT_ID = re.compile(r"^[a-z0-9_]+$")


def _sanitize_object_id(object_id: str) -> str:
    """Return an entity_id-safe object_id.

    Home Assistant 2026.2 tightened the object_id restrictions to only allow
    lowercase letters, numbers and underscores.
    """

    # Prefer HA's slugify with underscore separator when available.
    try:
        sanitized = slugify(object_id, separator="_")
    except TypeError:
        sanitized = slugify(object_id)

    sanitized = (sanitized or "entity").lower().replace("-", "_")
    sanitized = re.sub(r"[^a-z0-9_]", "_", sanitized)
    sanitized = re.sub(r"_+", "_", sanitized).strip("_")
    return sanitized or "entity"


async def _async_migrate_invalid_entity_ids(
    hass: HomeAssistant, entry: ConfigEntry
) -> None:
    """Migrate invalid entity_ids in the entity registry for this config entry."""

    registry = er.async_get(hass)
    reg_entries = er.async_entries_for_config_entry(registry, entry.entry_id)
    if not reg_entries:
        return

    for reg_entry in reg_entries:
        # Entity_id is always in the form <domain>.<object_id>
        try:
            entity_domain, object_id = reg_entry.entity_id.split(".", 1)
        except ValueError:
            continue

        if _VALID_OBJECT_ID.fullmatch(object_id):
            continue

        new_object_id = _sanitize_object_id(object_id)
        new_entity_id = f"{entity_domain}.{new_object_id}"

        # Disambiguate collisions by appending _2, _3, ...
        if new_entity_id != reg_entry.entity_id:
            suffix = 2
            while (
                new_entity_id in registry.entities
                and new_entity_id != reg_entry.entity_id
            ):
                new_entity_id = f"{entity_domain}.{new_object_id}_{suffix}"
                suffix += 1

        if new_entity_id == reg_entry.entity_id:
            continue

        _LOGGER.warning(
            "Renaming invalid entity_id %s -> %s (HA 2026.2 compatibility)",
            reg_entry.entity_id,
            new_entity_id,
        )
        registry.async_update_entity(reg_entry.entity_id, new_entity_id=new_entity_id)

PLATFORMS: list[Platform] = [
    Platform.MEDIA_PLAYER,
    Platform.SWITCH,
    Platform.SELECT,
    Platform.NUMBER,
    Platform.BUTTON,
    Platform.SENSOR,
]

# Type alias for config entry with runtime data
type OptomaConfigEntry = ConfigEntry[OptomaCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: OptomaConfigEntry) -> bool:
    """Set up Optoma Projector from a config entry."""
    # HA 2026.2 disallows entity_ids containing anything other than
    # lowercase letters, numbers and underscores in the object_id.
    # Migrate any existing invalid IDs before entities are set up.
    await _async_migrate_invalid_entity_ids(hass, entry)

    # Get options (allows changing without reconfiguring)
    scan_interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    optimistic = entry.options.get(CONF_OPTIMISTIC, DEFAULT_OPTIMISTIC)
    telnet_fallback = entry.options.get(CONF_TELNET_FALLBACK, DEFAULT_TELNET_FALLBACK)
    projector_id = entry.options.get(CONF_PROJECTOR_ID, DEFAULT_PROJECTOR_ID)

    coordinator = OptomaCoordinator(
        hass,
        config_entry=entry,
        host=entry.data[CONF_HOST],
        name=entry.data.get(CONF_NAME, DEFAULT_NAME),
        model=entry.data.get(CONF_MODEL, DEFAULT_MODEL),
        scan_interval=timedelta(seconds=scan_interval),
        optimistic=optimistic,
        telnet_fallback=telnet_fallback,
        projector_id=int(projector_id),
    )

    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception as err:
        # Clean up coordinator resources on failure
        await coordinator.async_shutdown()
        raise ConfigEntryNotReady(
            f"Could not connect to projector at {entry.data[CONF_HOST]}: {err}"
        ) from err

    # Store coordinator in runtime_data (new pattern, avoids hass.data pollution)
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Note: OptionsFlowWithReload handles reload automatically, no listener needed

    return True


async def async_unload_entry(hass: HomeAssistant, entry: OptomaConfigEntry) -> bool:
    """Unload a config entry."""
    # Shutdown the coordinator to close HTTP session
    coordinator: OptomaCoordinator = entry.runtime_data
    await coordinator.async_shutdown()
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
