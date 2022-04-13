"""
wemportal integration

Author: erikkastelec
https://github.com/erikkastelec/hass-WEM-Portal

"""
from datetime import timedelta

import voluptuous as vol

from homeassistant.const import CONF_PASSWORD, CONF_SCAN_INTERVAL, CONF_USERNAME
from homeassistant.core import HomeAssistant, callback
import homeassistant.helpers.config_validation as config_validation
from homeassistant.helpers.typing import ConfigType

from .const import CONF_LANGUAGE, CONF_MODE, CONF_SCAN_INTERVAL_API, DOMAIN, PLATFORMS
from .coordinator import WemPortalDataUpdateCoordinator
from .wemportalapi import WemPortalApi

CONFIG_SCHEMA = vol.Schema(
    {
        vol.Optional(DOMAIN, default=[]): vol.Schema(
            {
                vol.Optional(
                    CONF_SCAN_INTERVAL, default=timedelta(minutes=30)
                ): config_validation.time_period,
                vol.Optional(
                    CONF_SCAN_INTERVAL_API, default=timedelta(minutes=5)
                ): config_validation.time_period,
                vol.Optional(CONF_LANGUAGE, default="en"): config_validation.string,
                vol.Optional(CONF_MODE, default="both"): config_validation.string,
                vol.Required(CONF_USERNAME): config_validation.string,
                vol.Required(CONF_PASSWORD): config_validation.string,
            }
        )
    },
    extra=vol.ALLOW_EXTRA,
)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the wemportal component."""
    # Set proper update_interval, based on selected mode
    if config[DOMAIN].get(CONF_MODE) == "web":
        update_interval = config[DOMAIN].get(CONF_SCAN_INTERVAL)

    elif config[DOMAIN].get(CONF_MODE) == "api":
        update_interval = config[DOMAIN].get(CONF_SCAN_INTERVAL_API)
    else:
        update_interval = min(
            config[DOMAIN].get(CONF_SCAN_INTERVAL),
            config[DOMAIN].get(CONF_SCAN_INTERVAL_API),
        )
    # Creatie API object
    api = WemPortalApi(config[DOMAIN])
    # Create custom coordinator
    coordinator = WemPortalDataUpdateCoordinator(hass, api, update_interval)

    hass.data[DOMAIN] = {
        "api": api,
        "config": config[DOMAIN],
        "coordinator": coordinator,
    }

    await coordinator.async_config_entry_first_refresh()

    # Initialize platforms
    for platform in PLATFORMS:
        hass.helpers.discovery.load_platform(platform, DOMAIN, {}, config)
    return True

#     """Remove obsolete entities from entity registry."""

#     if hap.home.currentAPVersion < "2.2.12":
#         return

#     entity_registry = er.async_get(hass)
#     er_entries = async_entries_for_config_entry(entity_registry, entry.entry_id)
#     for er_entry in er_entries:
#         if er_entry.unique_id.startswith("HomematicipAccesspointStatus"):
#             entity_registry.async_remove(er_entry.entity_id)
#             continue

#         for hapid in hap.home.accessPointUpdateStates:
#             if er_entry.unique_id == f"HomematicipBatterySensor_{hapid}":
#                 entity_registry.async_remove(er_entry.entity_id)
