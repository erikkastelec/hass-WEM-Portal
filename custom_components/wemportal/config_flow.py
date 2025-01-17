"""Config flow for wemportal integration."""
from __future__ import annotations

import logging

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)

from homeassistant import exceptions
from homeassistant.const import CONF_PASSWORD, CONF_SCAN_INTERVAL, CONF_USERNAME
from homeassistant.core import callback, HomeAssistant
import homeassistant.helpers.config_validation as config_validation
from .wemportalapi import WemPortalApi
from .const import (
    DOMAIN,
    CONF_LANGUAGE,
    CONF_MODE,
    CONF_SCAN_INTERVAL_API,
    DEFAULT_MODE,
    AVAILABLE_MODES
)
from .exceptions import AuthError, UnknownAuthError

_LOGGER = logging.getLogger(__name__)

DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
    }
)


async def validate_input(hass: HomeAssistant, data):
    """Validate the user input allows us to connect."""
    
    # Create API object
    api = WemPortalApi(data[CONF_USERNAME], data[CONF_PASSWORD], "placeholder")

    # Try mobile API login
    if data[CONF_MODE] == "api" or data[CONF_MODE] == "both":
        try:
            await hass.async_add_executor_job(api.api_login)
        except AuthError:
            # If API login fails, try WEB API login
            _LOGGER.warning("Mobile API login failed, trying web login...")
            try:
                await hass.async_add_executor_job(api.web_login)
            except AuthError as exc:
                raise InvalidAuth from exc
            except Exception as exc:
                raise CannotConnect from exc
        except UnknownAuthError as exc:
            raise CannotConnect from exc
    elif data[CONF_MODE] == "web":
        try:
            await hass.async_add_executor_job(api.web_login)
        except AuthError as exc:
            raise InvalidAuth from exc
        except Exception as exc:
            raise CannotConnect from exc

    return data

class ConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for wemportal."""

    VERSION = 2

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: ConfigEntry,
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


class WemportalOptionsFlow(OptionsFlow):
    """Handle options."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        self.add_suggested_values_to_schema
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_SCAN_INTERVAL,
                        default=self.config_entry.options.get(CONF_SCAN_INTERVAL, 1800),
                    ): config_validation.positive_int,
                    vol.Required(
                        CONF_SCAN_INTERVAL_API,
                        default=self.config_entry.options.get(
                            CONF_SCAN_INTERVAL_API, 300
                        ),
                    ): config_validation.positive_int,
                    vol.Required(
                        CONF_LANGUAGE,
                        default=self.config_entry.options.get(CONF_LANGUAGE, "en"),
                    ): config_validation.string,
                    
                    vol.Required(
                        CONF_MODE, default=self.config_entry.options.get(CONF_MODE, DEFAULT_MODE)
                        ): vol.In(AVAILABLE_MODES),

                }
            ),
        )

