"""Optoma Projector Integration for Home Assistant."""
from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_SCAN_INTERVAL, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

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
