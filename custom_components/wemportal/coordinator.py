""" WemPortal integration coordinator """
from __future__ import annotations

import async_timeout
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import _LOGGER, DEFAULT_TIMEOUT
from .wemportalapi import WemPortalApi


class WemPortalDataUpdateCoordinator(DataUpdateCoordinator):
    """DataUpdateCoordinator for wemportal component"""

    def __init__(self, hass: HomeAssistant, api: WemPortalApi, update_interval):
        """Initialize DataUpdateCoordinator for the wemportal component"""
        super().__init__(
            hass,
            _LOGGER,
            name="WemPortal update",
            update_interval=update_interval,
        )
        self.api = api
        self.has = hass

    async def _async_update_data(self):
        """Fetch data from the wemportal api"""
        async with async_timeout.timeout(DEFAULT_TIMEOUT):
            return await self.hass.async_add_executor_job(self.api.fetch_data)
