import requests as reqs


class AuthError(reqs.HTTPError):
    """Exception to indicate an authentication error."""


class UnknownAuthError(reqs.HTTPError):
    """Exception to indicate an unknown authentication error."""


class WemPortalError(Exception):
    """
    Custom exception for WEM Portal errors
    """


class ExpiredSessionError(WemPortalError):
    """
    Custom exception for expired session errors
    """


class ParameterChangeError(WemPortalError):
    """
    Custom exception for parameter change errors
    """
