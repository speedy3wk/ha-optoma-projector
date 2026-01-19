"""Diagnostics support for Optoma Projector."""
from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant

from . import OptomaConfigEntry

# Keys to redact from diagnostics output
TO_REDACT = {CONF_HOST, "mac", "serial", "sn", "macaddr", "MAC"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: OptomaConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data

    return {
        "entry_data": async_redact_data(dict(entry.data), TO_REDACT),
        "entry_options": dict(entry.options),
        "coordinator": {
            "last_update_success": coordinator.last_update_success,
            "update_interval": str(coordinator.update_interval),
            "optimistic_mode": coordinator.optimistic,
        },
        "device_info": async_redact_data(coordinator.device_info_data, TO_REDACT),
        "projector_data": async_redact_data(coordinator.data or {}, TO_REDACT),
        "is_on": coordinator.is_on,
    }
