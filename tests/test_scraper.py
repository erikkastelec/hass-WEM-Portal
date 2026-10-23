"""Test the WEM Portal scraper."""
import pytest
from pytest_homeassistant_custom_component.common import load_fixture

from custom_components.wemportal.scraper import WemPortalScraper


@pytest.fixture(scope="module")
def parsed_values() -> dict[str, tuple[float | str | None, str | None]]:
    """Return the parsed expert page as (value, unit) by friendly name."""
    output = WemPortalScraper("test", "test").parse_expert_page(
        load_fixture("expert_page.html")
    )[0]
    return {
        entity["friendlyName"]: (entity["value"], entity["unit"])
        for key, entity in output.items()
        if key != "cookie"
    }


@pytest.mark.parametrize(
    ("friendly_name", "value", "unit"),
    [
        pytest.param("System - Außentemperatur", 12.5, "°C", id="number_with_unit"),
        pytest.param(
            "System - Außentemperatur Rücksetzen", "Nein", None, id="text_no_unit"
        ),
        pytest.param("System - Kollektortemperatur", None, "°C", id="placeholder"),
        pytest.param("System - Raumtemperatur", 0.0, "°C", id="off_is_numeric"),
        pytest.param("System - Betriebsart", "Automatik", None, id="text"),
        pytest.param(
            "Heizkreis - Heizkreis E - Vorlauftemperatur Aktuell Hzk0",
            None,
            "°C",
            id="placeholder_with_unit_nested_header",
        ),
    ],
)
def test_parse_expert_page(
    parsed_values: dict[str, tuple[float | str | None, str | None]],
    friendly_name: str,
    value: float | str | None,
    unit: str | None,
) -> None:
    """Test values and units are parsed from the expert page."""
    assert parsed_values[friendly_name] == (value, unit)
