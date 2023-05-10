""" WemPortal integration coordinator """
from __future__ import annotations
from time import monotonic

import async_timeout
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)
from .exceptions import ForbiddenError, ServerError, WemPortalError
from .const import _LOGGER, DEFAULT_CONF_SCAN_INTERVAL_API_VALUE, DEFAULT_TIMEOUT
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
        self.last_try = None
        self.num_failed = 0

    async def _async_update_data(self):
        """Fetch data from the wemportal api"""
        if self.num_failed > 2 and monotonic() - self.last_try < DEFAULT_CONF_SCAN_INTERVAL_API_VALUE:
            raise UpdateFailed("Waiting for more time to pass before retrying")
        async with async_timeout.timeout(DEFAULT_TIMEOUT):
            try:
                x = await self.hass.async_add_executor_job(self.api.fetch_data)
                self.num_failed = 0
                return x
            except WemPortalError as exc:
                self.num_failed += 1
                # if isinstance(exc.__cause__, (ServerError, ForbiddenError)):
                _LOGGER.warning("Creating new wemportal api instance", exc_info=exc)
                # TODO: This is a temporary solution and should be removed when api cause from #28 is resolved
                try:
                    new_api = WemPortalApi(
                        self.config_entry.data.get(CONF_USERNAME),
                        self.config_entry.data.get(CONF_PASSWORD),
                        self.config_entry.options,
                    )
                    del self.api
                    self.api = new_api
                except Exception as exc2:
                    raise UpdateFailed from exc2
                if isinstance(exc.__cause__, (ServerError, ForbiddenError)) and self.num_failed <= 1:
                    try:
                        x = await self.hass.async_add_executor_job(
                            self.api.fetch_data
                        )
                        self.num_failed = 0
                        return x
                    except WemPortalError as exc2:
                        self.num_failed += 1
                        _LOGGER.error(
                            "Error fetching data from wemportal", exc_info=exc2
                        )
                        raise UpdateFailed from exc2
                else:
                    raise UpdateFailed from exc
                # else:
                #     _LOGGER.error("Error fetching data from wemportal", exc_info=exc)
                #     raise UpdateFailed from exc
            finally:
                self.last_try = monotonic()
