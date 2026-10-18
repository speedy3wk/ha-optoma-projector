"""Sensor platform for Optoma Projector."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, ClassVar

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import EntityCategory, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import POWER_STATES, VALUE_NOT_AVAILABLE
from .coordinator import OptomaConfigEntry, OptomaCoordinator
from .entity import OptomaEntity

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class OptomaSensorEntityDescription(SensorEntityDescription):
    """Describes Optoma hour sensor entity."""

    # Candidate keys in the projector response; key names differ across models
    state_keys: tuple[str, ...]


SENSOR_DESCRIPTIONS: tuple[OptomaSensorEntityDescription, ...] = (
    OptomaSensorEntityDescription(
        key="light_source_hours",
        translation_key="light_source_hours",
        state_keys=("n", "lamphrs", "lamp_hours", "laser_hours", "LampHrs"),
        native_unit_of_measurement=UnitOfTime.HOURS,
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    OptomaSensorEntityDescription(
        key="filter_hours",
        translation_key="filter_hours",
        state_keys=("F19", "filterhrs", "filter_hours", "FilterHrs"),
        native_unit_of_measurement=UnitOfTime.HOURS,
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: OptomaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Optoma sensors."""
    coordinator = entry.runtime_data
    entities: list[SensorEntity] = [
        OptomaLastUpdateSensor(coordinator),
        OptomaPowerStateSensor(coordinator),
    ]
    entities.extend(
        OptomaHoursSensor(coordinator, description)
        for description in SENSOR_DESCRIPTIONS
    )
    async_add_entities(entities)


class OptomaHoursSensor(OptomaEntity, SensorEntity):
    """Usage hours; unavailable if the projector does not report them."""

    entity_description: OptomaSensorEntityDescription

    def __init__(
        self,
        coordinator: OptomaCoordinator,
        description: OptomaSensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    def _raw_value(self) -> int | None:
        data = self.coordinator.data or {}
        for key in self.entity_description.state_keys:
            value = data.get(key)
            if value is None or value == VALUE_NOT_AVAILABLE:
                continue
            try:
                return int(float(value))
            except TypeError, ValueError:
                continue
        return None

    @property
    def available(self) -> bool:
        """Return True if the projector reports this value."""
        return super().available and self._raw_value() is not None

    @property
    def native_value(self) -> int | None:
        """Return the hours."""
        return self._raw_value()


class OptomaLastUpdateSensor(OptomaEntity, SensorEntity):
    """Timestamp of the last successful update."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator: OptomaCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, "last_update")

    @property
    def available(self) -> bool:
        """Stay available so the last success stays visible during outages."""
        return True

    @property
    def native_value(self) -> datetime | None:
        """Return the last successful update time."""
        return self.coordinator.last_update_success_time


class OptomaPowerStateSensor(OptomaEntity, SensorEntity):
    """Power state (standby, on, warming, cooling)."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options: ClassVar[list[str]] = list(POWER_STATES.values())

    def __init__(self, coordinator: OptomaCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, "power_state")

    @property
    def native_value(self) -> str | None:
        """Return the power state."""
        return self.coordinator.power_state

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        return {
            "is_warming": self.coordinator.is_warming,
            "is_cooling": self.coordinator.is_cooling,
            "can_accept_power_command": self.coordinator.can_accept_power_command,
        }
