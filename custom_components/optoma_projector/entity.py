"""Base entity for Optoma Projector."""

from __future__ import annotations

from homeassistant.helpers.device_registry import (
    CONNECTION_NETWORK_MAC,
    DeviceInfo,
    format_mac,
)
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import OptomaCoordinator


class OptomaEntity(CoordinatorEntity[OptomaCoordinator]):
    """Base class for Optoma entities."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: OptomaCoordinator, key: str) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        entry_id = coordinator.config_entry.entry_id
        self._attr_unique_id = f"{entry_id}_{key}"
        self._attr_translation_key = key

        device_data = coordinator.device_info_data
        mac = device_data.get("mac")
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry_id)},
            name=coordinator.name,
            manufacturer="Optoma",
            model=device_data.get("model") or coordinator.model,
            sw_version=device_data.get("firmware"),
            serial_number=device_data.get("serial"),
            configuration_url=f"http://{coordinator.host}/index_login.asp",
            connections={(CONNECTION_NETWORK_MAC, format_mac(mac))} if mac else set(),
        )


class OptomaPoweredEntity(OptomaEntity):
    """Entity that is only available while the projector is on."""

    _state_key: str | None = None

    @property
    def available(self) -> bool:
        """Return True if the projector is on and the value is supported."""
        return (
            super().available
            and self.coordinator.is_on
            and (
                self._state_key is None
                or self.coordinator.is_key_available(self._state_key)
            )
        )
