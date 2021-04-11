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
    DEVICE_CLASS_TEMPERATURE,
    DEVICE_CLASS_ENERGY,
    DEVICE_CLASS_POWER_FACTOR,
    DEVICE_CLASS_POWER
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
        update_interval=config.get(CONF_SCAN_INTERVAL),
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
        self._last_updated = None
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
    def device_class(self):
        """Return the device_class of this entity."""
        if self._unit == '°C':
            return DEVICE_CLASS_TEMPERATURE
        elif self._unit == 'kWh' or self._unit == 'Wh':
            return DEVICE_CLASS_ENERGY
        elif self._unit == 'kW' or self._unit == 'W':
            return DEVICE_CLASS_POWER
        elif self._unit == '%':
            return DEVICE_CLASS_POWER_FACTOR
        else:
            return None

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
