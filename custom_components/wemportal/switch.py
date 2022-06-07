"""
Switch platform for wemportal component
"""

from homeassistant.components.switch import SwitchEntity
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
    """Setup the Wem Portal select."""

    coordinator = hass.data[DOMAIN]["coordinator"]

    entities: list[WemPortalSwitch] = []
    for unique_id, values in coordinator.data.items():
        if values["platform"] == "switch":
            entities.append(WemPortalSwitch(coordinator, unique_id, values))

    async_add_entities(entities)


class WemPortalSwitch(CoordinatorEntity, SwitchEntity):
    """Representation of a WEM Portal Sensor."""

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
        self._module_index = entity_data["ModuleIndex"]
        self._module_type = entity_data["ModuleType"]

    async def async_turn_on(self, **kwargs) -> None:
        await self.hass.async_add_executor_job(
            self.coordinator.api.change_value,
            self._parameter_id,
            self._module_index,
            self._module_type,
            1.0,
        )
        self._state = "on"
        self.coordinator.data[self._unique_id]["value"] = 1
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        await self.hass.async_add_executor_job(
            self.coordinator.api.change_value,
            self._parameter_id,
            self._module_index,
            self._module_type,
            0.0,
        )
        self._state = "off"
        self.coordinator.data[self._unique_id]["value"] = 0
        self.async_write_ha_state()

    @property
    def is_on(self) -> bool:
        """Return the state of the switch."""
        if self._state == 1.0:
            return True
        else:
            return False

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
            self._state = self.coordinator.data[self._unique_id]["value"]
            try:
                if int(self._state) == 1:
                    return "on"
                else:
                    return "off"
            except ValueError:
                return self._state

        except KeyError:
            _LOGGER.error("Can't find %s", self._unique_id)
            _LOGGER.debug("Sensor data %s", self.coordinator.data)
            return None

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
    def device_class(self):
        return "switch"

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
