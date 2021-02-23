"""
Gets sensor data from Weishaupt WEM portal using web scraping.
Author: erikkastelec
https://github.com/erikkastelec/hass-WEM-Portal

Configuration for this platform:
sensor:
  - platform: wemportal
    scan_interval: 1800
    username: username
    password: password
    resources:
      - heating_circuit_1-outside_temperature
      - heating_circuit_1-long_term_outside
      - heating_circuit_1-room_temperature
      - heating_circuit_1-flow_set_temperature
      - heating_circuit_1-flow_temperature
      - heating_circuit_1-version_R130
      - heating_circuit_2-outside_temperature
      - heating_circuit_2-outside_average
      - heating_circuit_2-long_term_outside
      - heating_circuit_2-room_setpoint
      - heating_circuit_2-flow_temperature
      - heating_circuit_2-pump
      - heating_circuit_2-flow_set_temperature
      - heating_circuit_2-version_WWP-EM-HK
      - heat_pump-hot_water_temperature
      - heat_pump-power_requirement
      - heat_pump-dynamic_switching
      - heat_pump-LWT
      - heat_pump-return_temperature
      - heat_pump-pump_speed
      - heat_pump-volume_flow
      - heat_pump-change_valve
      - heat_pump-version_WWP-SG
      - heat_pump-version_CPU
      - heat_pump-set_frequency_compressor
      - heat_pump-frequency_compressor
      - heat_pump-outside_OAT
      - heat_pump-heat_exchanger_ODU_entry
      - heat_pump-OMT
      - heat_pump-outside_CTT
      - heat_pump-hydraulic_unit_ICT
      - heat_pump-hydraulic_unit_IRT
      - heat_pump-operating_hours_compresso
      - heat_pump-switchings_compressor
      - heat_pump-switching_defrost
      - heat_pump-variant
      - 2.WEZ-EP_1
      - 2.WEZ-EP_2
      - 2.WEZ-operating_hours_E1
      - 2.WEZ-operating_hours_E2
      - 2.WEZ-switchings_E1
      - 2.WEZ-switching_E2
      - statistics-consuption_day
      - statistics-consuption_months
      - statistics-consuption_year
      - statistics-heat_consuption_day
      - statistics-heat_consuption_month
      - statistics-heat_consuption_year
      - statistics-hot_water_consuption_day
      - statistics-hot_water_consuption_mont
      - statistics-hot_water_consuption_year
      - statistics-cool_consuption_day
      - statistics-cool_consuption_month
      - statistics-cool_consuption_year
"""

from datetime import timedelta

import async_timeout
import homeassistant.helpers.config_validation as config_validation
import voluptuous as vol
from homeassistant.components.sensor import PLATFORM_SCHEMA
from homeassistant.const import (
    CONF_USERNAME,
    CONF_PASSWORD,
    CONF_SCAN_INTERVAL,
    CONF_NAME
)
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DEFAULT_NAME, _LOGGER, DEFAULT_TIMEOUT
from .wemportalapi import WemPortalApi

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): config_validation.string,
        vol.Optional(CONF_SCAN_INTERVAL, default=timedelta(minutes=30)): config_validation.time_period,
        vol.Required(CONF_USERNAME): config_validation.string,
        vol.Required(CONF_PASSWORD): config_validation.string,
    }
)


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Setup the Wem Portal sensors."""

    api = WemPortalApi(config.get(CONF_USERNAME), config.get(CONF_PASSWORD))

    async def async_update_data():
        """ fetch data from the Wem Portal website"""
        async with async_timeout.timeout(DEFAULT_TIMEOUT):
            data = await hass.async_add_executor_job(api.fetch_data)
            return data

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name="wem_portal_sensor",
        update_method=async_update_data,
        # Polling interval. Will only be polled if there are subscribers.
        update_interval=max(config.get(CONF_SCAN_INTERVAL), timedelta(minutes=15)),
    )

    # Fetch initial data so we have data when entities subscribe
    await coordinator.async_refresh()

    entities = []
    sensor_prefix = config.get(CONF_NAME)

    async_add_entities(
        WemPortalSensor(coordinator, _name, values[1], values[2]) for _name, values in coordinator.data.items()
    )


class WemPortalSensor(Entity):
    """Representation of a WEM Portal Sensor."""

    def __init__(self, coordinator, _name, _icon, _unit):
        """Initialize the sensor."""
        self.coordinator = coordinator
        # self.type = sensor_type
        self._last_updated = None
        # self._sensor_prefix = sensor_prefix
        # self._entity_type = SENSOR_TYPES[self.type][0]
        self._name = _name
        self._icon = _icon
        self._unit = _unit
        self._state = self.state

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
        return self._name
        # f"{self._sensor_prefix}_{self._entity_type}"

    @property
    def icon(self):
        """Icon to use in the frontend, if any."""
        return self._icon

    @property
    def state(self):
        """Return the state of the sensor."""
        try:
            state = self.coordinator.data[self._name][0]
            if state:
                return state
            return 0
        except KeyError:
            _LOGGER.error("can't find %s", self._name)
            _LOGGER.debug("sensor data %s", self.coordinator.data)
            return None

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement of this entity, if any."""
        return self._unit

    @property
    def device_state_attributes(self):
        """Return the state attributes of this device."""
        attr = {}
        if self._last_updated is not None:
            attr["Last Updated"] = self._last_updated
        return attr

    async def async_update(self):
        """Update Entity
        Only used by the generic entity update service."""
        await self.coordinator.async_request_refresh()
