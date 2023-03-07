"""Config flow for wemportal integration."""
from __future__ import annotations

import logging

import voluptuous as vol

from homeassistant import config_entries, core, exceptions
from homeassistant.const import CONF_PASSWORD, CONF_SCAN_INTERVAL, CONF_USERNAME
from homeassistant.core import callback
import homeassistant.helpers.config_validation as config_validation
from .wemportalapi import WemPortalApi
from .const import (
    DOMAIN,
    CONF_LANGUAGE,
    CONF_MODE,
    CONF_SCAN_INTERVAL_API,
)
from .exceptions import AuthError, UnknownAuthError

_LOGGER = logging.getLogger(__name__)

DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
    }
)


async def validate_input(hass: core.HomeAssistant, data):
    """Validate the user input allows us to connect."""
    og_data = data
    # Populate with default values
    # Should be fixed, but for now, this should work.
    data[CONF_MODE] = "api"
    data[CONF_LANGUAGE] = "en"
    data[CONF_SCAN_INTERVAL_API] = 300
    data[CONF_SCAN_INTERVAL] = 1800

    # Create API object
    api = WemPortalApi(data)

    # Try to login
    try:
        await hass.async_add_executor_job(api.api_login)
    except AuthError:
        raise InvalidAuth from AuthError
    except UnknownAuthError:
        raise CannotConnect from UnknownAuthError

    return og_data


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for kmtronic."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> WemportalOptionsFlow:
        """Get the options flow for this handler."""
        return WemportalOptionsFlow(config_entry)

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        errors = {}
        if user_input is not None:
            try:
                info = await validate_input(self.hass, user_input)
                for existing_entry in self._async_current_entries(include_ignore=False):
                    if existing_entry.data[CONF_USERNAME] == user_input[CONF_USERNAME]:
                        return self.async_abort(reason="already_configured")

                return self.async_create_entry(
                    title=info[CONF_USERNAME], data=user_input
                )

            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="user", data_schema=DATA_SCHEMA, errors=errors
        )


class CannotConnect(exceptions.HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(exceptions.HomeAssistantError):
    """Error to indicate there is invalid auth."""


class WemportalOptionsFlow(config_entries.OptionsFlow):
    """Handle options."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_SCAN_INTERVAL, default=1800
                    ): config_validation.positive_int,
                    vol.Optional(
                        CONF_SCAN_INTERVAL_API, default=300
                    ): config_validation.positive_int,
                    vol.Optional(CONF_LANGUAGE, default="en"): config_validation.string,
                    vol.Optional(CONF_MODE, default="api"): config_validation.string,
                }
            ),
        )
