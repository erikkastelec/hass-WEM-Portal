"""Test the WemPortal API."""
from collections.abc import Generator
from unittest.mock import patch, MagicMock
import pytest
import requests

from custom_components.wemportal.wemportalapi import WemPortalApi
from custom_components.wemportal.exceptions import ForbiddenError, WemPortalError


def test_api_login_success():
    """Test successful API login."""
    api = WemPortalApi("test", "test")
    
    with patch("custom_components.wemportal.wemportalapi.reqs.Session.post") as mock_post:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"Status": 0, "Message": "OK"}
        mock_post.return_value = mock_response

        api.api_login()
        
        assert api.valid_login is True
        mock_post.assert_called_once()


def test_api_login_failure():
    """Test API login failure resulting in ForbiddenError."""
    api = WemPortalApi("test", "test")
    
    with patch("custom_components.wemportal.wemportalapi.reqs.Session.post") as mock_post:
        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_response.json.return_value = {"Status": 403, "Message": "Forbidden"}
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError(response=mock_response)
        mock_post.return_value = mock_response

        with pytest.raises(ForbiddenError):
            api.api_login()
            
        assert api.valid_login is False


URL = "https://www.wemportal.com/app/CircuitTimes/Read"


def _response(status_code: int, body: bytes) -> requests.Response:
    """Build a real response, as a MagicMock would always be truthy."""
    response = requests.Response()
    response.status_code = status_code
    response.url = URL
    response._content = body
    return response


@pytest.fixture
def api() -> Generator[WemPortalApi]:
    """Return an API with a mocked session that does not sleep."""
    api = WemPortalApi("test", "test")
    api.session = MagicMock()
    with patch("custom_components.wemportal.wemportalapi.time.sleep"):
        yield api


def test_make_api_call_error_details(api: WemPortalApi) -> None:
    """Test the HTTP error and server message end up in the raised error."""
    api.session.post.return_value = _response(
        500, b'{"Status": 5, "Message": "Job not finished"}'
    )

    with pytest.raises(WemPortalError) as exc_info:
        api.make_api_call(URL, data={"DeviceID": 1})

    assert f"500 Server Error: None for url: {URL}" in str(exc_info.value)
    assert "internal status code: 5 and message: Job not finished" in str(
        exc_info.value
    )
    assert api.valid_login is False


@pytest.mark.parametrize("status_code", [401, 403])
def test_make_api_call_reauth_on_expired_session(
    api: WemPortalApi, status_code: int
) -> None:
    """Test an expired session triggers a login and a retry."""
    success = _response(200, b"{}")
    api.session.post.side_effect = [_response(status_code, b""), success]

    with patch.object(api, "api_login") as mock_login:
        assert api.make_api_call(URL, data={"DeviceID": 1}) is success

    mock_login.assert_called_once()
