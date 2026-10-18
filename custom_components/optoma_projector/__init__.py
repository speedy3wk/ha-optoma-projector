"""Optoma Projector Integration for Home Assistant."""

from __future__ import annotations

from datetime import timedelta
import logging
import re

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_SCAN_INTERVAL, Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.util import slugify

from .const import (
    BUTTONS,
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
    NUMBERS,
    SELECTS,
    SWITCHES,
)
from .coordinator import OptomaConfigEntry, OptomaCoordinator

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
    hass: HomeAssistant, entry: OptomaConfigEntry
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

# Entity keys used as unique_id suffix ("<host>_<key>" before 1.2, "<entry_id>_<key>" since)
_ENTITY_KEYS: frozenset[str] = frozenset(
    {
        "media_player",
        "power",
        "power_state",
        "last_update",
        "light_source_hours",
        "filter_hours",
        *(item[0] for item in SWITCHES),
        *(item[0] for item in SELECTS),
        *(item[0] for item in NUMBERS),
        *(item[0] for item in BUTTONS),
    }
)

__all__ = ["OptomaConfigEntry"]


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate old config entries."""
    if entry.version > 1:
        return False

    if entry.minor_version < 2:
        # Unique IDs were based on the host (IP), which changes on reconfigure.
        _migrate_unique_ids_to_entry_id(hass, entry)
        hass.config_entries.async_update_entry(entry, minor_version=2)
        _LOGGER.debug("Migrated %s to version 1.2", entry.title)

    return True


def _migrate_unique_ids_to_entry_id(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Rewrite '<host>_<key>' unique IDs and the device identifier to the entry ID."""
    ent_reg = er.async_get(hass)
    prefix = f"{entry.entry_id}_"
    taken = {
        (reg.domain, reg.unique_id)
        for reg in er.async_entries_for_config_entry(ent_reg, entry.entry_id)
        if reg.unique_id.startswith(prefix)
    }

    @callback
    def _update(reg_entry: er.RegistryEntry) -> dict[str, str] | None:
        if reg_entry.unique_id.startswith(prefix):
            return None
        keys = [k for k in _ENTITY_KEYS if reg_entry.unique_id.endswith(f"_{k}")]
        if not keys:
            return None
        new_unique_id = f"{prefix}{max(keys, key=len)}"
        if (reg_entry.domain, new_unique_id) in taken:
            # Leftover from an earlier host; keep as orphan rather than collide.
            return None
        taken.add((reg_entry.domain, new_unique_id))
        return {"new_unique_id": new_unique_id}

    for reg_entry in er.async_entries_for_config_entry(ent_reg, entry.entry_id):
        if changes := _update(reg_entry):
            ent_reg.async_update_entity(reg_entry.entity_id, **changes)

    dev_reg = dr.async_get(hass)
    new_identifier = (DOMAIN, entry.entry_id)
    devices = dr.async_entries_for_config_entry(dev_reg, entry.entry_id)
    if any(new_identifier in device.identifiers for device in devices):
        return
    for device in devices:
        if any(domain == DOMAIN for domain, _ in device.identifiers):
            dev_reg.async_update_device(device.id, new_identifiers={new_identifier})
            break


async def async_setup_entry(hass: HomeAssistant, entry: OptomaConfigEntry) -> bool:
    """Set up Optoma Projector from a config entry."""
    # HA 2026.2 disallows entity_ids containing anything other than
    # lowercase letters, numbers and underscores in the object_id.
    await _async_migrate_invalid_entity_ids(hass, entry)

    coordinator = OptomaCoordinator(
        hass,
        config_entry=entry,
        host=entry.data[CONF_HOST],
        name=entry.data.get(CONF_NAME, DEFAULT_NAME),
        model=entry.data.get(CONF_MODEL, DEFAULT_MODEL),
        scan_interval=timedelta(
            seconds=entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        ),
        optimistic=entry.options.get(CONF_OPTIMISTIC, DEFAULT_OPTIMISTIC),
        telnet_fallback=entry.options.get(
            CONF_TELNET_FALLBACK, DEFAULT_TELNET_FALLBACK
        ),
        projector_id=int(entry.options.get(CONF_PROJECTOR_ID, DEFAULT_PROJECTOR_ID)),
    )
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: OptomaConfigEntry) -> bool:
    """Unload a config entry (coordinator shutdown is registered automatically)."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
