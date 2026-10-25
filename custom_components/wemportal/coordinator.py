""" WemPortal integration coordinator """
from __future__ import annotations
import asyncio
from datetime import timedelta

from time import monotonic
from typing import override

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .const import (
    _LOGGER,
    DEFAULT_CONF_SCAN_INTERVAL_API_VALUE,
    DEFAULT_TIMEOUT,
    DOMAIN,
    STORAGE_VERSION,
)
from .exceptions import AuthError, ForbiddenError, WemPortalError
from .wemportalapi import WemPortalApi


def parameter_store(hass: HomeAssistant, entry: ConfigEntry) -> Store:
    """Return the store with the parameter definitions of an entry."""
    return Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}")


class WemPortalDataUpdateCoordinator(DataUpdateCoordinator):
    """DataUpdateCoordinator for wemportal component"""

    api: WemPortalApi

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        update_interval,
    ) -> None:
        """Initialize DataUpdateCoordinator for the wemportal component"""
        super().__init__(
            hass,
            _LOGGER,
            name="WemPortal update",
            # The first refresh leaves out schedules and statistics, so the next one follows right away
            update_interval=timedelta(seconds=1),
        )
        self.regular_update_interval = update_interval
        self.hass = hass
        self.config_entry = config_entry
        self._store = parameter_store(hass, config_entry)
        self.last_try = None
        self.num_failed = 0

    @override
    async def _async_setup(self) -> None:
        """Create the API with the parameter definitions saved earlier."""
        self.api = self._create_api(parameter_cache=await self._store.async_load())

    def _create_api(self, existing_data=None, parameter_cache=None) -> WemPortalApi:
        """Return a new API client for the account of the entry."""
        return WemPortalApi(
            self.config_entry.data[CONF_USERNAME],
            self.config_entry.data[CONF_PASSWORD],
            config=self.config_entry.options,
            existing_data=existing_data,
            parameter_cache=parameter_cache,
        )


    @override
    async def _async_update_data(self):
        """Fetch data from the wemportal api"""
        if self.num_failed > 2 and monotonic() - self.last_try < DEFAULT_CONF_SCAN_INTERVAL_API_VALUE:
            raise UpdateFailed("Waiting for more time to pass before retrying")
            
        device_registry = dr.async_get(self.hass)
        enabled_devices = []
        for device_id in self.api.data.keys():
            device_entry = device_registry.async_get_device_by_identifier(
                (DOMAIN, f"{self.config_entry.entry_id}:{device_id}"),
                self.config_entry.entry_id,
            )
            if device_entry is not None and device_entry.disabled_by is not None:
                _LOGGER.debug("Skipping disabled device %s", device_id)
                continue
            enabled_devices.append(device_id)

        async with asyncio.timeout(DEFAULT_TIMEOUT):
            try:
                # Schedules and statistics take over a minute, so leave them out of the setup
                include_slow = self.data is not None
                if include_slow:
                    self.update_interval = self.regular_update_interval
                data = await self.hass.async_add_executor_job(
                    self.api.fetch_data, enabled_devices, include_slow
                )
            except AuthError as exc:
                self.num_failed += 1
                _LOGGER.error("Authentication error, raising ConfigEntryAuthFailed: %s", exc)
                raise ConfigEntryAuthFailed("WEM Portal authentication failed. Check your credentials.") from exc
            except (WemPortalError, ForbiddenError) as exc:
                self.num_failed += 1
                if self.num_failed >= 2:
                    _LOGGER.info("API errors persistent. Re-instantiating WemPortalApi to recover from potentially corrupted session/state.")
                    self.api = self._create_api(self.api.data, self.api.parameter_cache)
                raise UpdateFailed(f"Error fetching data from wemportal: {exc}") from exc
            finally:
                self.last_try = monotonic()

        self.num_failed = 0
        if self.api.parameter_cache_changed:
            await self._store.async_save(self.api.parameter_cache)
            self.api.parameter_cache_changed = False
        return data
