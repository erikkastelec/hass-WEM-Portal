"""
Sensor platform for wemportal component
"""

from homeassistant.components.sensor import (
    SensorEntity,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry

from homeassistant.core import HomeAssistant
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
            if values["platform"] == "sensor":
                entities.append(
                    WemPortalSensor(
                        coordinator, config_entry, device_id, unique_id, values
                    )
                )
    try:
        async_add_entities(entities)
    except Exception as e:
        print(e)


class WemPortalSensor(CoordinatorEntity, SensorEntity):
    """Representation of a WEM Portal Sensor."""

    def __init__(
        self, coordinator, config_entry: ConfigEntry, device_id, _unique_id, entity_data
    ):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._last_updated = None
        self._config_entry = config_entry
        self._device_id = device_id
        self._name = _unique_id
        self._unique_id = get_wemportal_unique_id(
            self._config_entry.entry_id, str(self._device_id), str(self._name)
        )
        self._parameter_id = entity_data["ParameterID"]
        self._icon = entity_data["icon"]
        self._unit = entity_data["unit"]
        self._state = self.state

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
    def should_poll(self):
        """No need to poll. Coordinator notifies entity of updates."""
        return False

    @property
    def available(self):
        """Return if entity is available."""
        return self.coordinator.last_update_success

    async def async_added_to_hass(self):
        """When entity is added to hass."""
        self.coordinator.async_add_listener(self.async_write_ha_state)

    async def async_will_remove_from_hass(self):
        """When entity will be removed from hass."""
        self.coordinator.async_remove_listener(self.async_write_ha_state)

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._name

    @property
    def unique_id(self):
        """Return the unique ID of the sensor."""
        return self._unique_id

    @property
    def icon(self):
        """Icon to use in the frontend, if any."""
        return self._icon

    @property
    def state(self):
        """Return the state of the sensor."""
        try:
            state = self.coordinator.data[self._device_id][self._name]["value"]
            if state:
                return state
            return 0
        except KeyError:
            _LOGGER.error("Can't find %s", self._unique_id)
            _LOGGER.debug("Sensor data %s", self.coordinator.data)
            return None

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement of this entity, if any."""
        return self._unit

    @property
    def device_class(self):
        """Return the device_class of this entity."""
        if self._unit == "°C":
            return SensorDeviceClass.TEMPERATURE
        elif self._unit in ("kWh", "Wh"):
            return SensorDeviceClass.ENERGY
        elif self._unit in ("kW", "W"):
            return SensorDeviceClass.POWER
        elif self._unit == "%":
            return SensorDeviceClass.POWER_FACTOR
        else:
            return None

    @property
    def state_class(self):
        """Return the state class of this entity, if any."""
        if self._unit in ("°C", "kW", "W", "%"):
            return SensorStateClass.MEASUREMENT
        elif self._unit in ("kWh", "Wh"):
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
