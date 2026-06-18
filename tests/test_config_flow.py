"""Test the wemportal config flow."""
from unittest.mock import patch

import pytest
from homeassistant import config_entries
from homeassistant.const import CONF_USERNAME, CONF_PASSWORD

from custom_components.wemportal.const import DOMAIN, CONF_MODE
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
        "custom_components.wemportal.wemportalapi.WemPortalApi.web_login",
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
