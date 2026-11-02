"""Test the wemportal config flow."""
from unittest.mock import patch

import pytest
from homeassistant import config_entries
from homeassistant.const import CONF_USERNAME, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.wemportal.const import (
    CONF_LANGUAGE,
    CONF_MODE,
    DEFAULT_CONF_LANGUAGE_VALUE,
    DOMAIN,
)
from custom_components.wemportal.exceptions import AuthError


@pytest.fixture(autouse=True)
def bypass_setup_fixture():
    """Prevent setup."""
    with patch(
        "custom_components.wemportal.async_setup_entry",
        return_value=True,
    ):
        yield


async def test_form_successful_setup(hass):
    """Test we get the form and it processes a successful configuration."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == "form"
    assert result["errors"] == {}

    with patch(
        "custom_components.wemportal.wemportalapi.WemPortalApi.api_login", return_value=True
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_USERNAME: "test-username",
                CONF_PASSWORD: "test-password",
                CONF_MODE: "api",
            },
        )

    assert result2["type"] == "create_entry"
    assert result2["title"] == "test-username"
    assert result2["data"] == {
        CONF_USERNAME: "test-username",
        CONF_PASSWORD: "test-password",
        CONF_LANGUAGE: DEFAULT_CONF_LANGUAGE_VALUE,
        CONF_MODE: "api",
    }


async def test_form_invalid_auth(hass):
    """Test we gracefully handle invalid authentication errors."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    with patch(
        "custom_components.wemportal.wemportalapi.WemPortalApi.api_login",
        side_effect=AuthError,
    ), patch(
        "custom_components.wemportal.config_flow.WemPortalScraper.login",
        side_effect=AuthError,
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_USERNAME: "test-username",
                CONF_PASSWORD: "test-password",
                CONF_MODE: "api",
            },
        )

    assert result2["type"] == "form"
    assert result2["errors"] == {"base": "invalid_auth"}


async def test_form_cannot_connect(hass):
    """Test we gracefully handle connection errors."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    with patch(
        "custom_components.wemportal.wemportalapi.WemPortalApi.api_login",
        side_effect=Exception,
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_USERNAME: "test-username",
                CONF_PASSWORD: "test-password",
                CONF_MODE: "api",
            },
        )

    assert result2["type"] == "form"
    assert result2["errors"] == {"base": "cannot_connect"}


@pytest.mark.parametrize(
    ("side_effect", "error"),
    [
        pytest.param(AuthError, "invalid_auth", id="invalid_auth"),
        pytest.param(Exception, "cannot_connect", id="cannot_connect"),
    ],
)
async def test_reauth(
    hass: HomeAssistant, side_effect: type[Exception], error: str
) -> None:
    """Test a new password can be entered after the portal rejected the old one."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=2,
        data={CONF_USERNAME: "test-username", CONF_PASSWORD: "old-password"},
        options={CONF_MODE: "web"},
    )
    entry.add_to_hass(hass)

    result = await entry.start_reauth_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"

    with patch(
        "custom_components.wemportal.config_flow.WemPortalScraper.login",
        side_effect=side_effect,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_PASSWORD: "wrong-password"}
        )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": error}

    # The mode comes from the options, so web mode only checks the web login
    with patch(
        "custom_components.wemportal.config_flow.WemPortalScraper.login"
    ) as mock_login:
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_PASSWORD: "new-password"}
        )
    mock_login.assert_awaited_once()
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data[CONF_PASSWORD] == "new-password"
