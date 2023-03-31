""" Exceptions for the wemportal component."""

from homeassistant.exceptions import HomeAssistantError


class WemPortalError(HomeAssistantError):
    """
    Custom exception for WEM Portal errors
    """


class AuthError(WemPortalError):
    """Exception to indicate an authentication error."""


class UnknownAuthError(WemPortalError):
    """Exception to indicate an unknown authentication error."""


class ServerError(WemPortalError):
    """Exception to indicate a server error."""


class ForbiddenError(WemPortalError):
    """Exception to indicate a forbidden error (403)."""


class ExpiredSessionError(WemPortalError):
    """
    Custom exception for expired session errors
    """


class ParameterChangeError(WemPortalError):
    """
    Custom exception for parameter change errors
    """
