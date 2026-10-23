"""Base entities for the wemportal component."""

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import get_wemportal_unique_id
from .const import DOMAIN
from .coordinator import WemPortalDataUpdateCoordinator


class WemPortalEntity(CoordinatorEntity[WemPortalDataUpdateCoordinator]):
    """Base entity for a WEM Portal parameter."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: WemPortalDataUpdateCoordinator,
        config_entry: ConfigEntry,
        device_id,
        data_key,
        entity_data,
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self._config_entry = config_entry
        self._device_id = device_id
        self._data_key = data_key
        self._parameter_id = entity_data["ParameterID"]
        self._attr_name = entity_data.get("friendlyName", data_key)
        self._attr_unique_id = get_wemportal_unique_id(
            config_entry.entry_id, str(device_id), str(data_key)
        )
        self._attr_icon = entity_data["icon"]
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{config_entry.entry_id}:{device_id}")},
            via_device_id=coordinator.hass.data[DOMAIN][config_entry.entry_id][
                "hub_device_id"
            ],
            name=str(device_id),
            manufacturer="Weishaupt",
            model="WEM Portal",
            sw_version=coordinator.api.api_version,
        )


class WemPortalWritableEntity(WemPortalEntity):
    """Base entity for a WEM Portal parameter that can be changed."""

    def __init__(
        self,
        coordinator: WemPortalDataUpdateCoordinator,
        config_entry: ConfigEntry,
        device_id,
        data_key,
        entity_data,
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator, config_entry, device_id, data_key, entity_data)
        self._module_index = entity_data["ModuleIndex"]
        self._module_type = entity_data["ModuleType"]

    async def _async_change_value(self, value) -> None:
        """Write a new value for this parameter to the WEM Portal."""
        await self.hass.async_add_executor_job(
            self.coordinator.api.change_value,
            self._device_id,
            self._parameter_id,
            self._module_index,
            self._module_type,
            value,
        )
