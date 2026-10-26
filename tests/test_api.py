"""Test the WemPortal API."""
import asyncio
import logging
from collections.abc import AsyncGenerator, Generator
from unittest.mock import patch

import pytest
from aiohttp import ClientSession
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
)

from custom_components.wemportal.const import (
    API_EVENT_TYPE_READ_URL,
    API_LOGIN_URL,
    SLOW_UPDATE_INTERVAL,
)
from custom_components.wemportal.exceptions import ForbiddenError, WemPortalError
from custom_components.wemportal.scraper import WemPortalScraper
from custom_components.wemportal.wemportalapi import WemPortalApi

URL = "https://www.wemportal.com/app/CircuitTimes/Read"


@pytest.fixture(autouse=True)
def no_sleep() -> Generator[None]:
    """Skip the pauses between requests."""
    with patch("custom_components.wemportal.wemportalapi.asyncio.sleep"):
        yield


@pytest.fixture
async def session(aioclient_mock: AiohttpClientMocker) -> AsyncGenerator[ClientSession]:
    """Return a session whose requests are answered by the mocker."""
    session = aioclient_mock.create_session(asyncio.get_running_loop())
    yield session
    await session.close()


@pytest.fixture
def api(session: ClientSession) -> WemPortalApi:
    """Return a logged in API."""
    api = WemPortalApi("test", "test", session)
    api.valid_login = True
    return api


async def test_api_login_success(
    session: ClientSession, aioclient_mock: AiohttpClientMocker
) -> None:
    """Test successful API login."""
    aioclient_mock.post(API_LOGIN_URL, json={"Status": 0, "Message": "OK", "Version": "1.2"})
    api = WemPortalApi("test", "test", session)

    await api.api_login()

    assert api.valid_login is True
    assert api.api_version == "1.2"
    assert aioclient_mock.call_count == 1


async def test_api_login_failure(
    session: ClientSession, aioclient_mock: AiohttpClientMocker
) -> None:
    """Test API login failure resulting in ForbiddenError."""
    aioclient_mock.post(API_LOGIN_URL, status=403, json={"Status": 403, "Message": "Forbidden"})
    api = WemPortalApi("test", "test", session)

    with pytest.raises(ForbiddenError):
        await api.api_login()

    assert api.valid_login is False


async def test_make_api_call_error_details(
    api: WemPortalApi, aioclient_mock: AiohttpClientMocker
) -> None:
    """Test the HTTP error and server message end up in the raised error."""
    aioclient_mock.post(URL, status=500, json={"Status": 5, "Message": "Job not finished"})

    with pytest.raises(WemPortalError) as exc_info:
        await api.make_api_call(URL, data={"DeviceID": 1})

    assert "Request failed: 500" in str(exc_info.value)
    assert "internal status code: 5 and message: Job not finished" in str(
        exc_info.value
    )
    assert api.valid_login is True


async def test_make_api_call_auth_error_invalidates_login(
    api: WemPortalApi, aioclient_mock: AiohttpClientMocker
) -> None:
    """Test a session that stays expired after a retry forces a new login."""
    aioclient_mock.post(URL, status=401)

    with patch.object(api, "api_login"), pytest.raises(WemPortalError):
        await api.make_api_call(URL, data={"DeviceID": 1})

    assert api.valid_login is False


@pytest.mark.parametrize("status_code", [401, 403])
async def test_make_api_call_reauth_on_expired_session(
    api: WemPortalApi, aioclient_mock: AiohttpClientMocker, status_code: int
) -> None:
    """Test an expired session triggers a login and a retry."""
    aioclient_mock.post(URL, status=status_code)

    async def login() -> None:
        aioclient_mock.clear_requests()
        aioclient_mock.post(URL, json={"JobID": 42})

    with patch.object(api, "api_login", side_effect=login) as mock_login:
        assert await api.make_api_call(URL, data={"DeviceID": 1}) == {"JobID": 42}

    mock_login.assert_called_once()


async def test_get_parameters_unsupported_module(
    api: WemPortalApi, aioclient_mock: AiohttpClientMocker
) -> None:
    """Test a module the portal rejects with 400 is dropped."""
    aioclient_mock.post(API_EVENT_TYPE_READ_URL, status=400)
    api.data = {"1234": {"ConnectionStatus": 0}}
    api.modules = {"1234": {(0, 9): {"Index": 0, "Type": 9, "Name": "Gerät 0"}}}

    await api.get_parameters()

    assert api.modules == {"1234": {}}


async def test_circuit_times_fetched_hourly(api: WemPortalApi) -> None:
    """Test schedules are only fetched once per slow update interval."""
    api.data = {"1234": {}}
    api.modules = {"1234": {}}

    with (
        patch.object(
            api, "make_api_call", return_value={"ConnectionStatus": 0, "Modules": []}
        ),
        patch.object(api, "get_circuit_times") as mock_circuit_times,
        patch.object(api, "get_statistics"),
    ):
        await api.get_data()
        await api.get_data()
        assert mock_circuit_times.call_count == 1

        api.last_circuit_times_fetch -= SLOW_UPDATE_INTERVAL
        await api.get_data()

    assert mock_circuit_times.call_count == 2


async def test_parameter_data_failure_invalidates_login(api: WemPortalApi) -> None:
    """Test failing to fetch the values forces a new login next cycle."""
    api.data = {"1234": {}}
    api.modules = {"1234": {}}

    with (
        patch.object(
            api,
            "make_api_call",
            side_effect=[{"ConnectionStatus": 0}, WemPortalError("Server error")],
        ),
        patch.object(api, "get_circuit_times"),
        patch.object(api, "get_statistics"),
    ):
        await api.get_data()

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


async def test_get_devices_records_statistics_modules(api: WemPortalApi) -> None:
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

    with patch.object(api, "make_api_call", return_value=devices):
        await api.get_devices()

    assert api.statistics_module_candidates == {"1234": [0, 1]}


async def test_get_statistics_finds_module(api: WemPortalApi) -> None:
    """Test statistics are read from the first device module that answers."""
    api.data = {"1234": {}}
    api.statistics_module_candidates = {"1234": [0, 1]}
    refresh = {"GroupTypeDescriptions": [{"GroupType": 1, "Description": ""}]}
    stats = {"Unit": "kWh", "Values": [{"Value": 2981.72}, {"Value": 1751.31}]}

    with patch.object(
        api,
        "make_api_call",
        side_effect=[refresh, WemPortalError("invalid"), stats, stats, refresh, stats],
    ) as mock_call:
        await api.get_statistics()
        # The next hourly fetch reuses the module instead of probing again
        api.last_statistics_fetch -= SLOW_UPDATE_INTERVAL
        await api.get_statistics()

    reads = [
        (call.kwargs["data"]["ModuleType"], call.kwargs["data"]["ModuleIndex"], call.kwargs["data"]["Type"])
        for call in mock_call.call_args_list
        if "GroupType" in call.kwargs["data"]
    ]
    assert reads == [(9, 0, 3), (9, 1, 3), (9, 1, 3), (9, 1, 3)]
    assert api.statistics_modules == {"1234": 1}
    # The last entry of the yearly range is this year's running total
    assert api.data["1234"]["1234-Energy_1"]["value"] == 1751.31


async def test_get_statistics_without_module(
    api: WemPortalApi, caplog: pytest.LogCaptureFixture
) -> None:
    """Test a device without a module that has statistics is logged once."""
    api.data = {"1234": {}}
    api.statistics_module_candidates = {"1234": [0]}
    refresh = {"GroupTypeDescriptions": [{"GroupType": 1, "Description": ""}]}

    with patch.object(
        api, "make_api_call", side_effect=[refresh, WemPortalError("invalid")]
    ):
        await api.get_statistics()

    assert api.statistics_modules == {}
    assert "1234-Energy_1" not in api.data["1234"]
    assert "No device module returned statistics" in caplog.text


async def test_get_statistics_unavailable_group(
    api: WemPortalApi, caplog: pytest.LogCaptureFixture
) -> None:
    """Test groups that never returned data are not warned about, unlike failing ones."""
    api.data = {"1234": {}}
    api.statistics_modules = {"1234": 1}
    refresh = {
        "GroupTypeDescriptions": [
            {"GroupType": 1, "Description": ""},
            {"GroupType": 11, "Description": ""},
        ]
    }
    stats = {"Unit": "kWh", "Values": [{"Value": 1751.31}]}
    invalid = WemPortalError("invalid")

    with (
        caplog.at_level(logging.WARNING),
        patch.object(
            api,
            "make_api_call",
            side_effect=[refresh, stats, invalid, refresh, invalid, invalid],
        ),
    ):
        await api.get_statistics()
        assert caplog.records == []

        api.last_statistics_fetch -= SLOW_UPDATE_INTERVAL
        await api.get_statistics()

    assert [record.getMessage() for record in caplog.records] == [
        "Failed to fetch Statistics for group 1 (device 1234): invalid"
    ]


async def test_get_circuit_times(api: WemPortalApi) -> None:
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
    refresh = {"JobID": 42}
    schedule = {"CircuitTimesDay": ["Mo"], "PossibleValues": [1]}

    with patch.object(
        api, "make_api_call", side_effect=[refresh, schedule]
    ) as mock_call:
        await api.get_circuit_times("1234")

    payload = {"DeviceID": 1234, "ModuleIndex": 1, "ModuleType": 2, "ParameterID": "Heizprogramm1"}
    assert mock_call.call_args_list[0].kwargs["data"] == payload
    assert mock_call.call_args_list[1].kwargs["data"] == {**payload, "JobID": 42}
    sensor = api.data["1234"]["HK1-Heizprogramm1"]
    assert sensor["value"] == "Active"
    assert sensor["CircuitTimesDay"] == ["Mo"]
    assert sensor["PossibleValues"] == [1]
    assert sensor["DataType"] == 6
    assert sensor["platform"] == "sensor"


async def test_get_statistics(api: WemPortalApi) -> None:
    """Test a statistics group becomes an energy sensor."""
    api.data = {"1234": {}}
    api.statistics_modules = {"1234": 1}
    refresh = {"GroupTypeDescriptions": [{"GroupType": 1, "Description": " "}]}
    stats = {"Values": [{"Value": 1.0}, {"Value": 2.5}], "Unit": "kWh"}

    with patch.object(api, "make_api_call", side_effect=[refresh, stats]):
        await api.get_statistics()

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


async def test_fetch_data_web_mode(session: ClientSession) -> None:
    """Test web mode stores the scraped values."""
    api = WemPortalApi("test", "test", session, config={"mode": "web"})
    scraped = {
        "friendlyName": "System - Außentemperatur",
        "value": 12.5,
        "unit": "°C",
        "platform": "sensor",
    }

    with patch.object(WemPortalScraper, "scrape", return_value=[{"system-temp": scraped}]):
        data = await api.fetch_data()

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


async def test_fetch_data_uses_parameter_cache(session: ClientSession) -> None:
    """Test cached parameter definitions are used instead of fetching them."""
    api = WemPortalApi("test", "test", session, parameter_cache=CACHE)

    with (
        patch.object(api, "api_login"),
        patch.object(api, "make_api_call", return_value=DEVICES) as mock_call,
        patch.object(api, "get_data"),
    ):
        await api.fetch_data()

    assert mock_call.call_count == 1
    assert api.modules["1234"] == {
        (0, 2): {"Index": 0, "Type": 2, "Name": "HZK0", "parameters": PARAMETERS}
    }
    assert api.parameter_cache == CACHE
    assert not api.parameter_cache_changed


async def test_fetch_data_refreshes_outdated_parameter_cache(
    session: ClientSession,
) -> None:
    """Test the parameter definitions are fetched again after a firmware update."""
    api = WemPortalApi(
        "test",
        "test",
        session,
        parameter_cache={"1234": {**CACHE["1234"], "signature": ["0-2-", "0-9-OLD.FWU"]}},
    )

    with (
        patch.object(api, "api_login"),
        patch.object(
            api,
            "make_api_call",
            side_effect=[
                DEVICES,
                {"Parameters": []},
                {"Parameters": list(PARAMETERS.values())},
            ],
        ) as mock_call,
        patch.object(api, "get_data"),
    ):
        await api.fetch_data()

    assert mock_call.call_count == 3
    assert api.parameter_cache == CACHE
    assert api.parameter_cache_changed


async def test_get_data_without_slow_data(api: WemPortalApi) -> None:
    """Test schedules and statistics can be left out."""
    api.data = {"1234": {}}
    api.modules = {"1234": {}}

    with (
        patch.object(
            api, "make_api_call", return_value={"ConnectionStatus": 0, "Modules": []}
        ),
        patch.object(api, "get_circuit_times") as mock_circuit_times,
        patch.object(api, "get_statistics") as mock_statistics,
    ):
        await api.get_data(include_slow=False)

    mock_circuit_times.assert_not_called()
    mock_statistics.assert_not_called()
    # Not fetching them now must not postpone the next fetch
    assert api.last_circuit_times_fetch == 0.0
