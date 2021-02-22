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
    CONF_NAME,
    CONF_RESOURCES
)
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DEFAULT_NAME, _LOGGER, DEFAULT_TIMEOUT
from .wemportalapi import WemPortalApi

THERMOMETER_ICON = "mdi:thermometer"
FLASH_ICON = "mdi:flash"

SENSOR_TYPES = {
    "heating_circuit_1-outside_temperature": [
        "Heating Circuit 1-Outside Temperature",
        "°C",
        THERMOMETER_ICON
    ],
    "heating_circuit_1-long_term_outside": [
        "Heating Circuit 1-Long Term Outside",
        "°C",
        THERMOMETER_ICON
    ],
    "heating_circuit_1-room_temperature": [
        "Heating Circuit 1-Room Temperature",
        "°C",
        THERMOMETER_ICON
    ],
    "heating_circuit_1-flow_set_temperature": [
        "Heating Circuit 1-Flow Set Temperature",
        "°C",
        THERMOMETER_ICON
    ],
    "heating_circuit_1-flow_temperature": [
        "Heating Circuit 1-Flow Temperature",
        "°C",
        THERMOMETER_ICON
    ],
    "heating_circuit_1-version_R130": [
        "Heating Circuit 1-Version R130",
        "",
        FLASH_ICON
    ],
    "heating_circuit_2-outside_temperature": [
        "Heating Circuit 2-Outside Temperature",
        "°C",
        THERMOMETER_ICON
    ],
    "heating_circuit_2-outside_average": [
        "Heating Circuit 2-Outside Average",
        "°C",
        THERMOMETER_ICON
    ],
    "heating_circuit_2-long_term_outside": [
        "Heating Circuit 2-Long Term Outside",
        "°C",
        THERMOMETER_ICON
    ],
    "heating_circuit_2-room_setpoint": [
        "Heating Circuit 2-Room Setpoint",
        "°C",
        THERMOMETER_ICON
    ],
    "heating_circuit_2-flow_temperature": [
        "Heating Circuit 2-Flow Temperature",
        "°C",
        THERMOMETER_ICON
    ],
    "heating_circuit_2-pump": [
        "Heating Circuit 2-Pump",
        "",
        FLASH_ICON
    ],
    "heating_circuit_2-flow_set_temperature": [
        "Heating Circuit 2-Flow Set Temperature",
        "°C",
        THERMOMETER_ICON
    ],
    "heating_circuit_2-version_WWP-EM-HK": [
        "Heating Circuit 2-Version Wwp-Em-Hk  ",
        "",
        FLASH_ICON
    ],
    "heat_pump-hot_water_temperature": [
        "Heat Pump-Hot Water Temperature",
        "°C",
        THERMOMETER_ICON
    ],
    "heat_pump-power_requirement": [
        "Heat Pump-Power Requirement",
        "%",
        FLASH_ICON
    ],
    "heat_pump-dynamic_switching": [
        "Heat Pump-Dynamic Switching",
        "K",
        FLASH_ICON
    ],
    "heat_pump-LWT": [
        "Heat Pump-Lwt",
        "°C",
        THERMOMETER_ICON
    ],
    "heat_pump-return_temperature": [
        "Heat Pump-Return Temperature",
        "°C",
        THERMOMETER_ICON
    ],
    "heat_pump-pump_speed": [
        "Heat Pump-Pump Speed",
        "%",
        FLASH_ICON
    ],
    "heat_pump-volume_flow": [
        "Heat Pump-Volume Flow",
        "",
        FLASH_ICON
    ],
    "heat_pump-change_valve": [
        "Heat Pump-Change Valve",
        "circuit",
        FLASH_ICON
    ],
    "heat_pump-version_WWP-SG": [
        "Heat Pump-Version Wwp-Sg",
        "",
        FLASH_ICON
    ],
    "heat_pump-version_CPU": [
        "Heat Pump-Version Cpu",
        "",
        FLASH_ICON
    ],
    "heat_pump-set_frequency_compressor": [
        "Heat Pump-Set Frequency Compressor",
        "Hz",
        FLASH_ICON
    ],
    "heat_pump-frequency_compressor": [
        "Heat Pump-Frequency Compressor",
        "Hz",
        FLASH_ICON
    ],
    "heat_pump-outside_OAT": [
        "Heat Pump-Outside Oat",
        "°C",
        THERMOMETER_ICON
    ],
    "heat_pump-heat_exchanger_ODU_entry": [
        "Heat Pump-Heat Exchanger Odu Entry",
        "°C",
        THERMOMETER_ICON
    ],
    "heat_pump-OMT": [
        "Heat Pump-Omt",
        "°C",
        THERMOMETER_ICON
    ],
    "heat_pump-outside_CTT": [
        "Heat Pump-Outside Ctt",
        "°C",
        THERMOMETER_ICON
    ],
    "heat_pump-hydraulic_unit_ICT": [
        "Heat Pump-Hydraulic Unit Ict",
        "°C",
        THERMOMETER_ICON
    ],
    "heat_pump-hydraulic_unit_IRT": [
        "Heat Pump-Hydraulic Unit Irt",
        "°C",
        THERMOMETER_ICON
    ],
    "heat_pump-operating_hours_compresso": [
        "Heat Pump-Operating Hours Compressor",
        "h",
        FLASH_ICON
    ],
    "heat_pump-switchings_compressor": [
        "Heat Pump-Switchings Compressor",
        "",
        FLASH_ICON
    ],
    "heat_pump-switching_defrost": [
        "Heat Pump-Switching Defrost",
        "",
        FLASH_ICON
    ],
    "heat_pump-variant": [
        "Heat Pump-Variant",
        "",
        FLASH_ICON
    ],
    "2.WEZ-EP_1": [
        "2. Wez-Ep 1",
        "",
        FLASH_ICON
    ],
    "2.WEZ-EP_2": [
        "2. Wez-Ep 2",
        "",
        FLASH_ICON
    ],
    "2.WEZ-operating_hours_E1": [
        "2. Wez-Operating Hours E1",
        "h",
        FLASH_ICON
    ],
    "2.WEZ-operating_hours_E2": [
        "2. Wez-Operating Hours E2",
        "h",
        FLASH_ICON
    ],
    "2.WEZ-switchings_E1": [
        "2. Wez-Switchings E1",
        "",
        FLASH_ICON
    ],
    "2.WEZ-switching_E2": [
        "2. Wez-Switching E2",
        "",
        FLASH_ICON
    ],
    "statistics-consuption_day": [
        "Statistics-Consuption Day",
        "kWh",
        FLASH_ICON
    ],
    "statistics-consuption_months": [
        "Statistics-Consumption Months",
        "kWh",
        FLASH_ICON
    ],
    "statistics-consuption_year": [
        "Statistics-Consumption Year",
        "kWh",
        FLASH_ICON
    ],
    "statistics-heat_consuption_day": [
        "Statistics-Heat Consumption Day",
        "kWh",
        FLASH_ICON
    ],
    "statistics-heat_consuption_month": [
        "Statistics-Heat Consumption Month",
        "kWh",
        FLASH_ICON
    ],
    "statistics-heat_consuption_year": [
        "Statistics-Heat Consumption Year",
        "kWh",
        FLASH_ICON
    ],
    "statistics-hot_water_consuption_day": [
        "Statistics-Hot Water Consumption Day",
        "kWh",
        FLASH_ICON
    ],
    "statistics-hot_water_consuption_mont": [
        "Statistics-Hot Water Consumption Mont",
        "kWh",
        FLASH_ICON
    ],
    "statistics-hot_water_consuption_year": [
        "Statistics-Hot Water Consumption Year",
        "kWh",
        FLASH_ICON
    ],
    "statistics-cool_consuption_day": [
        "Statistics-Cool Consumption Day",
        "kWh",
        FLASH_ICON
    ],
    "statistics-cool_consuption_month": [
        "Statistics-Cool Consumption Month",
        "kWh",
        FLASH_ICON
    ],
    "statistics-cool_consuption_year": [
        "Statistics-Cool Consumption Year",
        "kWh",
        FLASH_ICON
    ]
}

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): config_validation.string,
        vol.Optional(CONF_SCAN_INTERVAL, default=timedelta(minutes=30)): config_validation.time_period,
        vol.Required(CONF_USERNAME): config_validation.string,
        vol.Required(CONF_PASSWORD): config_validation.string,
        vol.Required(CONF_RESOURCES, default=[]): vol.All(
            config_validation.ensure_list, [vol.In(SENSOR_TYPES)]
        ),
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

    for resource in config[CONF_RESOURCES]:
        sensor_type = resource.lower()

        if sensor_type not in SENSOR_TYPES:
            SENSOR_TYPES[sensor_type] = [sensor_type.title(), "", FLASH_ICON]

        entities.append(WemPortalSensor(coordinator, sensor_type, sensor_prefix))

    async_add_entities(entities)


class WemPortalSensor(Entity):
    """Representation of a WEM Portal Sensor."""

    def __init__(self, coordinator, sensor_type, sensor_prefix):
        """Initialize the sensor."""
        self.coordinator = coordinator
        self.type = sensor_type
        self._last_updated = None
        self._sensor_prefix = sensor_prefix
        self._entity_type = SENSOR_TYPES[self.type][0]
        self._name = SENSOR_TYPES[self.type][0]
        self._unit = SENSOR_TYPES[self.type][1]
        self._icon = SENSOR_TYPES[self.type][2]
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
        return f"{self._sensor_prefix}_{self._entity_type}"

    @property
    def icon(self):
        """Icon to use in the frontend, if any."""
        return self._icon

    @property
    def state(self):
        """Return the state of the sensor."""
        try:
            state = self.coordinator.data[self.type]
            if state:
                return state
            return 0
        except KeyError:
            _LOGGER.error("can't find %s", self.type)
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
