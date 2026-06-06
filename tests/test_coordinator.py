"""Test the wemportal coordinator."""
from unittest.mock import MagicMock, patch
from datetime import timedelta

import pytest
from homeassistant.helpers.update_coordinator import UpdateFailed
from homeassistant.exceptions import ConfigEntryAuthFailed

from custom_components.wemportal.coordinator import WemPortalDataUpdateCoordinator
from custom_components.wemportal.exceptions import WemPortalError, AuthError


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
        await coordinator.async_refresh()

    assert coordinator.last_update_success is False
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
        await coordinator.async_refresh()

    assert coordinator.last_update_success is False
    assert coordinator.num_failed == 1


async def test_coordinator_disabled_devices(hass):
    """Test coordinator filters out disabled devices."""
    api_mock = MagicMock()
    api_mock.data = {"1234": {}, "5678": {}}
    api_mock.fetch_data.return_value = {"1234": {}}

    coordinator = WemPortalDataUpdateCoordinator(
        hass,
        api_mock,
        None,
        timedelta(seconds=30),
    )

    with patch("custom_components.wemportal.coordinator.dr.async_get") as mock_dr_get:
        mock_registry = MagicMock()
        
        def mock_get_device(identifiers):
            device_id = list(identifiers)[0][1]
            mock_device = MagicMock()
            if device_id == "5678":
                mock_device.disabled_by = "user"
            else:
                mock_device.disabled_by = None
            return mock_device
            
        mock_registry.async_get_device.side_effect = mock_get_device
        mock_dr_get.return_value = mock_registry

        await coordinator.async_refresh()

        api_mock.fetch_data.assert_called_once_with(["1234"])
