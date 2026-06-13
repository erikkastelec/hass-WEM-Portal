"""
Weishaupt webscraping and API library
"""


import copy
import time
from datetime import datetime, timedelta

from bs4 import BeautifulSoup
import requests as reqs
from homeassistant.const import CONF_SCAN_INTERVAL
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
    CONF_SCAN_INTERVAL_API,
    DATA_GATHERING_ERROR,
    DEFAULT_CONF_LANGUAGE_VALUE,
    DEFAULT_CONF_MODE_VALUE,
    DEFAULT_CONF_SCAN_INTERVAL_API_VALUE,
    DEFAULT_CONF_SCAN_INTERVAL_VALUE,
)


class WemPortalApi:
    """Wrapper class for Weishaupt WEM Portal"""

    def __init__(self, username, password, config=None, existing_data=None) -> None:
        if config is None:
            config = {}
        self.data = copy.deepcopy(existing_data) if existing_data else {}
        self.username = username
        self.password = password
        self.mode = config.get(CONF_MODE, DEFAULT_CONF_MODE_VALUE)
        self.update_interval = timedelta(
            seconds=min(
                config.get(CONF_SCAN_INTERVAL, DEFAULT_CONF_SCAN_INTERVAL_VALUE),
                config.get(
                    CONF_SCAN_INTERVAL_API, DEFAULT_CONF_SCAN_INTERVAL_API_VALUE
                ),
            )
        )
        self.scan_interval = timedelta(
            seconds=config.get(CONF_SCAN_INTERVAL, DEFAULT_CONF_SCAN_INTERVAL_VALUE)
        )
        self.scan_interval_api = timedelta(
            seconds=config.get(
                CONF_SCAN_INTERVAL_API, DEFAULT_CONF_SCAN_INTERVAL_API_VALUE
            )
        )
        self.valid_login = False
        self.language = config.get(CONF_LANGUAGE, DEFAULT_CONF_LANGUAGE_VALUE)
        self.session = None
        self.modules = None
        self.webscraping_cookie = {}
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

        # Used to keep track of how many update intervals to wait before retrying spider
        self.spider_wait_interval = 0
        # Used to keep track of the number of times the spider consecutively fails
        self.spider_retry_count = 0
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
                    self.get_parameters()
                else:
                    needs_recovery = False
                    for _, modules in self.modules.items():
                        for module in modules.values():
                            if "parameters" not in module:
                                needs_recovery = True
                                break
                    if needs_recovery:
                        _LOGGER.info("Attempting to recover missing parameter definitions...")
                        self.get_parameters()

            # Select data source based on mode
            if self.mode == "web":
                # Get data by web scraping
                webscraping_data = self.fetch_webscraping_data()
                from .translations import translate
                for key, value in webscraping_data.items():
                    if isinstance(value, dict) and "friendlyName" in value:
                        value["friendlyName"] = translate(self.language, value["friendlyName"])
                self.data[next(iter(self.data), "0000")] = webscraping_data
            elif self.mode == "api":
                # Get data using API
                self.get_data(enabled_devices)
            else:
                # Get data using web scraping if it hasn't been updated recently,
                # otherwise use API to get data
                if self.last_scraping_update is None or (
                    (
                        (
                            datetime.now()
                            - self.last_scraping_update
                            + timedelta(seconds=10)
                        )
                        > self.scan_interval
                    )
                    and self.spider_wait_interval == 0
                ):
                    # Get data by web scraping
                    try:
                        webscraping_data = self.fetch_webscraping_data()
                        from .translations import translate
                        for key, value in webscraping_data.items():
                            if isinstance(value, dict) and "friendlyName" in value:
                                value["friendlyName"] = translate(self.language, value["friendlyName"])
                        self.data[next(iter(self.data), "0000")] = webscraping_data

                        # Update last_scraping_update timestamp
                        self.last_scraping_update = datetime.now()
                    except Exception as exc:
                        _LOGGER.warning("Web scraper failed this cycle. Falling back to API only. Error: %s", exc)
                        # We intentionally do not raise, so the API can still fetch the bulk of the data
                        
                else:
                    # Reduce spider_wait_interval by 1 if > 0
                    self.spider_wait_interval = (
                        self.spider_wait_interval - 1
                        if self.spider_wait_interval > 0
                        else self.spider_wait_interval
                    )

                # Get data using API (always run as a resilient fallback)
                self.get_data(enabled_devices)


            # Return data
            return self.data

        except Exception as exc:
            if isinstance(exc, WemPortalError):
                # Re-raise known errors so we don't wrap them twice
                raise
            # Wrap any unexpected python crashes to prevent HA from halting
            raise WemPortalError("Unexpected error occurred while fetching data") from exc

    def fetch_webscraping_data(self):
        """
        Call scraper to crawl WEM Portal.
        This function manages the process of initiating a web scraping job, 
        handling errors, and returning the scraped data.
        """
        from .scraper import WemPortalScraper

        # Set up the web scraping job with necessary parameters
        scraper = WemPortalScraper(
            self.username, 
            self.password, 
            self.webscraping_cookie
        )

        try:
            # Attempt to run the scraping job and extract the first result
            data = scraper.scrape()[0]

        except IndexError as exc:
            # Handle the case where the job result is not found
            self.spider_retry_count += 1
            if self.spider_retry_count == 2:
                self.webscraping_cookie = None
            self.spider_wait_interval = self.spider_retry_count
            raise WemPortalError(DATA_GATHERING_ERROR) from exc

        except AuthError as exc:
            # Handle authentication errors
            self.webscraping_cookie = None
            raise AuthError(
                "AuthenticationError: Could not login with provided username and password. "
                "Check if your config contains the right credentials"
            ) from exc

        except ExpiredSessionError as exc:
            # Handle errors due to expired session
            self.webscraping_cookie = None
            raise ExpiredSessionError(
                "ExpiredSessionError: Session expired. Next update will try to login again."
            ) from exc

        try:
            # Attempt to update the cookie from the scraped data
            self.webscraping_cookie = data["cookie"]
            del data["cookie"]
        except KeyError:
            # If the cookie is not found in the data, simply pass
            pass

        # Reset retry count and wait interval after a successful operation
        self.spider_retry_count = 0
        self.spider_wait_interval = 0

        # Return the scraped data
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
            if response is None:
                raise UnknownAuthError(
                    "Authentication Error: Encountered an unknown authentication error."
                ) from exc
            elif response.status_code == 400:
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
        from .const import WEB_LOGIN_URL
        login_url = WEB_LOGIN_URL

        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Accept-Language": "de,en;q=0.9",
        }

        # Step 1: Fetch the login page
        try:
            initial_response = session.get(login_url, headers=headers)
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
                login_url,
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
        if response:
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
        response = None

        for attempt in range(attempts):
            time.sleep(1)  # Wait 1 sec between requests to be graceful to the API.
            current_headers = headers or self.headers.copy()

            try:
                if not data:
                    _LOGGER.debug("Sending GET request to %s with headers: %s", url, current_headers)
                    response = self.session.get(url, headers=current_headers, timeout=10)
                else:
                    _LOGGER.debug("Sending POST request to %s with headers: %s and data: %s", url, current_headers, data)
                    response = self.session.post(url, headers=current_headers, json=data, timeout=10)

                response.raise_for_status()

                # Check for stealthy session expiration (HTML redirect)
                if "Account/Login" in response.url or (hasattr(response, "redirect_url") and response.redirect_url and "Account/Login" in str(response.redirect_url)):
                    raise ExpiredSessionError("Redirected to Account/Login")

                _LOGGER.debug(response)
                return response

            except (reqs.exceptions.RequestException, ExpiredSessionError) as exc:
                is_auth_error = isinstance(exc, ExpiredSessionError) or (
                    isinstance(exc, reqs.exceptions.RequestException)
                    and response
                    and response.status_code in (401, 403)
                )

                if is_auth_error and attempt < attempts - 1:
                    _LOGGER.info("Session expired for %s. Re-authenticating...", url)
                    self.api_login()
                    time.sleep(delay)
                    continue  # Loop back around and retry

                # If we're out of retries or it's a completely different error:
                server_status, server_message = self.get_response_details(response)
                
                # The old logic recreated the entire API instance when this happened.
                # To emulate that recovery mechanism without losing cached metadata,
                # we invalidate the login state so the next cycle creates a fresh requests.Session.
                self.valid_login = False
                
                raise WemPortalError(
                    f"{DATA_GATHERING_ERROR} Server returned status code: {server_status} and message: {server_message}"
                ) from exc

        return response

    def get_devices(self):
        # Check if device data is already present
        if self.data and self.modules:
            _LOGGER.debug("Device data is already cached.")
            return

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

    def get_parameters(self):
        assert self.modules is not None
        for device_id, device_data in self.data.items():
            if device_data["ConnectionStatus"] != 0:
                continue
            _LOGGER.debug("Fetching api parameters data for device %s", device_id)
            _LOGGER.debug(self.data)
            _LOGGER.debug(self.modules[device_id])
            delete_candidates = []
            forbidden_count = 0
            for key, values in self.modules[device_id].items():
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

    def change_value(
        self,
        device_id,
        parameter_id,
        module_index,
        module_type,
        numeric_value,
        login=True,
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
        # _LOGGER.info(data)

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
        for device_id in target_devices:
            _LOGGER.debug("Processing device_id=%s (type %s). Is in self.data? %s", device_id, type(device_id), str(device_id) in self.data)
            if str(device_id) not in self.data:
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

                self.data[device_id][f"{device_id}-ConnectionStatus"] = {
                    "friendlyName": "Connection Status",
                    "ParameterID": "ConnectionStatus",
                    "unit": None,
                    "value": conn_status,
                    "IsWriteable": False,
                    "DataType": -1,
                    "ModuleIndex": -1,
                    "ModuleType": -1,
                    "platform": "sensor",
                    "icon": "mdi:network"
                }

                errors = status_response.get("Errors", [])
                has_errors = "Yes" if errors else "No"
                error_msg = ", ".join([str(e) for e in errors]) if errors else "None"

                self.data[device_id][f"{device_id}-HasErrors"] = {
                    "friendlyName": "Has Errors",
                    "ParameterID": "HasErrors",
                    "unit": None,
                    "value": has_errors,
                    "IsWriteable": False,
                    "DataType": -1,
                    "ModuleIndex": -1,
                    "ModuleType": -1,
                    "platform": "sensor",
                    "icon": "mdi:alert"
                }

                self.data[device_id][f"{device_id}-ErrorMessages"] = {
                    "friendlyName": "Error Messages",
                    "ParameterID": "ErrorMessages",
                    "unit": None,
                    "value": error_msg[:255],
                    "IsWriteable": False,
                    "DataType": -1,
                    "ModuleIndex": -1,
                    "ModuleType": -1,
                    "platform": "sensor",
                    "icon": "mdi:message-alert"
                }

                if conn_status != "online":
                    _LOGGER.warning("Device %s is %s. Skipping data polling.", device_id, conn_status)
                    continue

            except Exception as exc:
                _LOGGER.warning("Failed to fetch Device Status: %s", exc)

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
                from .mapper import WemPortalDataMapper
                WemPortalDataMapper.process_api_values(
                    device_id=device_id,
                    values_json=values,
                    modules_dict=self.modules,
                    language=self.language,
                    scraping_mapper=self.scraping_mapper,
                    mode=self.mode,
                    api_data=self.data,
                )
            except Exception as exc:
                _LOGGER.warning("Failed to fetch parameter data... %s", exc)

            # 3. Fetch Heating Schedules (DataType == 6)
            try:
                for module in self.modules[device_id].values():
                    module_index = module.get("Index")
                    module_type = module.get("Type")
                    if "parameters" in module:
                        for param_id, param_data in module["parameters"].items():
                            if param_data.get("DataType") == 6:  # WemDataType.PROGRAM
                                try:
                                    refresh_payload = {
                                        "DeviceID": int(device_id),
                                        "ModuleIndex": module_index,
                                        "ModuleType": module_type,
                                        "ParameterID": param_id
                                    }

                                    job_resp = self.make_api_call(
                                        API_CIRCUIT_TIMES_REFRESH_URL,
                                        data=refresh_payload,
                                        do_retry=True
                                    ).json()

                                    job_id = job_resp.get("JobID")
                                    if job_id is None:
                                        continue

                                    time.sleep(2)  # Give backend time to build the schedule payload

                                    read_payload = {
                                        "DeviceID": int(device_id),
                                        "JobID": job_id,
                                        "ModuleIndex": module_index,
                                        "ModuleType": module_type,
                                        "ParameterID": param_id
                                    }

                                    schedule_resp = self.make_api_call(
                                        API_CIRCUIT_TIMES_READ_URL,
                                        data=read_payload,
                                        do_retry=True
                                    ).json()

                                    sensor_name = f"{module['Name']}-{param_id}"
                                    if sensor_name not in self.data[device_id]:
                                        from .translations import friendly_name_mapper, translate
                                        self.data[device_id][sensor_name] = {
                                            "friendlyName": translate(self.language, friendly_name_mapper(param_id)),
                                            "ParameterID": param_id,
                                            "unit": None,
                                            "value": "Active",
                                            "IsWriteable": False,
                                            "DataType": 6,
                                            "ModuleIndex": module_index,
                                            "ModuleType": module_type,
                                            "platform": "sensor",
                                            "icon": "mdi:calendar-clock",
                                        }

                                    self.data[device_id][sensor_name]["CircuitTimesDay"] = schedule_resp.get("CircuitTimesDay", [])
                                    self.data[device_id][sensor_name]["PossibleValues"] = schedule_resp.get("PossibleValues", [])
                                    self.data[device_id][sensor_name]["value"] = "Active"

                                except Exception as exc:
                                    _LOGGER.warning("Failed to fetch CircuitTimes for %s: %s", param_id, exc)
            except Exception as exc:
                _LOGGER.warning("Error processing CircuitTimes: %s", exc)

        # 4. Fetch Energy Statistics (Rate limited)
        self.get_statistics(enabled_devices)

    def get_statistics(self, enabled_devices=None):
        """Fetch historical statistics from the API, rate limited to once per hour."""
        now = time.time()
        if self.last_statistics_fetch is not None and (now - self.last_statistics_fetch) < 3600:
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
                
                group_types = refresh_resp.get("GroupTypeDescriptions", [])
                headers = {"X-Api-Version": "2.0.0.0"}
                
                for group in group_types:
                    group_id = group.get("GroupType")
                    group_name = group.get("Description")
                    if not group_name or group_name.strip() == "":
                        fallback_names = {
                            1: "Heating Energy Yield",
                            2: "Hot Water Energy Yield",
                            3: "Cooling Energy Yield",
                            4: "Total Energy Yield",
                            5: "Power Consumption Heating",
                            6: "Power Consumption Hot Water",
                            7: "Power Consumption Cooling",
                            8: "Total Power Consumption"
                        }
                        group_name = fallback_names.get(group_id, f"Energy {group_id}")
                    else:
                        from .translations import translate
                        translated_group = translate(self.language, group_name)
                        if "energy" not in translated_group.lower():
                            group_name = f"{translated_group} Energy"
                        else:
                            group_name = translated_group
                    
                    read_payload = {
                        "DeviceID": int(device_id),
                        "ModuleType": 7,
                        "ModuleIndex": 0,
                        "GroupType": group_id,
                        "Type": 1
                    }
                    
                    try:
                        time.sleep(2)  # Avoid hammering the API
                        stats_resp = self.make_api_call(
                            API_STATISTICS_READ_URL,
                            headers=headers,
                            data=read_payload,
                            do_retry=True
                        ).json()
                        
                        values = stats_resp.get("Values", [])
                        if not values:
                            continue
                            
                        # The last value in the array is the current day's consumption
                        latest_stat = values[-1]
                        current_value = latest_stat.get("Value", 0.0)
                        unit = stats_resp.get("Unit", "kWh")
                        
                        sensor_name = f"Energy_{group_id}"
                        
                        self.data[device_id][f"{device_id}-{sensor_name}"] = {
                            "friendlyName": group_name,
                            "ParameterID": sensor_name,
                            "unit": unit,
                            "value": current_value,
                            "IsWriteable": False,
                            "DataType": -1,
                            "ModuleIndex": -1,
                            "ModuleType": -1,
                            "platform": "sensor",
                            "icon": "mdi:lightning-bolt",
                            "device_class": "energy",
                            "state_class": "total_increasing"
                        }
                        
                    except Exception as exc:
                        _LOGGER.warning("Failed to fetch Statistics for group %s: %s", group_id, exc)
                        
            except Exception as exc:
                _LOGGER.warning("Error processing Statistics: %s", exc)
