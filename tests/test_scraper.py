"""Test the WEM Portal scraper."""
from collections.abc import Generator
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from curl_cffi.requests import RequestsError
from pytest_homeassistant_custom_component.common import load_fixture

from custom_components.wemportal.const import WEB_LOGIN_URL, WEB_MAIN_URL
from custom_components.wemportal.exceptions import AuthError, WemPortalError
from custom_components.wemportal.scraper import WemPortalScraper

LOGIN_PAGE = (
    "<html><body><form>"
    '<input type="hidden" id="__VIEWSTATE" value="state"/>'
    '<input type="hidden" id="__EVENTVALIDATION" value="validation"/>'
    '<input name="ctl00$content$tbxUserName"/>'
    "</form></body></html>"
)


def _response(
    status_code: int = 200, text: str = "<html></html>", url: str = WEB_MAIN_URL
) -> SimpleNamespace:
    """Return a response like the ones of curl_cffi."""
    return SimpleNamespace(status_code=status_code, text=text, url=url)


LOGIN_FORM = _response(text=LOGIN_PAGE, url=WEB_LOGIN_URL)
ACCEPTED = _response()


@pytest.fixture
def mock_session() -> Generator[MagicMock]:
    """Return a session that serves the login page and accepts the login."""
    with patch(
        "custom_components.wemportal.scraper.requests.AsyncSession"
    ) as mock_session_class:
        session = mock_session_class.return_value.__aenter__.return_value
        session.get = AsyncMock(return_value=LOGIN_FORM)
        session.post = AsyncMock(return_value=ACCEPTED)
        yield session


async def test_login(mock_session: MagicMock) -> None:
    """Test a login that leaves the login page succeeds."""
    await WemPortalScraper("user", "pass").login()

    login_data = mock_session.post.call_args.kwargs["data"]
    assert login_data["__VIEWSTATE"] == "state"
    assert login_data["__EVENTVALIDATION"] == "validation"
    assert login_data["ctl00$content$tbxUserName"] == "user"


async def test_login_rejected(mock_session: MagicMock) -> None:
    """Test the login form shown again means the credentials are wrong."""
    mock_session.post.return_value = LOGIN_FORM

    with pytest.raises(AuthError):
        await WemPortalScraper("user", "pass").login()


@pytest.mark.parametrize(
    ("get_result", "post_result"),
    [
        pytest.param(RequestsError("timeout"), ACCEPTED, id="login_page_unreachable"),
        pytest.param(_response(503), ACCEPTED, id="login_page_error"),
        pytest.param(_response(text="<html></html>"), ACCEPTED, id="login_page_without_form"),
        pytest.param(LOGIN_FORM, RequestsError("timeout"), id="login_post_unreachable"),
        pytest.param(LOGIN_FORM, _response(403), id="login_post_forbidden"),
        pytest.param(
            LOGIN_FORM,
            _response(url=f"{WEB_LOGIN_URL}?AspxAutoDetectCookieSupport=1"),
            id="cookies_not_detected",
        ),
        pytest.param(LOGIN_FORM, _response(url=WEB_LOGIN_URL), id="unexpected_login_page"),
    ],
)
async def test_login_failure_is_not_auth_error(
    mock_session: MagicMock,
    get_result: SimpleNamespace | Exception,
    post_result: SimpleNamespace | Exception,
) -> None:
    """Test failures that aren't a rejected login raise an error that is retried."""
    mock_session.get.side_effect = [get_result]
    mock_session.post.side_effect = [post_result]

    with pytest.raises(WemPortalError) as exc_info:
        await WemPortalScraper("user", "pass").login()

    # AuthError is a WemPortalError too, but it would stop the polling
    assert exc_info.type is WemPortalError


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
        pytest.param(
            "Heizkreis - Heizkreis E - Solltemperatur",
            0.0,
            "°C",
            id="setpoint_placeholder_is_zero",
        ),
        pytest.param(
            "Heizkreis - Heizkreis E - Anforderung",
            0.0,
            "°C",
            id="demand_placeholder_is_zero",
        ),
        pytest.param(
            "Heizkreis - Heizkreis E - Leistungsanforderung",
            None,
            "%",
            id="power_demand_placeholder_is_none",
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
