""" WemPortal integration coordinator """
from __future__ import annotations

import async_timeout
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)
from .exceptions import WemPortalError
from .const import _LOGGER, DEFAULT_TIMEOUT
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
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

    async def _async_update_data(self):
        """Fetch data from the wemportal api"""
        async with async_timeout.timeout(DEFAULT_TIMEOUT):
            try:
                return await self.hass.async_add_executor_job(self.api.fetch_data)
            except WemPortalError as exc:
                _LOGGER.error("Error fetching data from wemportal", exc_info=exc)
                _LOGGER.error("Creating new wemportal api instance")
                # TODO: This is a temporary solution and should be removed when api cause from #28 is resolved
                try:
                    new_api = WemPortalApi(
                        self.config_entry.data.get(CONF_USERNAME),
                        self.config_entry.data.get(CONF_PASSWORD),
                        self.config_entry.options,
                    )
                    self.api = new_api
                except Exception:
                    pass
                raise UpdateFailed from exc
