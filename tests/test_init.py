"""Test the wemportal setup."""
from datetime import timedelta
from typing import Any
from unittest.mock import MagicMock, call

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
    load_json_object_fixture,
)

from custom_components.wemportal import coordinator
from custom_components.wemportal.const import DOMAIN

DEVICE_ID = "1234"


@pytest.mark.usefixtures("mock_wemportal_api")
async def test_child_device_via_hub(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """Test entities share a child device linked to the hub device."""
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    entry_id = mock_config_entry.entry_id
    device_registry = dr.async_get(hass)
    hub = device_registry.async_get_device_by_identifier((DOMAIN, entry_id), entry_id)
    device = device_registry.async_get_device_by_identifier(
        (DOMAIN, f"{entry_id}:{DEVICE_ID}"), entry_id
    )
    assert hub is not None
    assert device is not None
    assert device.via_device_id == hub.id
    assert device.manufacturer == "Weishaupt"
    assert device.model == "WEM Portal"
    assert device.sw_version == "1.2.3"

    entities = er.async_entries_for_config_entry(er.async_get(hass), entry_id)
    assert {entity.domain for entity in entities} == {
        "sensor",
        "number",
        "select",
        "switch",
    }
    assert all(entity.device_id == device.id for entity in entities)


async def test_parameter_cache_stored(
    hass: HomeAssistant,
    hass_storage: dict[str, Any],
    mock_config_entry: MockConfigEntry,
    mock_wemportal_api: MagicMock,
) -> None:
    """Test the parameter definitions are loaded, saved and removed with the entry."""
    mock_config_entry.add_to_hass(hass)
    storage_key = f"{DOMAIN}.{mock_config_entry.entry_id}"
    hass_storage[storage_key] = {"version": 1, "key": storage_key, "data": {"1234": "old"}}
    mock_wemportal_api.parameter_cache = {"1234": "new"}
    mock_wemportal_api.parameter_cache_changed = True

    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert coordinator.WemPortalApi.call_args.kwargs["parameter_cache"] == {"1234": "old"}
    assert hass_storage[storage_key]["data"] == {"1234": "new"}

    await hass.config_entries.async_remove(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert storage_key not in hass_storage


async def test_sensors_added_after_setup(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_wemportal_api: MagicMock,
) -> None:
    """Test sensors from schedules and statistics are added when they show up."""
    data = load_json_object_fixture("api_data.json")
    schedule = {
        "friendlyName": "Heating Program 1",
        "ParameterID": "Heizprogramm1",
        "unit": None,
        "value": "Active",
        "icon": "mdi:calendar-clock",
        "platform": "sensor",
    }
    mock_wemportal_api.fetch_data.side_effect = [
        data,
        {DEVICE_ID: {**data[DEVICE_ID], "HZK0-Heizprogramm1": schedule}},
    ]
    mock_config_entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    assert mock_wemportal_api.fetch_data.call_args_list == [call([], False)]

    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=2))
    await hass.async_block_till_done()

    assert mock_wemportal_api.fetch_data.call_args_list == [
        call([], False),
        call([], True),
    ]
    entity_id = er.async_get(hass).async_get_entity_id(
        "sensor",
        DOMAIN,
        f"{mock_config_entry.entry_id}:{DEVICE_ID}:HZK0-Heizprogramm1",
    )
    assert entity_id is not None
    assert hass.states.get(entity_id).state == "Active"
