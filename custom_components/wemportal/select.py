"""
Select platform for wemportal component
"""

from typing import override

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from rapidfuzz import process, utils

from .const import _LOGGER, DOMAIN
from .entity import WemPortalWritableEntity


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


class WemPortalSelect(WemPortalWritableEntity, SelectEntity):
    """Representation of a WEM Portal Sensor."""

    def __init__(
        self, coordinator, config_entry: ConfigEntry, device_id, _unique_id, entity_data
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, config_entry, device_id, _unique_id, entity_data)
        self._options = entity_data["options"]
        self._options_names = entity_data["optionsNames"]

        try:
            val = entity_data["value"]
            if val in self._options_names:
                self._attr_current_option = val
            elif val in self._options:
                self._attr_current_option = self._options_names[self._options.index(val)]
            else:
                try:
                    self._attr_current_option = self._options_names[self._options.index(int(val))]
                except (ValueError, TypeError):
                    if val is not None and self._options_names:
                        best_match, score, _ = process.extractOne(
                            str(val), self._options_names, processor=utils.default_process
                        )
                        if score >= 75:
                            self._attr_current_option = best_match
                        else:
                            raise ValueError
                    else:
                        raise ValueError
        except (ValueError, TypeError):
            self._attr_current_option = None
            _LOGGER.warning("Value %s not found in options %s (names: %s) for select %s", entity_data["value"], self._options, self._options_names, self._attr_name)
        _LOGGER.debug('Init select: %s: "%s"', self._attr_name, self._attr_current_option)

    @override
    async def async_select_option(self, option: str) -> None:
        """Call the API to change the parameter value"""
        await self._async_change_value(
            self._options[self._options_names.index(option)]
        )

        self._attr_current_option = option

        self.async_write_ha_state()

    @property
    @override
    def options(self) -> list[str]:
        """Return list of available options."""
        return self._options_names

    @callback
    @override
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""

        try:
            val = self.coordinator.data[self._device_id][self._data_key]["value"]
            if val in self._options_names:
                self._attr_current_option = val
            elif val in self._options:
                self._attr_current_option = self._options_names[self._options.index(val)]
            else:
                try:
                    self._attr_current_option = self._options_names[self._options.index(int(val))]
                except (ValueError, TypeError):
                    if val is not None and self._options_names:
                        best_match, score, _ = process.extractOne(
                            str(val), self._options_names, processor=utils.default_process
                        )
                        if score >= 75:
                            self._attr_current_option = best_match
                        else:
                            raise ValueError
                    else:
                        raise ValueError
        except KeyError:
            self._attr_current_option = None
            _LOGGER.warning("Can't find %s", self._attr_unique_id)
            _LOGGER.debug("Sensor data %s", self.coordinator.data)
        except (ValueError, TypeError):
            self._attr_current_option = None
            _LOGGER.warning("Value %s not found in options %s (names: %s) for select %s", val, self._options, self._options_names, self._attr_name)

        self.async_write_ha_state()
