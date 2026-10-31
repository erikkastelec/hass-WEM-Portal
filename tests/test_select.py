"""Test the wemportal select platform."""
from unittest.mock import MagicMock

import pytest
from homeassistant.const import STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    load_json_object_fixture,
)

from custom_components.wemportal.const import DOMAIN

DEVICE_ID = "1234"
SELECT_KEY = "Heizkreis-Betriebsart"


@pytest.mark.parametrize(
    ("value", "state"),
    [
        pytest.param(1, "Automatic", id="option_value"),
        pytest.param("Standby", "Standby", id="option_name"),
        pytest.param("AUTOMATIC ", "Automatic", id="close_match"),
        pytest.param("Party", STATE_UNKNOWN, id="no_match"),
    ],
)
async def test_select_current_option(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_wemportal_api: MagicMock,
    value: int | str,
    state: str,
) -> None:
    """Test the current option is matched from the value of the WEM Portal."""
    data = load_json_object_fixture("api_data.json")
    data[DEVICE_ID][SELECT_KEY]["value"] = value
    mock_wemportal_api.fetch_data.return_value = data
    mock_config_entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    entity_id = er.async_get(hass).async_get_entity_id(
        "select", DOMAIN, f"{mock_config_entry.entry_id}:{DEVICE_ID}:{SELECT_KEY}"
    )
    assert hass.states.get(entity_id).state == state
