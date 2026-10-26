"""
wemportal integration

Author: erikkastelec
https://github.com/erikkastelec/hass-WEM-Portal

"""
import homeassistant.helpers.entity_registry as entity_registry
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as device_registry

from .const import (
    _LOGGER,
    DOMAIN,
    PLATFORMS,
)
from .coordinator import (
    WemPortalConfigEntry,
    WemPortalData,
    WemPortalDataUpdateCoordinator,
    parameter_store,
)


def get_wemportal_unique_id(config_entry_id: str, device_id: str, name: str):
    """Return unique ID for WEM Portal."""
    return f"{config_entry_id}:{device_id}:{name}"


# Migrate values from previous versions
async def migrate_unique_ids(
    hass: HomeAssistant, config_entry: ConfigEntry, coordinator
):
    er = entity_registry.async_get(hass)
    # Do migration for first device if we have multiple
    device_id = list(coordinator.data.keys())[0]
    data = coordinator.data[device_id]

    change = False
    for unique_id, values in data.items():
        if isinstance(values, int):
            continue
            
        new_id = get_wemportal_unique_id(config_entry.entry_id, device_id, unique_id)
        
        # Build a list of possible old unique_ids
        friendly_name = values.get("friendlyName", "")
        platform = values.get("platform", "sensor")
        
        possible_old_ids = []
        if unique_id != "ConnectionStatus":
            possible_old_ids.append(unique_id)
            possible_old_ids.append(f"{device_id}-{unique_id}")
            
        if friendly_name:
            possible_old_ids.append(friendly_name)
            possible_old_ids.append(f"{device_id}-{friendly_name}")
            possible_old_ids.append(get_wemportal_unique_id(config_entry.entry_id, device_id, friendly_name))
            
        parameter_id = values.get("ParameterID")
        if parameter_id:
            possible_old_ids.append(parameter_id)
            possible_old_ids.append(f"{device_id}-{parameter_id}")
            possible_old_ids.append(get_wemportal_unique_id(config_entry.entry_id, device_id, parameter_id))
            
        # Try to find an entity under any of these old ids
        for old_id in possible_old_ids:
            if not old_id:
                continue
            name_id = er.async_get_entity_id(platform, DOMAIN, old_id)
            if name_id is not None:
                new_entity_id = er.async_get_entity_id(platform, DOMAIN, new_id)
                if new_entity_id is not None and new_entity_id != name_id:
                    _LOGGER.info(
                        "Found entity with old id and an entity with a new unique_id. Preserving old entity..."
                    )
                    er.async_remove(new_entity_id)
                    
                if old_id != new_id:
                    _LOGGER.info(
                        "Migrating entity %s from old id %s to new unique_id %s",
                        name_id,
                        old_id,
                        new_id,
                    )
                    er.async_update_entity(
                        name_id,
                        new_unique_id=new_id,
                    )
                    change = True
                break

    if change:
        await coordinator.async_refresh()


async def async_setup_entry(hass: HomeAssistant, entry: WemPortalConfigEntry) -> bool:
    """Set up the wemportal component."""
    dr = device_registry.async_get(hass)
    devices = device_registry.async_entries_for_config_entry(dr, entry.entry_id)
    device_ids = [device.name for device in devices]
    if not device_ids:
        _LOGGER.warning("No devices found for %s. Starting first time initialization.", DOMAIN)
    else:
        _LOGGER.info("Found devices for %s: %s", DOMAIN, device_ids)

    coordinator = WemPortalDataUpdateCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()

    # Is there an on_update function that we can add listener to?
    _LOGGER.info("Migrating entity names for wemportal")
    await migrate_unique_ids(hass, entry, coordinator)

    # Register the hub device so child devices can reference it via via_device_id
    hub_device = dr.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, entry.entry_id)},
        manufacturer="Weishaupt",
        name=entry.title or "WEM Portal",
        model="WEM Portal",
    )

    entry.runtime_data = WemPortalData(coordinator, hub_device.id)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_entry_updated))

    return True


async def async_migrate_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Handle schema migrations."""
    # V1 to V2 migration is a no-op for the data schema, as entity ID migration 
    # is handled dynamically inside async_setup_entry via migrate_unique_ids.
    return True


async def _async_entry_updated(hass: HomeAssistant, config_entry: WemPortalConfigEntry) -> None:
    """Handle entry updates."""
    _LOGGER.info("Migrating entity names for wemportal because of config entry update")
    await migrate_unique_ids(hass, config_entry, config_entry.runtime_data.coordinator)
    await hass.config_entries.async_reload(config_entry.entry_id)


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Remove the cached parameter definitions of a removed entry."""
    await parameter_store(hass, entry).async_remove()


async def async_unload_entry(hass: HomeAssistant, config_entry: WemPortalConfigEntry) -> bool:
    """Handle removal of an entry."""
    return await hass.config_entries.async_unload_platforms(config_entry, PLATFORMS)
