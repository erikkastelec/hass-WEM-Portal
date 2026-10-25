"""Test the WemPortal API."""
import logging
from collections.abc import Generator
from unittest.mock import patch, MagicMock
import pytest
import requests

from custom_components.wemportal.const import SLOW_UPDATE_INTERVAL
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
    """Return a logged in API with a mocked session that does not sleep."""
    api = WemPortalApi("test", "test")
    api.session = MagicMock()
    api.valid_login = True
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
    assert api.valid_login is True


def test_make_api_call_auth_error_invalidates_login(api: WemPortalApi) -> None:
    """Test a session that stays expired after a retry forces a new login."""
    api.session.post.side_effect = [_response(401, b""), _response(401, b"")]

    with patch.object(api, "api_login"), pytest.raises(WemPortalError):
        api.make_api_call(URL, data={"DeviceID": 1})

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


def test_circuit_times_fetched_hourly(api: WemPortalApi) -> None:
    """Test schedules are only fetched once per slow update interval."""
    api.data = {"1234": {}}
    api.modules = {"1234": {}}

    with (
        patch.object(api, "make_api_call") as mock_call,
        patch.object(api, "get_circuit_times") as mock_circuit_times,
        patch.object(api, "get_statistics"),
    ):
        mock_call.return_value.json.return_value = {
            "ConnectionStatus": 0,
            "Modules": [],
        }
        api.get_data()
        api.get_data()
        assert mock_circuit_times.call_count == 1

        api.last_circuit_times_fetch -= SLOW_UPDATE_INTERVAL
        api.get_data()

    assert mock_circuit_times.call_count == 2


def test_parameter_data_failure_invalidates_login(api: WemPortalApi) -> None:
    """Test failing to fetch the values forces a new login next cycle."""
    api.data = {"1234": {}}
    api.modules = {"1234": {}}
    device_status = MagicMock()
    device_status.json.return_value = {"ConnectionStatus": 0}

    with (
        patch.object(
            api,
            "make_api_call",
            side_effect=[device_status, WemPortalError("Server error")],
        ),
        patch.object(api, "get_circuit_times"),
        patch.object(api, "get_statistics"),
    ):
        api.get_data()

    assert api.valid_login is False

def test_failing_request_logged_once(
    api: WemPortalApi, caplog: pytest.LogCaptureFixture
) -> None:
    """Test a failing request is logged as a warning once and when it recovers."""
    request = "CircuitTimes for Heizprogramm1 (device 1234)"
    error = WemPortalError("Server error")

    with caplog.at_level(logging.DEBUG, logger="custom_components.wemportal"):
        api._log_request_failure(request, error)
        api._log_request_failure(request, error)
        api._log_request_success(request)
        api._log_request_failure(request, error)

    assert [(record.levelname, record.getMessage()) for record in caplog.records] == [
        ("WARNING", f"Failed to fetch {request}: Server error"),
        ("DEBUG", f"Failed to fetch {request}: Server error"),
        ("INFO", f"Fetching {request} works again"),
        ("WARNING", f"Failed to fetch {request}: Server error"),
    ]
