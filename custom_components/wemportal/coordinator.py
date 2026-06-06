""" WemPortal integration coordinator """
from __future__ import annotations
from time import monotonic
import copy

import async_timeout
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import device_registry as dr
from .exceptions import ForbiddenError, ServerError, WemPortalError, AuthError
from .const import _LOGGER, DEFAULT_CONF_SCAN_INTERVAL_API_VALUE, DEFAULT_TIMEOUT, DOMAIN
from homeassistant.const import CONF_PASSWORD
from .wemportalapi import WemPortalApi

class WemPortalDataUpdateCoordinator(DataUpdateCoordinator):
    """DataUpdateCoordinator for wemportal component"""

    def __init__(
        self,
        hass: HomeAssistant,
        api: WemPortalApi,
        config_entry: ConfigEntry,
        update_interval,
    ) -> None:
        """Initialize DataUpdateCoordinator for the wemportal component"""
        super().__init__(
            hass,
            _LOGGER,
            name="WemPortal update",
            update_interval=update_interval,
        )
        self.api = api
        self.hass = hass
        self.config_entry = config_entry
        self.last_try = None
        self.num_failed = 0


    async def _async_update_data(self):
        """Fetch data from the wemportal api"""
        if self.num_failed > 2 and monotonic() - self.last_try < DEFAULT_CONF_SCAN_INTERVAL_API_VALUE:
            raise UpdateFailed("Waiting for more time to pass before retrying")
            
        device_registry = dr.async_get(self.hass)
        enabled_devices = []
        for device_id in self.api.data.keys():
            device_entry = device_registry.async_get_device(identifiers={(DOMAIN, str(device_id))})
            if device_entry is not None and device_entry.disabled_by is not None:
                _LOGGER.debug("Skipping disabled device %s", device_id)
                continue
            enabled_devices.append(device_id)

        async with async_timeout.timeout(DEFAULT_TIMEOUT):
            try:
                x = await self.hass.async_add_executor_job(self.api.fetch_data, enabled_devices)
                self.num_failed = 0
                return x
            except AuthError as exc:
                self.num_failed += 1
                _LOGGER.error("Authentication error, raising ConfigEntryAuthFailed: %s", exc)
                raise ConfigEntryAuthFailed("WEM Portal authentication failed. Check your credentials.") from exc
            except (WemPortalError, ForbiddenError) as exc:
                self.num_failed += 1
                raise UpdateFailed(f"Error fetching data from wemportal: {exc}") from exc
            finally:
                self.last_try = monotonic()
