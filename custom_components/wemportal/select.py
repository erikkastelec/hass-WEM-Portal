"""
Select platform for wemportal component
"""

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, _LOGGER
from . import get_wemportal_unique_id


async def async_setup_platform(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
    discovery_info=None,
):
    """Setup the Wem Portal select."""

    coordinator = hass.data[DOMAIN]["coordinator"]

    entities: list[WemPortalSelect] = []
    for device_id, entity_data in coordinator.data.items():
        for unique_id, values in entity_data.items():
            if isinstance(values, int):
                continue
            if values["platform"] == "select":
                entities.append(
                    WemPortalSelect(
                        coordinator, config_entry, device_id, unique_id, values
                    )
                )

    async_add_entities(entities)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Select entry setup."""

    coordinator = hass.data[DOMAIN][config_entry.entry_id]["coordinator"]
    entities: list[WemPortalSelect] = []
    for device_id, entity_data in coordinator.data.items():
        for unique_id, values in entity_data.items():
            if isinstance(values, int):
                continue
            if values["platform"] == "select":
                entities.append(
                    WemPortalSelect(
                        coordinator, config_entry, device_id, unique_id, values
                    )
                )

    async_add_entities(entities)


class WemPortalSelect(CoordinatorEntity, SelectEntity):
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
        self._options = entity_data["options"]
        self._options_names = entity_data["optionsNames"]
        self._module_index = entity_data["ModuleIndex"]
        self._module_type = entity_data["ModuleType"]
        self._attr_current_option = self._options_names[self._options.index( entity_data["value"])]

    async def async_select_option(self, option: str) -> None:
        """Call the API to change the parameter value"""
        await self.hass.async_add_executor_job(
            self.coordinator.api.change_value,
            self._device_id,
            self._parameter_id,
            self._module_index,
            self._module_type,
            self._options[self._options_names.index(option)],
        )

        self._attr_current_option = option

        self.async_write_ha_state()

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

    @property
    def options(self) -> list[str]:
        """Return list of available options."""
        return self._options_names

    # async def async_added_to_hass(self):
    #     """When entity is added to hass."""
    #     self.async_on_remove(
    #         self.coordinator.async_add_listener(self._handle_coordinator_update)
    #     )

    @property
    def extra_state_attributes(self):
        """Return the state attributes of this device."""
        attr = {}
        if self._last_updated is not None:
            attr["Last Updated"] = self._last_updated
        return attr

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""

        try:
            self._attr_current_option = self._options_names[self._options.index( self.coordinator.data[self._device_id][self._attr_name]["value"])]
        except KeyError:
            self._attr_current_option = None
            _LOGGER.warning("Can't find %s", self._attr_unique_id)
            _LOGGER.debug("Sensor data %s", self.coordinator.data)

        self.async_write_ha_state()

    async def async_update(self):
        """Update Entity
        Only used by the generic entity update service."""
        await self.coordinator.async_request_refresh()
