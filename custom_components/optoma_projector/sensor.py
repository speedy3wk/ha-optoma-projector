"""Sensor platform for Optoma Projector."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import EntityCategory, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import OptomaConfigEntry
from .const import KEY_POWER, POWER_STATES, VALUE_NOT_AVAILABLE
from .coordinator import OptomaCoordinator
from .entity import OptomaEntity

# Limit concurrent platform updates (projector can only handle one request at a time)
PARALLEL_UPDATES = 1


@dataclass(frozen=True, kw_only=True)
class OptomaSensorEntityDescription(SensorEntityDescription):
    """Describes Optoma sensor entity."""

    state_key: str | None = None
    # Alternative keys to check if primary key is not found
    fallback_keys: tuple[str, ...] = ()


SENSOR_DESCRIPTIONS: tuple[OptomaSensorEntityDescription, ...] = (
    OptomaSensorEntityDescription(
        key="light_source_hours",
        translation_key="light_source_hours",
        # Common keys for lamp/laser hours across different Optoma models
        state_key="n",
        fallback_keys=("lamphrs", "lamp_hours", "laser_hours", "LampHrs"),
        native_unit_of_measurement=UnitOfTime.HOURS,
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:lightbulb-on-outline",
    ),
    OptomaSensorEntityDescription(
        key="filter_hours",
        translation_key="filter_hours",
        state_key="F19",
        fallback_keys=("filterhrs", "filter_hours", "FilterHrs"),
        native_unit_of_measurement=UnitOfTime.HOURS,
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:air-filter",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: OptomaConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Optoma sensors."""
    coordinator = entry.runtime_data

    entities: list[SensorEntity] = [
        OptomaLastUpdateSensor(coordinator),
        OptomaPowerStateSensor(coordinator),
    ]

    entities.extend(
        OptomaSensor(coordinator, description) for description in SENSOR_DESCRIPTIONS
    )

    async_add_entities(entities)


class OptomaSensor(OptomaEntity, SensorEntity):
    """Sensor entity for Optoma projector."""

    entity_description: OptomaSensorEntityDescription

    def __init__(
        self,
        coordinator: OptomaCoordinator,
        description: OptomaSensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> float | str | None:
        """Return the sensor value."""
        if not self.coordinator.data:
            return None

        # Try primary key first
        if self.entity_description.state_key:
            value = self.coordinator.data.get(self.entity_description.state_key)
            if value is not None:
                return self._convert_value(value)

        # Try fallback keys
        for key in self.entity_description.fallback_keys:
            value = self.coordinator.data.get(key)
            if value is not None:
                return self._convert_value(value)

        return None

    def _convert_value(self, value: str) -> float | str | None:
        """Convert value to appropriate type."""
        # 255 means "not available" for this projector
        if value == VALUE_NOT_AVAILABLE:
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return str(value)


class OptomaLastUpdateSensor(OptomaEntity, SensorEntity):
    """Last update timestamp sensor."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_translation_key = "last_update"

    def __init__(self, coordinator: OptomaCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, "last_update")

    @property
    def native_value(self) -> datetime | None:
        """Return the last update time."""
        # last_update_success_time may not exist in older HA versions
        return getattr(self.coordinator, "last_update_success_time", None)


class OptomaPowerStateSensor(OptomaEntity, SensorEntity):
    """Power state sensor showing human-readable power status."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_translation_key = "power_state"
    _attr_icon = "mdi:power"

    def __init__(self, coordinator: OptomaCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, "power_state")

    @property
    def native_value(self) -> str:
        """Return the power state."""
        if not self.coordinator.data:
            return "unknown"

        power_value = self.coordinator.data.get(KEY_POWER)
        return POWER_STATES.get(power_value, "unknown")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        return {
            "is_warming": self.coordinator.is_warming,
            "is_cooling": self.coordinator.is_cooling,
            "can_accept_power_command": self.coordinator.can_accept_power_command,
        }
