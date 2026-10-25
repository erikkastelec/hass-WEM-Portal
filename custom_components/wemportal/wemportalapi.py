"""
Weishaupt webscraping and API library
"""


import copy
import time

from bs4 import BeautifulSoup
import requests as reqs
from homeassistant.const import CONF_SCAN_INTERVAL
from .mapper import WemPortalDataMapper
from .scraper import WemPortalScraper
from .translations import friendly_name_mapper, translate
from .exceptions import (
    AuthError,
    ForbiddenError,
    UnknownAuthError,
    WemPortalError,
    ExpiredSessionError,
    ParameterChangeError,
    ServerError,
)

from .const import (
    _LOGGER,
    API_DATA_ACCESS_READ_URL,
    API_DATA_ACCESS_WRITE_URL,
    API_DEVICE_READ_URL,
    API_EVENT_TYPE_READ_URL,
    API_LOGIN_URL,
    API_REFRESH_URL,
    API_DEVICE_STATUS_READ_URL,
    API_CIRCUIT_TIMES_REFRESH_URL,
    API_CIRCUIT_TIMES_READ_URL,
    API_STATISTICS_REFRESH_URL,
    API_STATISTICS_READ_URL,
    CONF_LANGUAGE,
    CONF_MODE,
    DATA_GATHERING_ERROR,
    DEFAULT_CONF_LANGUAGE_VALUE,
    DEFAULT_CONF_MODE_VALUE,
    DEFAULT_CONF_SCAN_INTERVAL_VALUE,
    SLOW_UPDATE_INTERVAL,
    STATISTICS_MODULE_TYPE,
    WEB_LOGIN_URL,
)

# Used when the portal doesn't return a description for a statistics group
STATISTICS_FALLBACK_NAMES = {
    1: "Heating Energy Yield",
    2: "Hot Water Energy Yield",
    3: "Cooling Energy Yield",
    4: "Total Energy Yield",
    5: "Power Consumption Heating",
    6: "Power Consumption Hot Water",
    7: "Power Consumption Cooling",
    8: "Total Power Consumption",
}


def _virtual_sensor(friendly_name, parameter_id, value, icon, unit=None, **extra):
    """Return the data of a sensor that isn't a WEM Portal parameter."""
    return {
        "friendlyName": friendly_name,
        "ParameterID": parameter_id,
        "unit": unit,
        "value": value,
        "IsWriteable": False,
        "DataType": -1,
        "ModuleIndex": -1,
        "ModuleType": -1,
        "platform": "sensor",
        "icon": icon,
        **extra,
    }


def _module_signature(device_modules):
    """Return what identifies the modules of a device, including their firmware."""
    return sorted(
        f"{module['Index']}-{module['Type']}-{module.get('FWUVersion', '')}"
        for module in device_modules
    )


class WemPortalApi:
    """Wrapper class for Weishaupt WEM Portal"""

    def __init__(
        self, username, password, config=None, existing_data=None, parameter_cache=None
    ) -> None:
        if config is None:
            config = {}
        self.data = copy.deepcopy(existing_data) if existing_data else {}
        # Parameter definitions per device, saved to disk as fetching them takes about 6 s per module
        self.parameter_cache = copy.deepcopy(parameter_cache) if parameter_cache else {}
        self.device_modules: dict[str, list[dict]] = {}
        self.username = username
        self.password = password
        self.mode = config.get(CONF_MODE, DEFAULT_CONF_MODE_VALUE)
        self.scan_interval = config.get(CONF_SCAN_INTERVAL, DEFAULT_CONF_SCAN_INTERVAL_VALUE)
        self.valid_login = False
        self.language = config.get(CONF_LANGUAGE, DEFAULT_CONF_LANGUAGE_VALUE)
        self.session = None
        self.modules = None
        self.last_scraping_update = None
        # Headers used for all API calls
        self.headers = {
            "User-Agent": "WeishauptWEMApp",
            "X-Api-Version": "3.1.3.0",
            "Accept": "*/*",
            "Host": "www.wemportal.com"
        }
        self.scraping_mapper = {}
        self.last_statistics_fetch = 0.0
        # Indexes of the device modules (Type 9) per device, and the one that has the statistics
        self.statistics_module_candidates: dict[str, list[int]] = {}
        self.statistics_modules: dict[str, int] = {}
        # Statistics groups per device that returned data, as not every listed group is available
        self.statistics_groups: dict[str, set[int]] = {}
        self.last_circuit_times_fetch = 0.0
        # Requests that failed last time, so repeated failures are only logged once
        self.failing_requests: set[str] = set()
        self.api_version = None

    def fetch_data(self, enabled_devices=None):
        try:
            if self.mode != "web":
                # Login and get device info
                if not self.valid_login:
                    self.api_login()
                # Fetch device and parameter data only at start, or recover missing metadata
                if self.modules is None:
                    self.get_devices()
                    self._restore_parameters()
                    self.get_parameters()
                    self._update_parameter_cache()
                elif any(
                    "parameters" not in module
                    for modules in self.modules.values()
                    for module in modules.values()
                ):
                    _LOGGER.info("Attempting to recover missing parameter definitions...")
                    self.get_parameters()

            if self.mode == "web":
                self._merge_webscraping_data(next(iter(self.data), "0000"), self.fetch_webscraping_data())
            elif self.mode == "api":
                self.get_data(enabled_devices)
            else:
                # Scrape once per scan interval, with 10 s of slack for the poll timing
                if (
                    self.last_scraping_update is None
                    or time.monotonic() - self.last_scraping_update + 10 > self.scan_interval
                ):
                    try:
                        self._merge_webscraping_data(next(iter(self.data), "0000"), self.fetch_webscraping_data())
                        self.last_scraping_update = time.monotonic()
                    except Exception as exc:
                        # Don't raise, so the API can still fetch the bulk of the data
                        _LOGGER.warning("Web scraper failed this cycle. Falling back to API only. Error: %s", exc)

                # The API always runs as a resilient fallback
                self.get_data(enabled_devices)

            return self.data

        except WemPortalError:
            raise
        except Exception as exc:
            # Wrap unexpected errors so the coordinator treats them as a failed update
            raise WemPortalError("Unexpected error occurred while fetching data") from exc

    def _merge_webscraping_data(self, device_id, webscraping_data):
        if str(device_id) not in self.data:
            self.data[str(device_id)] = {}

        for key, new_val in webscraping_data.items():
            if isinstance(new_val, dict):
                if "friendlyName" in new_val:
                    new_val["friendlyName"] = translate(self.language, new_val["friendlyName"])
                
                # Preserve the old unit if the current scrape is missing it (e.g. value is "--")
                # This prevents Home Assistant from complaining about unit changes.
                if new_val.get("unit") is None:
                    old_val = self.data[str(device_id)].get(key)
                    if isinstance(old_val, dict) and old_val.get("unit") is not None:
                        new_val["unit"] = old_val.get("unit")
                        
            self.data[str(device_id)][key] = new_val

    def fetch_webscraping_data(self):
        """Scrape the expert page of the WEM Portal."""
        try:
            data = WemPortalScraper(self.username, self.password).scrape()[0]
        except AuthError as exc:
            raise AuthError(
                "AuthenticationError: Could not login with provided username and password. "
                "Check if your config contains the right credentials"
            ) from exc

        # The scraper logs in on every run, so its session cookie isn't reused
        data.pop("cookie", None)
        return data

    def api_login(self):
        payload = {
            "Name": self.username,
            "PasswordUTF8": self.password,
            "AppID": "com.weishaupt.wemapp",
            "AppVersion": "2.0.2",
            "ClientOS": "Android",
        }
        if self.session is not None:
            self.session.close()
        self.session = reqs.Session()
        self.session.cookies.clear()
        self.session.headers.update(self.headers)
        try:
            response = self.session.post(
                API_LOGIN_URL,
                data=payload,
            )
            response.raise_for_status()
            
            # Verify the response is actually valid JSON and successful
            response_data = response.json()
            if response_data.get("Status") != 0:
                raise AuthError(f"Login failed: Server returned {response_data}")
                
            self.api_version = response_data.get("Version")
            _LOGGER.debug("API login successful for %s", self.username)
            self.valid_login = True
            
        except ValueError as exc: # Catches JSONDecodeError if response is HTML
            _LOGGER.warning("API login failed for %s. Received HTML instead of JSON.", self.username)
            self.valid_login = False
            raise WemPortalError("API login failed: received HTML instead of JSON (Possible rate limit or WAF block)") from exc
        except reqs.exceptions.HTTPError as exc:
            _LOGGER.warning("API login failed for %s with HTTPError.", self.username)
            self.valid_login = False
            response_status, response_message = self.get_response_details(response)
            if response.status_code == 400:
                raise AuthError(
                    f"Authentication Error: Check if your login credentials are correct. Received response code: {response.status_code}, response: {response.content}. Server returned internal status code: {response_status} and message: {response_message}"
                ) from exc
            elif response.status_code == 403:
                raise ForbiddenError(
                    f"WemPortal forbidden error: Server returned internal status code: {response_status} and message: {response_message}"
                ) from exc
            elif response.status_code == 500:
                raise ServerError(
                    f"WemPortal server error: Server returned internal status code: {response_status} and message: {response_message}"
                ) from exc
            else:
                raise UnknownAuthError(
                    f"Authentication Error: Encountered an unknown authentication error. Received response code: {response.status_code}, response: {response.content}. Server returned internal status code: {response_status} and message: {response_message}"
                ) from exc


    def web_login(self):
        """
        Logs into the WEM Portal web interface by mimicking browser behavior.
        Args:
            username (str): The user's username (email).
            password (str): The user's password.
        Returns:
            dict: Session cookies for the authenticated session.
        Raises:
            AuthError: If the login credentials are invalid.
            ForbiddenError: If access is forbidden.
            UnknownAuthError: For other unknown login errors.
        """
        session = reqs.Session()
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Accept-Language": "de,en;q=0.9",
        }

        # Step 1: Fetch the login page
        try:
            initial_response = session.get(WEB_LOGIN_URL, headers=headers)
            initial_response.raise_for_status()
        except reqs.exceptions.HTTPError as exc:
            raise UnknownAuthError("Failed to load the login page.") from exc

        # Step 2: Parse the login page and extract hidden form fields
        soup = BeautifulSoup(initial_response.text, "html.parser")
        form_data = {}
        for input_tag in soup.find_all("input"):
            if input_tag.get("type") == "hidden" and input_tag.get("name"):
                form_data[input_tag["name"]] = input_tag.get("value", "")

        # Add username and password to the form data
        form_data["ctl00$content$tbxUserName"] = self.username
        form_data["ctl00$content$tbxPassword"] = self.password
        form_data["ctl00$content$btnLogin"] = "Anmelden"  # Login button value

        # Step 3: Submit the login form
        try:
            response = session.post(
                WEB_LOGIN_URL,
                data=form_data,
                headers={
                    **headers,
                    "Content-Type": "application/x-www-form-urlencoded",
                },
            )
            response.raise_for_status()

            # Step 4: Check if login was successful
            if "ctl00_btnLogout" in response.text:
                _LOGGER.debug("WEB login successful for %s", self.username)
                return
            else:
                raise AuthError("Login failed: Invalid username or password.")
        except reqs.exceptions.HTTPError as exc:
            if response.status_code == 403:
                raise ForbiddenError("Access forbidden during login.") from exc
            raise UnknownAuthError("Failed to submit the login form.") from exc

    def get_response_details(self, response: reqs.Response):
        server_status = ""
        server_message = ""
        # A requests.Response is falsy for 4xx/5xx, which are the responses we need here
        if response is not None:
            try:
                response_data = response.json()
                _LOGGER.debug(response_data)
                # Status we get back from server
                server_status = response_data["Status"]
                server_message = response_data["Message"]
            except (KeyError, ValueError):
                pass
        return server_status, server_message


    def make_api_call(
        self, url: str, headers=None, data=None, do_retry=True, delay=5
    ) -> reqs.Response:
        attempts = 2 if do_retry else 1

        for attempt in range(attempts):
            time.sleep(1)  # Wait 1 sec between requests to be graceful to the API.
            current_headers = headers or self.headers.copy()
            response = None

            try:
                if not data:
                    _LOGGER.debug("Sending GET request to %s with headers: %s", url, current_headers)
                    response = self.session.get(url, headers=current_headers, timeout=10)
                else:
                    _LOGGER.debug("Sending POST request to %s with headers: %s and data: %s", url, current_headers, data)
                    response = self.session.post(url, headers=current_headers, json=data, timeout=10)

                response.raise_for_status()

                # Check for stealthy session expiration (HTML redirect)
                if "Account/Login" in response.url:
                    raise ExpiredSessionError("Redirected to Account/Login")

                _LOGGER.debug(response)
                return response

            except (reqs.exceptions.RequestException, ExpiredSessionError) as exc:
                is_auth_error = isinstance(exc, ExpiredSessionError) or (
                    isinstance(exc, reqs.exceptions.RequestException)
                    and response is not None
                    and response.status_code in (401, 403)
                )

                if is_auth_error and attempt < attempts - 1:
                    _LOGGER.info("Session expired for %s. Re-authenticating...", url)
                    self.api_login()
                    time.sleep(delay)
                    continue  # Loop back around and retry

                # If we're out of retries or it's a completely different error:
                server_status, server_message = self.get_response_details(response)
                
                # Log in with a fresh session next cycle. A failing optional endpoint
                # (schedules, statistics) doesn't mean the session is broken.
                if is_auth_error:
                    self.valid_login = False

                raise WemPortalError(
                    f"{DATA_GATHERING_ERROR} Request failed: {exc}. Server returned internal status code: {server_status} and message: {server_message}"
                ) from exc

    def get_devices(self):
        _LOGGER.debug("Fetching api device data")
        self.modules = {}
        self.data = {}
        data = self.make_api_call(API_DEVICE_READ_URL, do_retry=True).json()

        for device in data["Devices"]:
            device_id_str = str(device["ID"])
            self.data[device_id_str] = {}
            self.modules[device_id_str] = {}
            for module in device["Modules"]:
                self.modules[device_id_str][(module["Index"], module["Type"])] = {
                    "Index": module["Index"],
                    "Type": module["Type"],
                    "Name": module["Name"],
                }
            self.data[device_id_str]["ConnectionStatus"] = device["ConnectionStatus"]
            self.device_modules[device_id_str] = device["Modules"]
            self.statistics_module_candidates[device_id_str] = [
                module["Index"]
                for module in device["Modules"]
                if module["Type"] == STATISTICS_MODULE_TYPE
            ]

    def get_parameters(self):
        assert self.modules is not None
        for device_id, device_data in self.data.items():
            if device_data["ConnectionStatus"] != 0:
                continue
            _LOGGER.debug("Fetching api parameters data for device %s", device_id)
            _LOGGER.debug("Modules of device %s: %s", device_id, self.modules[device_id])
            delete_candidates = []
            forbidden_count = 0
            for values in self.modules[device_id].values():
                # Check if parameters are already cached
                if "parameters" in values and values["parameters"]:
                    _LOGGER.debug(
                        "Parameters for device %s, index %s, and type %s are already cached.",
                        device_id, values["Index"], values["Type"]
                    )
                    continue
                data = {
                    "DeviceID": int(device_id),
                    "ModuleIndex": values["Index"],
                    "ModuleType": values["Type"],
                }
                try:
                    time.sleep(5)
                    response = self.make_api_call(
                        API_EVENT_TYPE_READ_URL, data=data, do_retry=False
                    )
                except WemPortalError as exc:
                    if isinstance(exc.__cause__, reqs.exceptions.HTTPError):
                        status_code = exc.__cause__.response.status_code
                        if status_code == 403:
                            forbidden_count += 1
                            if forbidden_count >= 3:
                                _LOGGER.error(
                                    "Rate limited (403) three times while fetching parameters "
                                    "for device %s. Aborting.",
                                    device_id
                                )
                                raise ForbiddenError("Rate limited during get_parameters") from exc
                            
                            _LOGGER.warning(
                                "Rate limit warning (403) for device %s module %s. Strike %s of 3.",
                                device_id,
                                values["Index"],
                                forbidden_count
                            )
                            continue
                        elif status_code == 400:
                            _LOGGER.warning(
                                "Module index %s type %s is unsupported by WEM Portal. "
                                "Deleting from cache.",
                                values["Index"],
                                values["Type"]
                            )
                            delete_candidates.append((values["Index"], values["Type"]))
                            continue
                    raise
                parameters = {}
                try:
                    for parameter in response.json()["Parameters"]:
                        parameters[parameter["ParameterID"]] = parameter
                    if not parameters:
                        delete_candidates.append((values["Index"], values["Type"]))
                    else:
                        self.modules[device_id][(values["Index"], values["Type"])][
                            "parameters"
                        ] = parameters
                except KeyError:
                    _LOGGER.warning(
                        "An error occurred while gathering parameters data for module %s. Skipping this module. "
                        "If this problem persists, open an issue at "
                        "https://github.com/erikkastelec/hass-WEM-Portal/issues",
                        values
                    )
                    continue
            for key in delete_candidates:
                del self.modules[device_id][key]

    def _restore_parameters(self):
        """Use the cached parameter definitions of devices whose modules didn't change."""
        for device_id, device_modules in self.device_modules.items():
            cached = self.parameter_cache.get(device_id)
            if cached is None or cached["signature"] != _module_signature(device_modules):
                continue
            _LOGGER.debug("Using cached parameter definitions for device %s", device_id)
            for key, parameters in cached["parameters"].items():
                module_key = tuple(int(part) for part in key.split("-"))
                if module_key not in self.modules[device_id]:
                    continue
                if parameters:
                    self.modules[device_id][module_key]["parameters"] = parameters
                else:
                    # Modules without parameters are removed, as when they are fetched
                    del self.modules[device_id][module_key]

    def _update_parameter_cache(self):
        """Remember the parameter definitions of every module that was resolved."""
        for device_id, device_modules in self.device_modules.items():
            # Parameters aren't fetched for offline devices, so keep what was cached
            if self.data[device_id]["ConnectionStatus"] != 0:
                continue
            parameters = {}
            for module in device_modules:
                module_key = (module["Index"], module["Type"])
                current = self.modules[device_id].get(module_key)
                if current is None:
                    parameters[f"{module_key[0]}-{module_key[1]}"] = {}
                elif current.get("parameters"):
                    parameters[f"{module_key[0]}-{module_key[1]}"] = current["parameters"]
            self.parameter_cache[device_id] = {
                "signature": _module_signature(device_modules),
                "parameters": parameters,
            }

    def change_value(
        self,
        device_id,
        parameter_id,
        module_index,
        module_type,
        numeric_value,
    ):
        """POST request to API to change a specific value"""
        _LOGGER.debug("Changing value for %s", parameter_id)

        data = {
            "DeviceID": int(device_id),
            "Modules": [
                {
                    "ModuleIndex": int(module_index),
                    "ModuleType": int(module_type),
                    "Parameters": [
                        {
                            "ParameterID": parameter_id,
                            "NumericValue": float(numeric_value),
                        }
                    ],
                }
            ],
        }

        try:
            self.make_api_call(
                API_DATA_ACCESS_WRITE_URL,
                data=data,
                do_retry=True
            )
        except Exception as exc:
            raise ParameterChangeError(
                f"Error changing parameter {parameter_id} value"
            ) from exc

    # Refresh data and retrieve new data
    def get_data(self, enabled_devices=None):
        _LOGGER.debug("Fetching fresh api data. enabled_devices=%s, self.data.keys()=%s", enabled_devices, list(self.data.keys()))
        target_devices = enabled_devices if enabled_devices else list(self.data.keys())
        _LOGGER.debug("Computed target_devices=%s", target_devices)
        now = time.time()
        fetch_circuit_times = now - self.last_circuit_times_fetch >= SLOW_UPDATE_INTERVAL
        if fetch_circuit_times:
            self.last_circuit_times_fetch = now
        for device_id in target_devices:
            if device_id not in self.data:
                continue

            # 1. Fetch Device Status First
            try:
                status_response = self.make_api_call(
                    API_DEVICE_STATUS_READ_URL,
                    data={"DeviceID": int(device_id)},
                    do_retry=True
                ).json()

                status_map = {0: "online", 7: "wrong_secret", 8: "busy", 50: "offline"}
                conn_status = status_map.get(status_response.get("ConnectionStatus", -1), "unknown")
                errors = status_response.get("Errors", [])
                error_msg = ", ".join(str(e) for e in errors) if errors else "None"

                self.data[device_id][f"{device_id}-ConnectionStatus"] = _virtual_sensor(
                    "Connection Status", "ConnectionStatus", conn_status, "mdi:network"
                )
                self.data[device_id][f"{device_id}-HasErrors"] = _virtual_sensor(
                    "Has Errors", "HasErrors", "Yes" if errors else "No", "mdi:alert"
                )
                self.data[device_id][f"{device_id}-ErrorMessages"] = _virtual_sensor(
                    "Error Messages", "ErrorMessages", error_msg[:255], "mdi:message-alert"
                )

                self._log_request_success(f"device status (device {device_id})")

                if conn_status != "online":
                    _LOGGER.warning("Device %s is %s. Skipping data polling.", device_id, conn_status)
                    continue

            except Exception as exc:
                self._log_request_failure(f"device status (device {device_id})", exc)

            # 2. Proceed with data fetch
            try:
                data = {
                    "DeviceID": int(device_id),
                    "Modules": [
                        {
                            "ModuleIndex": module["Index"],
                            "ModuleType": module["Type"],
                            "Parameters": [
                                {"ParameterID": parameter}
                                for parameter in module["parameters"].keys()
                            ],
                        }
                        for module in self.modules[device_id].values()
                        if "parameters" in module and module["parameters"]
                    ],
                }
            except KeyError as exc:
                _LOGGER.debug("%s: %s", DATA_GATHERING_ERROR, self.modules[device_id])
                raise WemPortalError(DATA_GATHERING_ERROR) from exc

            try:
                self.make_api_call(
                    API_REFRESH_URL,
                    data=data,
                )
                time.sleep(5)
                values = self.make_api_call(
                    API_DATA_ACCESS_READ_URL,
                    data=data,
                    do_retry=True
                ).json()
                WemPortalDataMapper.process_api_values(
                    device_id=device_id,
                    values_json=values,
                    modules_dict=self.modules,
                    language=self.language,
                    scraping_mapper=self.scraping_mapper,
                    mode=self.mode,
                    api_data=self.data,
                )
                self._log_request_success(f"parameter data (device {device_id})")
            except Exception as exc:
                self._log_request_failure(f"parameter data (device {device_id})", exc)
                # Errors are swallowed here, so recover a possibly broken session by
                # logging in again next cycle
                self.valid_login = False

            # 3. Fetch Heating Schedules (Rate limited)
            if fetch_circuit_times:
                self.get_circuit_times(device_id)

        # 4. Fetch Energy Statistics (Rate limited)
        self.get_statistics(enabled_devices)

    def get_circuit_times(self, device_id):
        """Fetch the heating schedules (DataType == 6) of a device."""
        programs = [
            (module, param_id)
            for module in self.modules[device_id].values()
            for param_id, param_data in module.get("parameters", {}).items()
            if param_data.get("DataType") == 6  # WemDataType.PROGRAM
        ]
        for module, param_id in programs:
            request = f"CircuitTimes for {param_id} (device {device_id})"
            payload = {
                "DeviceID": int(device_id),
                "ModuleIndex": module["Index"],
                "ModuleType": module["Type"],
                "ParameterID": param_id,
            }
            try:
                job_id = self.make_api_call(
                    API_CIRCUIT_TIMES_REFRESH_URL, data=payload, do_retry=True
                ).json().get("JobID")
                if job_id is None:
                    continue

                time.sleep(2)  # Give backend time to build the schedule payload
                schedule_resp = self.make_api_call(
                    API_CIRCUIT_TIMES_READ_URL,
                    data={**payload, "JobID": job_id},
                    do_retry=True
                ).json()
            except Exception as exc:
                self._log_request_failure(request, exc)
                continue

            self._log_request_success(request)
            sensor = self.data[device_id].setdefault(
                f"{module['Name']}-{param_id}",
                {
                    "friendlyName": translate(self.language, friendly_name_mapper(param_id)),
                    "ParameterID": param_id,
                    "unit": None,
                    "IsWriteable": False,
                    "DataType": 6,
                    "ModuleIndex": module["Index"],
                    "ModuleType": module["Type"],
                    "platform": "sensor",
                    "icon": "mdi:calendar-clock",
                },
            )
            sensor["CircuitTimesDay"] = schedule_resp.get("CircuitTimesDay", [])
            sensor["PossibleValues"] = schedule_resp.get("PossibleValues", [])
            sensor["value"] = "Active"

    def get_statistics(self, enabled_devices=None):
        """Fetch historical statistics from the API, rate limited to once per hour."""
        now = time.time()
        if now - self.last_statistics_fetch < SLOW_UPDATE_INTERVAL:
            return
            
        self.last_statistics_fetch = now
        _LOGGER.debug("Fetching statistics data")
        
        target_devices = enabled_devices if enabled_devices else list(self.data.keys())
        for device_id in target_devices:
            if device_id not in self.data:
                continue
            try:
                refresh_resp = self.make_api_call(
                    API_STATISTICS_REFRESH_URL,
                    data={"DeviceID": int(device_id)},
                    do_retry=True
                ).json()
                _LOGGER.debug("Statistics refresh response for device %s: %s", device_id, refresh_resp)

                group_types = refresh_resp.get("GroupTypeDescriptions", [])
                if not group_types:
                    continue
                module_index = self._find_statistics_module(device_id, group_types[0].get("GroupType"))
                if module_index is None:
                    self._log_request_failure(
                        f"Statistics (device {device_id})",
                        WemPortalError("No device module returned statistics"),
                    )
                    continue

                for group in group_types:
                    group_id = group.get("GroupType")
                    group_name = group.get("Description")
                    if not group_name or not group_name.strip():
                        group_name = STATISTICS_FALLBACK_NAMES.get(group_id, f"Energy {group_id}")
                    else:
                        translated_group = translate(self.language, group_name)
                        if "energy" not in translated_group.lower():
                            group_name = f"{translated_group} Energy"
                        else:
                            group_name = translated_group
                    
                    request = f"Statistics for group {group_id} (device {device_id})"

                    try:
                        stats_resp = self._read_statistics(device_id, module_index, group_id)
                        
                        self._log_request_success(request)
                        self.statistics_groups.setdefault(device_id, set()).add(group_id)
                        values = stats_resp.get("Values", [])
                        if not values:
                            continue

                        # The last entry is this year's running total
                        sensor_name = f"Energy_{group_id}"
                        self.data[device_id][f"{device_id}-{sensor_name}"] = _virtual_sensor(
                            group_name,
                            sensor_name,
                            values[-1].get("Value", 0.0),
                            "mdi:lightning-bolt",
                            unit=stats_resp.get("Unit", "kWh"),
                            device_class="energy",
                            state_class="total_increasing",
                        )

                    except Exception as exc:
                        if group_id in self.statistics_groups.get(device_id, set()):
                            self._log_request_failure(request, exc)
                        else:
                            _LOGGER.debug("Failed to fetch %s: %s", request, exc)

            except Exception as exc:
                self._log_request_failure(f"Statistics (device {device_id})", exc)

    def _read_statistics(self, device_id, module_index, group_id):
        """Read the yearly statistics of a group from a device module."""
        time.sleep(2)  # Avoid hammering the API
        return self.make_api_call(
            API_STATISTICS_READ_URL,
            headers={"X-Api-Version": "2.0.0.0"},
            data={
                "DeviceID": int(device_id),
                "ModuleType": STATISTICS_MODULE_TYPE,
                "ModuleIndex": module_index,
                "GroupType": group_id,
                # Yearly range: day and month lists end in placeholders for periods that aren't over
                "Type": 3,
            },
            do_retry=True,
        ).json()

    def _find_statistics_module(self, device_id, group_id):
        """Return the index of the device module that has the statistics, if any."""
        # Which device module has them differs per installation, so try each once
        if device_id not in self.statistics_modules:
            for module_index in self.statistics_module_candidates.get(device_id, []):
                try:
                    self._read_statistics(device_id, module_index, group_id)
                except WemPortalError as exc:
                    _LOGGER.debug("Device module %s has no statistics: %s", module_index, exc)
                    continue
                self.statistics_modules[device_id] = module_index
                break
        return self.statistics_modules.get(device_id)

    def _log_request_failure(self, request: str, exc: Exception) -> None:
        """Log a failed request as a warning once, then as debug while it keeps failing."""
        if request in self.failing_requests:
            _LOGGER.debug("Failed to fetch %s: %s", request, exc)
            return
        self.failing_requests.add(request)
        _LOGGER.warning("Failed to fetch %s: %s", request, exc)

    def _log_request_success(self, request: str) -> None:
        """Log once that a previously failing request works again."""
        if request in self.failing_requests:
            self.failing_requests.discard(request)
            _LOGGER.info("Fetching %s works again", request)
