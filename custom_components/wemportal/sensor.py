"""
Sensor platform for wemportal component
"""

from homeassistant.components.sensor import (
    SensorEntity,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import _LOGGER, DOMAIN
from . import get_wemportal_unique_id


async def async_setup_platform(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
    discovery_info=None,
):
    """Setup the Wem Portal sensor."""

    coordinator = hass.data[DOMAIN]["coordinator"]
    entities: list[WemPortalSensor] = []
    for device_id, entity_data in coordinator.data.items():
        for unique_id, values in entity_data.items():
            if isinstance(values, int):
                continue
            if values["platform"] == "sensor":
                entities.append(
                    WemPortalSensor(
                        coordinator, config_entry, device_id, unique_id, values
                    )
                )

    async_add_entities(entities)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Sensor entry setup."""

    coordinator = hass.data[DOMAIN][config_entry.entry_id]["coordinator"]
    entities: list[WemPortalSensor] = []
    for device_id, entity_data in coordinator.data.items():
        for unique_id, values in entity_data.items():
            if isinstance(values, int):
                continue
            if values["platform"] == "sensor":
                entities.append(
                    WemPortalSensor(
                        coordinator, config_entry, device_id, unique_id, values
                    )
                )
    async_add_entities(entities)


class WemPortalSensor(CoordinatorEntity, SensorEntity):
    """Representation of a WEM Portal Sensor."""

    def __init__(
        self, coordinator, config_entry: ConfigEntry, device_id, _unique_id, entity_data
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._last_updated = None
        self._config_entry = config_entry
        self._device_id = device_id
        self._attr_name = _unique_id
        self._attr_unique_id = get_wemportal_unique_id(
            self._config_entry.entry_id, str(self._device_id), str(self._attr_name)
        )
        self._parameter_id = entity_data["ParameterID"]
        self._attr_icon = entity_data["icon"]
        self._attr_native_unit_of_measurement = entity_data["unit"]
        self._attr_native_value = entity_data["value"]
        self._attr_should_poll = False

    @property
    def device_info(self) -> DeviceInfo:
        """Get device information."""
        return {
            "identifiers": {
                (DOMAIN, f"{self._config_entry.entry_id}:{str(self._device_id)}")
            },
            "via_device": (DOMAIN, self._config_entry.entry_id),
            "name": str(self._device_id),
            "manufacturer": "Weishaupt",
        }

    @property
    def available(self):
        """Return if entity is available."""
        return self.coordinator.last_update_success

    # async def async_added_to_hass(self):
    #     """When entity is added to hass."""
    #     self.async_on_remove(
    #         self.coordinator.async_add_listener(self._handle_coordinator_update)
    #     )

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""

        try:
            self._attr_native_value = self.coordinator.data[self._device_id][
                self._attr_name
            ]["value"]
        except KeyError:
            self._attr_native_value = None
            _LOGGER.warning("Can't find %s", self._attr_unique_id)
            _LOGGER.debug("Sensor data %s", self.coordinator.data)

        self.async_write_ha_state()

    @property
    def device_class(self):
        """Return the device_class of this entity."""
        if self._attr_native_unit_of_measurement == "°C":
            return SensorDeviceClass.TEMPERATURE
        elif self._attr_native_unit_of_measurement in ("kWh", "Wh"):
            return SensorDeviceClass.ENERGY
        elif self._attr_native_unit_of_measurement in ("kW", "W"):
            return SensorDeviceClass.POWER
        elif self._attr_native_unit_of_measurement == "%":
            return SensorDeviceClass.POWER_FACTOR
        else:
            return None

    @property
    def state_class(self):
        """Return the state class of this entity, if any."""
        if self._attr_native_unit_of_measurement in ("°C", "kW", "W", "%"):
            return SensorStateClass.MEASUREMENT
        elif self._attr_native_unit_of_measurement in ("kWh", "Wh"):
            return SensorStateClass.TOTAL_INCREASING
        else:
            return None

    @property
    def extra_state_attributes(self):
        """Return the state attributes of this device."""
        attr = {}
        if self._last_updated is not None:
            attr["Last Updated"] = self._last_updated
        return attr

    async def async_update(self):
        """Update Entity
        Only used by the generic entity update service."""
        await self.coordinator.async_request_refresh()
