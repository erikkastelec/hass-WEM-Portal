"""
Number platform for wemportal component
"""

from homeassistant.components.number import NumberEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import _LOGGER, DOMAIN


async def async_setup_platform(
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        async_add_entities: AddEntitiesCallback,
        discovery_info=None,
):
    """Setup the Wem Portal sensors."""

    coordinator = hass.data[DOMAIN]["coordinator"]

    entities: list[WemPortalNumber] = []
    for unique_id, values in coordinator.data.items():
        if values["platform"] == "number":
            entities.append(WemPortalNumber(coordinator, unique_id, values))

    async_add_entities(entities)


class WemPortalNumber(CoordinatorEntity, NumberEntity):
    """Representation of a WEM Portal number."""

    def __init__(self, coordinator, _unique_id, entity_data):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._last_updated = None
        self._name = _unique_id
        self._parameter_id = entity_data["ParameterID"]
        self._unique_id = _unique_id
        self._icon = entity_data["icon"]
        self._unit = entity_data["unit"]
        self._state = self.state
        self._attr_native_min_value = entity_data["min_value"]
        self._attr_native_max_value = entity_data["max_value"]
        self._attr_native_step = entity_data["step"]
        self._module_index = entity_data["ModuleIndex"]
        self._module_type = entity_data["ModuleType"]

    async def async_set_native_value(self, value: float) -> None:
        """Update the current value."""
        await self.hass.async_add_executor_job(
            self.coordinator.api.change_value,
            self._parameter_id,
            self._module_index,
            self._module_type,
            value,
        )
        self._state = value
        self.coordinator.data[self._unique_id]["value"] = value
        self.async_write_ha_state()

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
        """Return the unique ID of the binary sensor."""
        return self._unique_id

    @property
    def icon(self):
        """Icon to use in the frontend, if any."""
        return self._icon

    @property
    def state(self):
        """Return the state of the sensor."""
        try:
            state = self.coordinator.data[self._unique_id]["value"]
            if state:
                return state
            return 0
        except KeyError:
            _LOGGER.error("Can't find %s", self._unique_id)
            _LOGGER.debug("Sensor data %s", self.coordinator.data)
            return None

    @property
    def native_unit_of_measurement(self):
        """Return the unit of measurement of this entity, if any."""
        return self._unit

    # @property
    # def state_class(self):
    #     """Return the state class of this entity, if any."""
    #     if self._unit in ("°C", "kW", "W", "%"):
    #         return STATE_CLASS_MEASUREMENT
    #     elif self._unit in ("kWh", "Wh"):
    #         return STATE_CLASS_TOTAL_INCREASING
    #     else:
    #         return None

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
