"""
Number platform for wemportal component
"""

from homeassistant.components.number import NumberEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from . import get_wemportal_unique_id
from homeassistant.helpers.entity import DeviceInfo
from .const import _LOGGER, DOMAIN
from .utils import (fix_value_and_uom, uom_to_device_class)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Number entry setup."""

    coordinator = hass.data[DOMAIN][config_entry.entry_id]["coordinator"]
    entities: list[WemPortalNumber] = []
    for device_id, entity_data in coordinator.data.items():
        for unique_id, values in entity_data.items():
            if isinstance(values, int):
                continue
            if values["platform"] == "number":
                entities.append(
                    WemPortalNumber(
                        coordinator, config_entry, device_id, unique_id, values
                    )
                )

    async_add_entities(entities)


class WemPortalNumber(CoordinatorEntity, NumberEntity):
    """Representation of a WEM Portal number."""

    def _validated_native_value(self, val, uom):
        """Return a Home Assistant-safe native value."""
        effective_uom = uom
        if effective_uom in (None, ""):
            effective_uom = getattr(self, "_attr_native_unit_of_measurement", None)
        is_numeric_sensor = effective_uom not in (None, "")

        if val is None:
            _LOGGER.warning('Invalid number value for "%s": %r -> set to None', self._attr_name, val)
            return None

        if isinstance(val, str):
            val = val.strip()
            if val == "":
                _LOGGER.warning('Invalid number value for "%s": %r -> set to None', self._attr_name, val)
                return None

        if is_numeric_sensor:
            try:
                float(val)
            except (TypeError, ValueError):
                _LOGGER.warning('Invalid numeric number value for "%s": %r -> set to None', self._attr_name, val)
                return None

        return val

    def __init__(
        self, coordinator, config_entry: ConfigEntry, device_id, _unique_id, entity_data
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)

        val, uom = fix_value_and_uom(entity_data["value"], entity_data["unit"])

        self._config_entry = config_entry
        self._device_id = device_id
        self._attr_has_entity_name = True
        self._attr_name = entity_data.get("friendlyName", _unique_id)
        self._attr_unique_id = get_wemportal_unique_id(
            self._config_entry.entry_id, str(self._device_id), str(_unique_id)
        )
        self._last_updated = None
        self._parameter_id = entity_data["ParameterID"]
        self._data_key = _unique_id
        self._attr_icon = entity_data["icon"]
        self._attr_native_unit_of_measurement = uom
        self._attr_native_value = self._validated_native_value(val, uom)
        self._attr_native_min_value = entity_data["min_value"]
        self._attr_native_max_value = entity_data["max_value"]
        self._attr_native_step = entity_data["step"]
        self._attr_should_poll = False
        self._module_index = entity_data["ModuleIndex"]
        self._module_type = entity_data["ModuleType"]

        _LOGGER.debug(
            'Init number: %s: "%s" [%s]', 
            self._attr_name, 
            self._attr_native_value, 
            self._attr_native_unit_of_measurement
        )

    async def async_set_native_value(self, value: float) -> None:
        """Update the current value."""
        await self.hass.async_add_executor_job(
            self.coordinator.api.change_value,
            self._device_id,
            self._parameter_id,
            self._module_index,
            self._module_type,
            value,
        )
        self._attr_native_value = value  # type: ignore
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

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""

        try:
            entity_data = self.coordinator.data[self._device_id][self._data_key]
            val, uom = fix_value_and_uom(entity_data["value"], entity_data["unit"])

            self._attr_native_value = self._validated_native_value(val, uom)

            # set uom if it references a valid non-trivial unit of measurement
            if uom not in (None, ""):
                self._attr_native_unit_of_measurement = uom

            _LOGGER.debug(
                'Update number: %s: "%s" [%s]', 
                self._attr_name, 
                self._attr_native_value, 
                self._attr_native_unit_of_measurement
            )

        except KeyError:
            self._attr_native_value = None
            _LOGGER.warning("Can't find %s", self._attr_unique_id)
            _LOGGER.debug("Sensor data %s", self.coordinator.data)

        self.async_write_ha_state()

    @property
    def device_class(self):
        """Return the device class of the sensor."""
        return uom_to_device_class(self._attr_native_unit_of_measurement)

    @property
    def extra_state_attributes(self):
        """Return the state attributes of this device."""
        attr = {}
        if self._last_updated is not None:
            attr["Last Updated"] = self._last_updated
        return attr
