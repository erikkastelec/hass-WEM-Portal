"""
Switch platform for wemportal component
"""

from typing import override

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import _LOGGER, BOOLEAN_ON_STRINGS, DOMAIN
from .entity import WemPortalWritableEntity
from .utils import fix_value_and_uom


def _is_on(value) -> bool:
    """Return True if value represents an active/on state."""
    if value in (1, 1.0, True):
        return True
    if isinstance(value, str):
        return value.strip().lower() in BOOLEAN_ON_STRINGS
    return False


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Switch entry setup."""

    coordinator = hass.data[DOMAIN][config_entry.entry_id]["coordinator"]
    entities: list[WemPortalSwitch] = []
    for device_id, entity_data in coordinator.data.items():
        for unique_id, values in entity_data.items():
            if isinstance(values, int):
                continue
            if values["platform"] == "switch":
                entities.append(
                    WemPortalSwitch(
                        coordinator, config_entry, device_id, unique_id, values
                    )
                )
    async_add_entities(entities)


class WemPortalSwitch(WemPortalWritableEntity, SwitchEntity):
    """Representation of a WEM Portal Sensor."""

    def __init__(
        self,
        coordinator,
        config_entry: ConfigEntry,
        device_id,
        _unique_id,
        entity_data,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, config_entry, device_id, _unique_id, entity_data)

        val, uom = fix_value_and_uom(entity_data["value"], entity_data["unit"])

        self._attr_unit = uom
        self._attr_is_on = _is_on(val)
        self._attr_device_class = "switch"  # type: ignore

        _LOGGER.debug('Init switch: %s: "%s" [%s]', self._attr_name, self._attr_is_on, self._attr_unit)

    @override
    async def async_turn_on(self, **kwargs) -> None:
        await self._async_change_value(1.0)
        self._attr_is_on = True
        self.async_write_ha_state()

    @override
    async def async_turn_off(self, **kwargs) -> None:
        await self._async_change_value(0.0)
        self._attr_is_on = False
        self.async_write_ha_state()

    @callback
    @override
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        try:
            temp_val = self.coordinator.data[self._device_id][self._data_key]["value"]
            self._attr_is_on = _is_on(temp_val)
            
            _LOGGER.debug('Update switch: %s: "%s" [%s]', self._attr_name, self._attr_is_on, self._attr_unit)

        except KeyError:
            self._attr_is_on = None
            _LOGGER.warning("Can't find %s", self._attr_unique_id)
            _LOGGER.debug("Sensor data %s", self.coordinator.data)

        self.async_write_ha_state()
