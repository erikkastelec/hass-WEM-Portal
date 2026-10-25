"""Test the wemportal coordinator."""
from datetime import timedelta
from unittest.mock import MagicMock

import pytest
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.update_coordinator import UpdateFailed
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.wemportal.const import DOMAIN
from custom_components.wemportal.coordinator import WemPortalDataUpdateCoordinator
from custom_components.wemportal.exceptions import AuthError, WemPortalError


async def test_coordinator_update_success(hass):
    """Test successful coordinator update."""
    api_mock = MagicMock()
    api_mock.fetch_data.return_value = {"0000": {"sensor1": {"value": 10}}}

    coordinator = WemPortalDataUpdateCoordinator(
        hass,
        api_mock,
        None,
        timedelta(seconds=30),
    )

    await coordinator.async_refresh()

    assert coordinator.last_update_success is True
    assert coordinator.data == {"0000": {"sensor1": {"value": 10}}}
    assert coordinator.num_failed == 0


async def test_coordinator_update_failed(hass):
    """Test coordinator gracefully handles WemPortalError."""
    api_mock = MagicMock()
    api_mock.fetch_data.side_effect = WemPortalError("Mocked API Error")

    coordinator = WemPortalDataUpdateCoordinator(
        hass,
        api_mock,
        None,
        timedelta(seconds=30),
    )

    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()

    assert coordinator.num_failed == 1

async def test_coordinator_auth_failed(hass):
    """Test coordinator handles AuthError by raising ConfigEntryAuthFailed."""
    api_mock = MagicMock()
    api_mock.data = {"0000": {}}
    api_mock.fetch_data.side_effect = AuthError("Mocked Auth Error")

    coordinator = WemPortalDataUpdateCoordinator(
        hass,
        api_mock,
        None,
        timedelta(seconds=30),
    )

    with pytest.raises(ConfigEntryAuthFailed):
        await coordinator._async_update_data()

    assert coordinator.num_failed == 1


async def test_coordinator_disabled_devices(hass):
    """Test coordinator filters out disabled devices."""
    api_mock = MagicMock()
    api_mock.data = {"1234": {}, "5678": {}}
    api_mock.fetch_data.return_value = {"1234": {}}

    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)
    device_registry = dr.async_get(hass)
    for device_id in ("1234", "5678"):
        device_registry.async_get_or_create(
            config_entry_id=entry.entry_id,
            identifiers={(DOMAIN, f"{entry.entry_id}:{device_id}")},
        )
    disabled_device = device_registry.async_get_device_by_identifier(
        (DOMAIN, f"{entry.entry_id}:5678"), entry.entry_id
    )
    device_registry.async_update_device(
        disabled_device.id, disabled_by=dr.DeviceEntryDisabler.USER
    )

    coordinator = WemPortalDataUpdateCoordinator(
        hass,
        api_mock,
        entry,
        timedelta(seconds=30),
    )

    await coordinator.async_refresh()

    api_mock.fetch_data.assert_called_once_with(["1234"])
