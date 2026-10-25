"""Test the wemportal coordinator."""
from datetime import timedelta
from unittest.mock import MagicMock, call

from freezegun.api import FrozenDateTimeFactory
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
    load_json_object_fixture,
)

from custom_components.wemportal.const import DEFAULT_CONF_SCAN_INTERVAL_API_VALUE, DOMAIN
from custom_components.wemportal.exceptions import AuthError, WemPortalError

DEVICE_ID = "1234"
SENSOR_KEY = "Wärmeerzeuger-Temperatur"
UPDATE_INTERVAL = timedelta(seconds=DEFAULT_CONF_SCAN_INTERVAL_API_VALUE)


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> str:
    """Set up the integration and return the entity ID of the temperature sensor."""
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    entity_id = er.async_get(hass).async_get_entity_id(
        "sensor", DOMAIN, f"{entry.entry_id}:{DEVICE_ID}:{SENSOR_KEY}"
    )
    assert entity_id is not None
    return entity_id


async def _tick(hass: HomeAssistant, freezer: FrozenDateTimeFactory, delta: timedelta) -> None:
    """Move the time forward and run what is due."""
    freezer.tick(delta)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()


async def test_slow_data_after_first_refresh(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    mock_config_entry: MockConfigEntry,
    mock_wemportal_api: MagicMock,
) -> None:
    """Test schedules and statistics are fetched right after the setup, then regularly."""
    await _setup(hass, mock_config_entry)
    assert mock_wemportal_api.fetch_data.call_args_list == [call([], False)]

    await _tick(hass, freezer, timedelta(seconds=1))
    assert mock_wemportal_api.fetch_data.call_args_list == [call([], False), call([], True)]

    await _tick(hass, freezer, UPDATE_INTERVAL - timedelta(seconds=1))
    assert mock_wemportal_api.fetch_data.call_count == 2

    await _tick(hass, freezer, timedelta(seconds=1))
    assert mock_wemportal_api.fetch_data.call_args_list[-1] == call([], True)
    assert mock_wemportal_api.fetch_data.call_count == 3


async def test_update_refreshes_state(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    mock_config_entry: MockConfigEntry,
    mock_wemportal_api: MagicMock,
) -> None:
    """Test a refresh updates the entity states."""
    entity_id = await _setup(hass, mock_config_entry)
    assert hass.states.get(entity_id).state == "21.5"

    data = load_json_object_fixture("api_data.json")
    data[DEVICE_ID][SENSOR_KEY]["value"] = 22.0
    mock_wemportal_api.fetch_data.return_value = data
    await _tick(hass, freezer, timedelta(seconds=1))

    assert hass.states.get(entity_id).state == "22.0"


async def test_update_failed(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    mock_config_entry: MockConfigEntry,
    mock_wemportal_api: MagicMock,
) -> None:
    """Test the entities become unavailable while updates fail and recover after."""
    entity_id = await _setup(hass, mock_config_entry)
    data = mock_wemportal_api.fetch_data.return_value

    mock_wemportal_api.fetch_data.side_effect = WemPortalError("Server error")
    await _tick(hass, freezer, timedelta(seconds=1))
    assert hass.states.get(entity_id).state == STATE_UNAVAILABLE

    mock_wemportal_api.fetch_data.side_effect = None
    mock_wemportal_api.fetch_data.return_value = data
    await _tick(hass, freezer, UPDATE_INTERVAL)
    assert hass.states.get(entity_id).state == "21.5"


async def test_auth_failed(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    mock_config_entry: MockConfigEntry,
    mock_wemportal_api: MagicMock,
) -> None:
    """Test an authentication error makes the entities unavailable and stops polling."""
    entity_id = await _setup(hass, mock_config_entry)

    mock_wemportal_api.fetch_data.side_effect = AuthError("Invalid credentials")
    await _tick(hass, freezer, timedelta(seconds=1))
    assert hass.states.get(entity_id).state == STATE_UNAVAILABLE

    await _tick(hass, freezer, UPDATE_INTERVAL)
    assert mock_wemportal_api.fetch_data.call_count == 2


async def test_disabled_devices_not_fetched(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_wemportal_api: MagicMock,
) -> None:
    """Test data is only fetched for devices that aren't disabled."""
    mock_config_entry.add_to_hass(hass)
    device_registry = dr.async_get(hass)
    for device_id in (DEVICE_ID, "5678"):
        device_registry.async_get_or_create(
            config_entry_id=mock_config_entry.entry_id,
            identifiers={(DOMAIN, f"{mock_config_entry.entry_id}:{device_id}")},
        )
    disabled_device = device_registry.async_get_device_by_identifier(
        (DOMAIN, f"{mock_config_entry.entry_id}:5678"), mock_config_entry.entry_id
    )
    device_registry.async_update_device(
        disabled_device.id, disabled_by=dr.DeviceEntryDisabler.USER
    )
    mock_wemportal_api.data = {DEVICE_ID: {}, "5678": {}}

    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert mock_wemportal_api.fetch_data.call_args_list == [call([DEVICE_ID], False)]
