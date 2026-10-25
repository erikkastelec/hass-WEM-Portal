"""Test the WemPortal API."""
import logging
from collections.abc import Generator
from unittest.mock import patch, MagicMock
import pytest
import requests

from custom_components.wemportal.const import SLOW_UPDATE_INTERVAL
from custom_components.wemportal.scraper import WemPortalScraper
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


def _json(body: dict) -> MagicMock:
    """Return a mocked response with a JSON body."""
    response = MagicMock()
    response.json.return_value = body
    return response


def test_get_devices_records_statistics_modules(api: WemPortalApi) -> None:
    """Test the device modules are remembered as statistics candidates."""
    devices = {
        "Devices": [
            {
                "ID": 1234,
                "ConnectionStatus": 0,
                "Modules": [
                    {"Index": 0, "Type": 9, "Name": "Gerät 0"},
                    {"Index": 0, "Type": 7, "Name": "WE0"},
                    {"Index": 1, "Type": 9, "Name": "Gerät 1"},
                ],
            }
        ]
    }

    with patch.object(api, "make_api_call", return_value=_json(devices)):
        api.get_devices()

    assert api.statistics_module_candidates == {"1234": [0, 1]}


def test_get_statistics_finds_module(api: WemPortalApi) -> None:
    """Test statistics are read from the first device module that answers."""
    api.data = {"1234": {}}
    api.statistics_module_candidates = {"1234": [0, 1]}
    refresh = _json({"GroupTypeDescriptions": [{"GroupType": 1, "Description": ""}]})
    stats = _json({"Unit": "kWh", "Values": [{"Value": 2981.72}, {"Value": 1751.31}]})

    with patch.object(
        api,
        "make_api_call",
        side_effect=[refresh, WemPortalError("invalid"), stats, stats, refresh, stats],
    ) as mock_call:
        api.get_statistics()
        # The next hourly fetch reuses the module instead of probing again
        api.last_statistics_fetch -= SLOW_UPDATE_INTERVAL
        api.get_statistics()

    reads = [
        (call.kwargs["data"]["ModuleType"], call.kwargs["data"]["ModuleIndex"], call.kwargs["data"]["Type"])
        for call in mock_call.call_args_list
        if "GroupType" in call.kwargs["data"]
    ]
    assert reads == [(9, 0, 3), (9, 1, 3), (9, 1, 3), (9, 1, 3)]
    assert api.statistics_modules == {"1234": 1}
    # The last entry of the yearly range is this year's running total
    assert api.data["1234"]["1234-Energy_1"]["value"] == 1751.31


def test_get_statistics_without_module(
    api: WemPortalApi, caplog: pytest.LogCaptureFixture
) -> None:
    """Test a device without a module that has statistics is logged once."""
    api.data = {"1234": {}}
    api.statistics_module_candidates = {"1234": [0]}
    refresh = _json({"GroupTypeDescriptions": [{"GroupType": 1, "Description": ""}]})

    with patch.object(
        api, "make_api_call", side_effect=[refresh, WemPortalError("invalid")]
    ):
        api.get_statistics()

    assert api.statistics_modules == {}
    assert "1234-Energy_1" not in api.data["1234"]
    assert "No device module returned statistics" in caplog.text


def test_get_statistics_unavailable_group(
    api: WemPortalApi, caplog: pytest.LogCaptureFixture
) -> None:
    """Test groups that never returned data are not warned about, unlike failing ones."""
    api.data = {"1234": {}}
    api.statistics_modules = {"1234": 1}
    refresh = _json(
        {
            "GroupTypeDescriptions": [
                {"GroupType": 1, "Description": ""},
                {"GroupType": 11, "Description": ""},
            ]
        }
    )
    stats = _json({"Unit": "kWh", "Values": [{"Value": 1751.31}]})
    invalid = WemPortalError("invalid")

    with (
        caplog.at_level(logging.WARNING),
        patch.object(
            api,
            "make_api_call",
            side_effect=[refresh, stats, invalid, refresh, invalid, invalid],
        ),
    ):
        api.get_statistics()
        assert caplog.records == []

        api.last_statistics_fetch -= SLOW_UPDATE_INTERVAL
        api.get_statistics()

    assert [record.getMessage() for record in caplog.records] == [
        "Failed to fetch Statistics for group 1 (device 1234): invalid"
    ]


def test_get_circuit_times(api: WemPortalApi) -> None:
    """Test a schedule is read with the job of its refresh request."""
    api.data = {"1234": {}}
    api.modules = {
        "1234": {
            (1, 2): {
                "Index": 1,
                "Type": 2,
                "Name": "HK1",
                "parameters": {
                    "Heizprogramm1": {"DataType": 6},
                    "Komfort": {"DataType": 3},
                },
            }
        }
    }
    refresh = MagicMock()
    refresh.json.return_value = {"JobID": 42}
    schedule = MagicMock()
    schedule.json.return_value = {"CircuitTimesDay": ["Mo"], "PossibleValues": [1]}

    with patch.object(
        api, "make_api_call", side_effect=[refresh, schedule]
    ) as mock_call:
        api.get_circuit_times("1234")

    payload = {"DeviceID": 1234, "ModuleIndex": 1, "ModuleType": 2, "ParameterID": "Heizprogramm1"}
    assert mock_call.call_args_list[0].kwargs["data"] == payload
    assert mock_call.call_args_list[1].kwargs["data"] == {**payload, "JobID": 42}
    sensor = api.data["1234"]["HK1-Heizprogramm1"]
    assert sensor["value"] == "Active"
    assert sensor["CircuitTimesDay"] == ["Mo"]
    assert sensor["PossibleValues"] == [1]
    assert sensor["DataType"] == 6
    assert sensor["platform"] == "sensor"


def test_get_statistics(api: WemPortalApi) -> None:
    """Test a statistics group becomes an energy sensor."""
    api.data = {"1234": {}}
    api.statistics_modules = {"1234": 1}
    refresh = MagicMock()
    refresh.json.return_value = {
        "GroupTypeDescriptions": [{"GroupType": 1, "Description": " "}]
    }
    stats = MagicMock()
    stats.json.return_value = {"Values": [{"Value": 1.0}, {"Value": 2.5}], "Unit": "kWh"}

    with patch.object(api, "make_api_call", side_effect=[refresh, stats]):
        api.get_statistics()

    assert api.data["1234"]["1234-Energy_1"] == {
        "friendlyName": "Heating Energy Yield",
        "ParameterID": "Energy_1",
        "unit": "kWh",
        "value": 2.5,
        "IsWriteable": False,
        "DataType": -1,
        "ModuleIndex": -1,
        "ModuleType": -1,
        "platform": "sensor",
        "icon": "mdi:lightning-bolt",
        "device_class": "energy",
        "state_class": "total_increasing",
    }


def test_fetch_data_web_mode() -> None:
    """Test web mode stores the scraped values without the scraper's cookie."""
    api = WemPortalApi("test", "test", config={"mode": "web"})
    scraped = {
        "friendlyName": "System - Außentemperatur",
        "value": 12.5,
        "unit": "°C",
        "platform": "sensor",
    }

    with patch.object(
        WemPortalScraper, "scrape", return_value=[{"system-temp": scraped, "cookie": {}}]
    ):
        data = api.fetch_data()

    assert list(data) == ["0000"]
    assert list(data["0000"]) == ["system-temp"]
    assert data["0000"]["system-temp"]["value"] == 12.5


DEVICES = {
    "Devices": [
        {
            "ID": 1234,
            "ConnectionStatus": 0,
            "Modules": [
                {"Index": 0, "Type": 9, "Name": "Gerät 0", "FWUVersion": "A.FWU"},
                {"Index": 0, "Type": 2, "Name": "HZK0", "FWUVersion": ""},
            ],
        }
    ]
}
PARAMETERS = {"Komfort": {"ParameterID": "Komfort", "DataType": 3}}
CACHE = {
    "1234": {
        "signature": ["0-2-", "0-9-A.FWU"],
        "parameters": {"0-9": {}, "0-2": PARAMETERS},
    }
}


def test_fetch_data_uses_parameter_cache() -> None:
    """Test cached parameter definitions are used instead of fetching them."""
    api = WemPortalApi("test", "test", parameter_cache=CACHE)

    with (
        patch.object(api, "api_login"),
        patch.object(api, "make_api_call", return_value=_json(DEVICES)) as mock_call,
        patch.object(api, "get_data"),
    ):
        api.fetch_data()

    assert mock_call.call_count == 1
    assert api.modules["1234"] == {
        (0, 2): {"Index": 0, "Type": 2, "Name": "HZK0", "parameters": PARAMETERS}
    }
    assert api.parameter_cache == CACHE


def test_fetch_data_refreshes_outdated_parameter_cache() -> None:
    """Test the parameter definitions are fetched again after a firmware update."""
    api = WemPortalApi(
        "test", "test", parameter_cache={"1234": {**CACHE["1234"], "signature": ["0-2-", "0-9-OLD.FWU"]}}
    )

    with (
        patch.object(api, "api_login"),
        patch.object(
            api,
            "make_api_call",
            side_effect=[
                _json(DEVICES),
                _json({"Parameters": []}),
                _json({"Parameters": list(PARAMETERS.values())}),
            ],
        ) as mock_call,
        patch.object(api, "get_data"),
        patch("custom_components.wemportal.wemportalapi.time.sleep"),
    ):
        api.fetch_data()

    assert mock_call.call_count == 3
    assert api.parameter_cache == CACHE
