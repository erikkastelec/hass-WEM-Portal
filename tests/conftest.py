"""Global fixtures for wemportal integration."""
from collections.abc import Generator
from unittest.mock import MagicMock, patch

import pytest
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    load_json_object_fixture,
)

from custom_components.wemportal.const import DOMAIN

pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable custom integrations defined in the test dir."""
    yield


@pytest.fixture
def mock_setup_entry():
    """Override async_setup_entry."""
    with patch(
        "custom_components.wemportal.async_setup_entry", return_value=True
    ) as mock_setup_entry:
        yield mock_setup_entry


@pytest.fixture
def mock_config_entry() -> MockConfigEntry:
    """Return a mocked config entry."""
    return MockConfigEntry(
        domain=DOMAIN,
        version=2,
        data={CONF_USERNAME: "user", CONF_PASSWORD: "pass"},
    )


@pytest.fixture
def mock_wemportal_api() -> Generator[MagicMock]:
    """Return a mocked WEM Portal API."""
    with patch(
        "custom_components.wemportal.coordinator.WemPortalApi", autospec=True
    ) as mock_api_class:
        api = mock_api_class.return_value
        api.data = {}
        api.api_version = "1.2.3"
        api.parameter_cache = {}
        api.parameter_cache_changed = False
        api.fetch_data.return_value = load_json_object_fixture("api_data.json")
        yield api
