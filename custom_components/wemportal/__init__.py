"""
wemportal integration

Author: erikkastelec
https://github.com/erikkastelec/hass-WEM-Portal

"""
from datetime import timedelta

import homeassistant.helpers.config_validation as config_validation
import voluptuous as vol
from homeassistant.const import CONF_PASSWORD, CONF_SCAN_INTERVAL, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType
from homeassistant.config_entries import ConfigEntry
from .const import CONF_LANGUAGE, CONF_MODE, CONF_SCAN_INTERVAL_API, DOMAIN, PLATFORMS
from .coordinator import WemPortalDataUpdateCoordinator
from .wemportalapi import WemPortalApi


# CONFIG_SCHEMA = vol.Schema(
#     {
#         DOMAIN: vol.Schema(
#             {
#                 vol.Optional(
#                     CONF_SCAN_INTERVAL, default=timedelta(minutes=30)
#                 ): config_validation.time_period,
#                 vol.Optional(
#                     CONF_SCAN_INTERVAL_API, default=timedelta(minutes=5)
#                 ): config_validation.time_period,
#                 vol.Optional(CONF_LANGUAGE, default="en"): config_validation.string,
#                 vol.Optional(CONF_MODE, default="api"): config_validation.string,
#                 vol.Required(CONF_USERNAME): config_validation.string,
#                 vol.Required(CONF_PASSWORD): config_validation.string,
#             }
#         )
#     },
#     extra=vol.ALLOW_EXTRA,
# )


def get_wemportal_unique_id(config_entry_id: str, device_id: str, name: str):
    """Return unique ID for WEM Portal."""
    return f"{config_entry_id}:{device_id}:{name}"


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the wemportal component."""
    hass.data.setdefault(DOMAIN, {})
    return True


#     # Set proper update_interval, based on selected mode
#     if config[DOMAIN].get(CONF_MODE) == "web":
#         update_interval = config[DOMAIN].get(CONF_SCAN_INTERVAL)

#     elif config[DOMAIN].get(CONF_MODE) == "api":
#         update_interval = config[DOMAIN].get(CONF_SCAN_INTERVAL_API)
#     else:
#         update_interval = min(
#             config[DOMAIN].get(CONF_SCAN_INTERVAL),
#             config[DOMAIN].get(CONF_SCAN_INTERVAL_API),
#         )
#     # Creatie API object
#     api = WemPortalApi(config[DOMAIN])
#     # Create custom coordinator
#     coordinator = WemPortalDataUpdateCoordinator(hass, api, update_interval)

#     hass.data[DOMAIN] = {
#         "api": api,
#         "coordinator": coordinator,
#     }

#     await coordinator.async_config_entry_first_refresh()

#     # Initialize platforms
#     for platform in PLATFORMS:
#         hass.helpers.discovery.load_platform(platform, DOMAIN, {}, config)
#     return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up the wemportal component."""
    # Set proper update_interval, based on selected mode
    if entry.data.get(CONF_MODE) == "web":
        update_interval = entry.data.get(CONF_SCAN_INTERVAL)

    elif entry.data.get(CONF_MODE) == "api":
        update_interval = entry.data.get(CONF_SCAN_INTERVAL_API)
    else:
        update_interval = min(
            entry.data.get(CONF_SCAN_INTERVAL),
            entry.data.get(CONF_SCAN_INTERVAL_API),
        )
    # Creatie API object
    api = WemPortalApi(entry.data)
    # Create custom coordinator
    coordinator = WemPortalDataUpdateCoordinator(
        hass, api, timedelta(seconds=update_interval)
    )

    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id] = {
        "api": api,
        # "config": entry.data,
        "coordinator": coordinator,
    }

    # TODO: Implement removal of outdated entries
    # current_devices: set[tuple[str, str]] = set({(DOMAIN, entry.entry_id)})

    # device_registry = dr.async_get(hass)
    # for device_entry in dr.async_entries_for_config_entry(
    #     device_registry, entry.entry_id
    # ):
    #     for identifier in device_entry.identifiers:
    #         if identifier in current_devices:
    #             break
    #     else:
    #         device_registry.async_remove_device(device_entry.id)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_entry_updated))

    return True


async def _async_entry_updated(hass: HomeAssistant, config_entry: ConfigEntry) -> None:
    """Handle entry updates."""
    await hass.config_entries.async_reload(config_entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Handle removal of an entry."""
    unload_ok = bool(
        await hass.config_entries.async_unload_platforms(config_entry, PLATFORMS)
    )
    if unload_ok:
        hass.data[DOMAIN].pop(config_entry.entry_id)

    return unload_ok
