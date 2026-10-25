"""
Sensor platform for wemportal component
"""

from typing import override

from homeassistant.components.sensor import RestoreSensor, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import _LOGGER, DOMAIN
from .entity import WemPortalEntity
from .utils import fix_value_and_uom, uom_to_device_class, uom_to_state_class


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


class WemPortalSensor(WemPortalEntity, RestoreSensor):
    """Representation of a WEM Portal Sensor."""

    def _validated_native_value(self, val, uom):
        """Return a Home Assistant-safe native value."""
        effective_uom = uom
        if effective_uom in (None, ""):
            effective_uom = getattr(self, "_attr_native_unit_of_measurement", None)
        is_numeric_sensor = effective_uom not in (None, "")

        # None means the WEM Portal has no value right now, which isn't an error
        if val is None:
            return None

        if isinstance(val, str):
            val = val.strip()
            if val == "":
                _LOGGER.warning('Invalid sensor value for "%s": %r -> set to None', self._attr_name, val)
                return None
            if val.startswith("{"):
                return "Programmed"

        if is_numeric_sensor:
            if isinstance(val, str):
                from .utils import sanitize_value
                val = sanitize_value(val, effective_uom, self._attr_name)
            try:
                float(val)
            except (TypeError, ValueError):
                _LOGGER.warning('Invalid numeric sensor value for "%s": %r -> set to None', self._attr_name, val)
                return None

        return val

    def __init__(
        self, coordinator, config_entry: ConfigEntry, device_id, _unique_id, entity_data
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, config_entry, device_id, _unique_id, entity_data)

        val, uom = fix_value_and_uom(entity_data["value"], entity_data["unit"])

        self._attr_native_unit_of_measurement = uom
        self._attr_native_value = self._validated_native_value(val, uom)

        self._attr_device_class = entity_data.get("device_class")
        self._attr_state_class = entity_data.get("state_class")

        _LOGGER.debug(
            'Init sensor: %s: "%s" [%s]',
            self._attr_name,
            self._attr_native_value,
            self._attr_native_unit_of_measurement
        )

    @override
    async def async_added_to_hass(self) -> None:
        """Call when entity about to be added to hass."""
        await super().async_added_to_hass()
        if (last_sensor_data := await self.async_get_last_sensor_data()) is not None:
            if self._attr_native_unit_of_measurement in (None, ""):
                self._attr_native_unit_of_measurement = last_sensor_data.native_unit_of_measurement
                _LOGGER.debug(
                    "Restored unit %s for %s from previous session", 
                    self._attr_native_unit_of_measurement, self._attr_name
                )
    @callback
    @override
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
                'Update sensor: %s: "%s" [%s]', 
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
    @override
    def entity_category(self):
        """Return the entity category."""
        if any(x in self._attr_unique_id for x in ["ConnectionStatus", "HasErrors", "ErrorMessages"]):
            return EntityCategory.DIAGNOSTIC
        return None

    @property
    @override
    def device_class(self):
        """Return the device class of the sensor."""
        if self._attr_device_class is not None:
            return self._attr_device_class
        return uom_to_device_class(self._attr_native_unit_of_measurement)

    @property
    @override
    def state_class(self):
        """Return the state class of the sensor."""
        if self._attr_state_class is not None:
            return self._attr_state_class
        return uom_to_state_class(self._attr_native_unit_of_measurement)

    @property
    @override
    def extra_state_attributes(self):
        """Return the state attributes of this device."""
        attr = {}
        try:
            entity_data = self.coordinator.data[self._device_id][self._data_key]
            if "CircuitTimesDay" in entity_data:
                attr["CircuitTimesDay"] = entity_data["CircuitTimesDay"]
            if "PossibleValues" in entity_data:
                attr["PossibleValues"] = entity_data["PossibleValues"]
            if isinstance(entity_data.get("value"), str) and entity_data["value"].startswith("{"):
                attr["Raw_JSON"] = entity_data["value"]
        except KeyError:
            pass
            
        return attr
