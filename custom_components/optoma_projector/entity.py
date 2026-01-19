"""Base entity for Optoma Projector."""
from __future__ import annotations

from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import OptomaCoordinator


class OptomaEntity(CoordinatorEntity[OptomaCoordinator]):
    """Base class for Optoma entities."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: OptomaCoordinator,
        key: str,
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.host}_{key}"
        # Use translation_key for proper i18n (new pattern)
        self._attr_translation_key = key

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info."""
        # Get device info from coordinator (fetched from projector)
        device_data = self.coordinator.device_info_data
        mac = device_data.get("mac")
        serial = device_data.get("serial")

        # Build device info with proper typing
        return DeviceInfo(
            identifiers={(DOMAIN, self.coordinator.host)},
            name=self.coordinator.name,
            manufacturer="Optoma",
            model=device_data.get("model") or self.coordinator.model,
            sw_version=device_data.get("firmware") or self._get_firmware_from_data(),
            configuration_url=f"http://{self.coordinator.host}/index_login.asp",
            connections={(CONNECTION_NETWORK_MAC, mac)} if mac else set(),
            serial_number=serial if serial else None,
        )

    def _get_firmware_from_data(self) -> str | None:
        """Try to get firmware version from projector data."""
        if self.coordinator.data:
            # Common keys for firmware/version info
            for key in ("v", "ver", "version", "fw", "firmware"):
                if key in self.coordinator.data:
                    return str(self.coordinator.data[key])
        return None
