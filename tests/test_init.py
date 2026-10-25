"""Test the wemportal setup."""
import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

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
