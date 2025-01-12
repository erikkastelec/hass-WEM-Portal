"""
Weishaupt webscraping and API library
"""


import copy
import json
import time
from collections import defaultdict
from datetime import datetime, timedelta

from bs4 import BeautifulSoup
import requests as reqs
import scrapyscript
from fuzzywuzzy import fuzz
from homeassistant.const import CONF_SCAN_INTERVAL
from scrapy import FormRequest, Spider, Request
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
    API_DATA_ACCESS_WRITE_URL,
    API_DEVICE_READ_URL,
    API_EVENT_TYPE_READ_URL,
    API_LOGIN_URL,
    API_REFRESH_URL,
    CONF_LANGUAGE,
    CONF_MODE,
    CONF_SCAN_INTERVAL_API,
    DATA_GATHERING_ERROR,
    DEFAULT_CONF_LANGUAGE_VALUE,
    DEFAULT_CONF_MODE_VALUE,
    DEFAULT_CONF_SCAN_INTERVAL_API_VALUE,
    DEFAULT_CONF_SCAN_INTERVAL_VALUE,
    WEB_LOGIN_URL,
    WEB_MAIN_URL,
    API_DATA_ACCESS_READ_URL
)


class WemPortalApi:
    """Wrapper class for Weishaupt WEM Portal"""

    def __init__(self, username, password, device_id, config={}, existing_data=None) -> None:
        self.data = copy.deepcopy(existing_data) if existing_data else {device_id: {}}
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

        # Used to keep track of how many update intervals to wait before retrying spider
        self.spider_wait_interval = 0
        # Used to keep track of the number of times the spider consecutively fails
        self.spider_retry_count = 0

    def fetch_data(self):
        try:
            if self.mode != "web":
                # Login and get device info
                if not self.valid_login:
                    self.api_login()
                # Fetch device and parameter data only at start
                if self.modules is None:
                    self.get_devices()
                    self.get_parameters()

            # Select data source based on mode
            if self.mode == "web":
                # Get data by web scraping
                self.data[next(iter(self.data), "0000")] = self.fetch_webscraping_data()
            elif self.mode == "api":
                # Get data using API
                self.get_data()
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
                        self.data[next(iter(self.data), "0000")] = webscraping_data

                        # Update last_scraping_update timestamp
                        self.last_scraping_update = datetime.now()
                    except Exception as exc:
                        _LOGGER.error(exc)

                else:
                    # Reduce spider_wait_interval by 1 if > 0
                    self.spider_wait_interval = (
                        self.spider_wait_interval - 1
                        if self.spider_wait_interval > 0
                        else self.spider_wait_interval
                    )

                # Get data using API
                if self.last_scraping_update is not None:
                    self.get_data()


            # Return data
            return self.data

        # Catch and raise any exceptions as a WemPortalError
        except Exception as exc:
            raise WemPortalError from exc

    def fetch_webscraping_data(self):
        """
        Call spider to crawl WEM Portal.
        This function manages the process of initiating a web scraping job, 
        handling errors, and returning the scraped data.
        """

        # Set up the web scraping job with necessary parameters
        wemportal_job = scrapyscript.Job(
            WemPortalSpider, 
            self.username, 
            self.password, 
            self.webscraping_cookie
        )

        # Initialize the processor for running the job
        processor = scrapyscript.Processor(settings=None)

        try:
            # Attempt to run the scraping job and extract the first result
            data = processor.run([wemportal_job])[0]

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
            self.webscraping_cookiescraped_entity = data["cookie"]
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
        except reqs.exceptions.HTTPError as exc:
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
        # Everything went fine, set valid_login to True
        self.valid_login = True


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
        login_url = "https://www.wemportal.com/Web/Login.aspx"

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
            except KeyError:
                pass
        return server_status, server_message

    def make_api_call(
        self, url: str, headers=None, data=None, do_retry=True, delay=5
    ) -> reqs.Response:
        response = None
        try:
            time.sleep(1)  # Wait 1 sec between requests to be graceful to the API. 
            if not headers:
                headers = self.headers
            if not data:
                _LOGGER.debug(f"Sending GET request to {url} with headers: {headers}")
                response = self.session.get(url, headers=headers)
            else:
                headers["Content-Type"] = "application/json"
                data = {k: v.encode('utf-8') if isinstance(v, str) else v for k, v in data.items()}
                _LOGGER.debug(f"Sending POST request to {url} with headers: {headers} and data: {data}")
                response = self.session.post(
                    url, headers=headers, data=json.dumps(data)
                )

            response.raise_for_status()
        except Exception as exc:
            if response and response.status_code in (401, 403) and not do_retry:
                self.api_login()
                headers = headers or self.headers
                time.sleep(delay)
                response = self.make_api_call(
                    url,
                    headers=headers,
                    data=data,
                    do_retry=False,
                    delay=delay,
                )
            else:
                server_status, server_message = self.get_response_details(response)
                raise WemPortalError(
                    f"{DATA_GATHERING_ERROR} Server returned status code: {server_status} and message: {server_message}"
                ) from exc

        _LOGGER.debug(response)
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
            self.data[device["ID"]] = {}
            self.modules[device["ID"]] = {}
            for module in device["Modules"]:
                self.modules[device["ID"]][(module["Index"], module["Type"])] = {
                    "Index": module["Index"],
                    "Type": module["Type"],
                    "Name": module["Name"],
                }
            self.data[device["ID"]]["ConnectionStatus"] = device["ConnectionStatus"]
            # TODO: remove when we implement multiple device support
            break

    def get_parameters(self):
        assert self.modules is not None
        for device_id in self.data.keys():
            if self.data[device_id]["ConnectionStatus"] != 0:
                continue
            _LOGGER.debug("Fetching api parameters data for device %s", device_id)
            _LOGGER.debug(self.data)
            _LOGGER.debug(self.modules[device_id])
            delete_candidates = []
            for key, values in self.modules[device_id].items():
                # Check if parameters are already cached
                if "parameters" in values and values["parameters"]:
                    _LOGGER.debug(
                        "Parameters for device %s, index %s, and type %s are already cached.",
                        device_id, values["Index"], values["Type"]
                    )
                    continue
                data = {
                    "DeviceID": device_id,
                    "ModuleIndex": values["Index"],
                    "ModuleType": values["Type"],
                }
                try:
                    time.sleep(5) 
                    response = self.make_api_call(
                        API_EVENT_TYPE_READ_URL, data=data, do_retry=False
                    )
                except WemPortalError as exc:
                    if isinstance(exc.__cause__, reqs.exceptions.HTTPError) and (exc.__cause__.response.status_code == 400 or exc.__cause__.response.status_code == 403):
                        _LOGGER.error("Could not fetch parameters for device %s for index %s and type %s", device_id,  values["Index"], values["Type"])
                        delete_candidates.append((values["Index"], values["Type"]))
                        continue
                    else:
                        raise
                _LOGGER.debug(response.json())
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
                except KeyError as exc:
                    # TODO: make sure that we should fail here or should we just log and continue
                    raise WemPortalError(
                        "An error occurred while gathering parameters data. This issue should resolve by "
                        "itself. If this problem persists, open an issue at "
                        "https://github.com/erikkastelec/hass-WEM-Portal/issues'  "
                    ) from exc
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
            "DeviceID": device_id,
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

        # TODO: do this with self.make_api_call()
        headers = copy.deepcopy(self.headers)
        headers["Content-Type"] = "application/json"
        response = self.session.post(
            API_DATA_ACCESS_WRITE_URL,
            headers=headers,
            data=json.dumps(data),
        )
        if response.status_code in (401, 403) and login:
            self.api_login()
            self.change_value(
                device_id,
                parameter_id,
                module_index,
                module_type,
                numeric_value,
                login=False,
            )
        try:
            response.raise_for_status()
        except Exception as exc:
            raise ParameterChangeError(
                "Error changing parameter %s value" % parameter_id
            ) from exc

    # Refresh data and retrieve new data
    def get_data(self):
        _LOGGER.debug("Fetching fresh api data")
        for device_id in self.data.keys():  # type: ignore
            try:
                data = {
                    "DeviceID": device_id,
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
                    ],
                }
            except KeyError as exc:
                _LOGGER.debug(DATA_GATHERING_ERROR, ": ")
                _LOGGER.debug(self.modules[device_id])
                raise WemPortalError(DATA_GATHERING_ERROR) from exc

            self.make_api_call(
                "https://www.wemportal.com/app/DataAccess/Refresh",
                data=data,
            )
            time.sleep(5)
            values = self.make_api_call(
                "https://www.wemportal.com/app/DataAccess/Read",
                data=data,
                do_retry=True
            ).json()
            # TODO: CLEAN UP
            # Map values to sensors we got during scraping.
            icon_mapper = defaultdict(lambda: "mdi:flash")
            icon_mapper["°C"] = "mdi:thermometer"
            for module in values["Modules"]:
                for value in module["Values"]:
                    name = (
                        self.modules[device_id][
                            (module["ModuleIndex"], module["ModuleType"])
                        ]["Name"]
                        + "-"
                        + self.modules[device_id][
                            (module["ModuleIndex"], module["ModuleType"])
                        ]["parameters"][value["ParameterID"]]["ParameterID"]
                    )
                    module_data = module_data = self.modules[device_id][
                        (module["ModuleIndex"], module["ModuleType"])
                    ]["parameters"][value["ParameterID"]]
                    data[name] = {
                        "friendlyName": self.translate(
                            self.language,
                            self.friendly_name_mapper(value["ParameterID"]),
                        ),
                        "ParameterID": value["ParameterID"],
                        "unit": value["Unit"],
                        "value": value["NumericValue"],
                        "IsWriteable": module_data["IsWriteable"],
                        "DataType": module_data["DataType"],
                        "ModuleIndex": module["ModuleIndex"],
                        "ModuleType": module["ModuleType"],
                    }
                    if not value["NumericValue"]:
                        data[name]["value"] = value["StringValue"]
                    if self.modules[device_id][
                        (module["ModuleIndex"], module["ModuleType"])
                    ]["parameters"][value["ParameterID"]]["EnumValues"]:
                        if value["StringValue"] in [
                            "off",
                            "Aus",
                            "Label ist null",
                            "Label ist null ",
                        ]:
                            data[name]["value"] = 0.0
                        else:
                            try:
                                data[name]["value"] = float(value["StringValue"])
                            except ValueError:
                                data[name]["value"] = value["StringValue"]
                    if data[name]["value"] in [
                        "off",
                        "Aus",
                        "Label ist null",
                        "Label ist null ",
                    ]:
                        data[name]["value"] = 0.0

                    if data[name]["IsWriteable"]:
                        # NUMBER PLATFORM
                        # Define common attributes
                        common_attrs = {
                            "friendlyName": data[name]["friendlyName"],
                            "ParameterID": value["ParameterID"],
                            "unit": value["Unit"],
                            "icon": icon_mapper[value["Unit"]],
                            "value": value["NumericValue"],
                            "DataType": data[name]["DataType"],
                            "ModuleIndex": module["ModuleIndex"],
                            "ModuleType": module["ModuleType"],
                        }

                        # Process data based on platform type

                        # NUMBER PLATFORM
                        if data[name]["DataType"] == -1 or data[name]["DataType"] == 3:
                            self.data[device_id][name] = {
                                **common_attrs,
                                "platform": "number",
                                "min_value": float(module_data["MinValue"]),
                                "max_value": float(module_data["MaxValue"]),
                                "step": 0.5 if data[name]["DataType"] == -1 else 1,
                            }
                        # SELECT PLATFORM
                        elif data[name]["DataType"] == 1:
                            self.data[device_id][name] = {
                                **common_attrs,
                                "platform": "select",
                                "options": [
                                    x["Value"] for x in module_data["EnumValues"]
                                ],
                                "optionsNames": [
                                    x["Name"] for x in module_data["EnumValues"]
                                ],
                            }
                        # SWITCH PLATFORM
                        elif data[name]["DataType"] == 2:
                            try:
                                if (
                                    int(module_data["MinValue"]) == 0
                                    and int(module_data["MaxValue"]) == 1
                                ):
                                    self.data[device_id][name] = {
                                        **common_attrs,
                                        "platform": "switch",
                                    }
                                else:
                                    # Skip schedules
                                    continue
                            except (ValueError, TypeError):
                                continue

                            # Catches exception when converting to int when MinValur or MaxValue is Nones
                            except Exception:
                                continue

                for key, value in data.items():
                    if key not in ["DeviceID", "Modules"] and not value["IsWriteable"]:
                        # Ony when mode == both. Combines data from web and api
                        # Only for single device, don't know how to handle multiple devices with scraping yet
                        if self.mode == "both" and len(self.data.keys()) < 2:
                            try:
                                temp = self.scraping_mapper[value["ParameterID"]]
                            except KeyError:
                                for scraped_entity in self.data[device_id].keys():
                                    scraped_entity_id = self.data[device_id][
                                        scraped_entity
                                    ]["ParameterID"]
                                    try:
                                        if (
                                            fuzz.ratio(
                                                value["friendlyName"],
                                                scraped_entity_id.split("-")[1],
                                            )
                                            >= 90
                                        ):
                                            self.scraping_mapper.setdefault(
                                                value["ParameterID"], []
                                            ).append(scraped_entity_id)
                                    except IndexError:
                                        pass
                                # Check if empty
                                try:
                                    temp = self.scraping_mapper[value["ParameterID"]]
                                except KeyError:
                                    self.scraping_mapper[value["ParameterID"]] = [
                                        value["friendlyName"]
                                    ]

                            finally:
                                for scraped_entity in self.scraping_mapper[
                                    value["ParameterID"]
                                ]:
                                    sensor_dict = {
                                        "value": value.get("value"),
                                        "name": self.data[device_id]
                                        .get(scraped_entity, {})
                                        .get("name"),
                                        "unit": self.data[device_id]
                                        .get(scraped_entity, {})
                                        .get("unit", value.get("unit")),
                                        "icon": self.data[device_id]
                                        .get(scraped_entity, {})
                                        .get(
                                            "icon", icon_mapper.get(value.get("unit"))
                                        ),
                                        "friendlyName": scraped_entity,
                                        "ParameterID": scraped_entity,
                                        "platform": "sensor",
                                    }

                                    self.data[device_id][scraped_entity] = sensor_dict
                        else:
                            self.data[device_id][key] = {
                                "value": value["value"],
                                "ParameterID": value["ParameterID"],
                                "unit": value["unit"],
                                "icon": icon_mapper[value["unit"]],
                                "friendlyName": value["friendlyName"],
                                "platform": "sensor",
                            }

    def friendly_name_mapper(self, value):
        friendly_name_dict = {
            "pp_beginn": "party_beginn",
            "pp_ende": "party_ende",
            "pp_funktion": "party_funktion",
            "pp_raumsoll": "party_raumsoll",
            "aktraumsoll": "raumsolltemperatur",
            "u_beginn": "urlaub_beginn",
            "u_ende": "urlaub_ende",
            "u_funktion": "urlaub_funktion",
            "u_raumsoll": "urlasub_raumsoll",
            "ww-push": "warmwasser_push",
            "ww-program": "warmwasser_program",
            "aktwwsoll": "warmwassersolltemperatur",
            "leistung": "wärmeleistung",
            "absenk": "absenktemperatur",
            "absenkww": "absenk_warmwasser_temperatur",
            "normalww": "normal_warmwasser_temperatur",
            "komfort": "komforttemperatur",
            "normal": "normaltemperatur",
        }
        try:
            out = friendly_name_dict[value.casefold()]
        except KeyError:
            out = value.casefold()
        return out

    def translate(self, language, value):
        # TODO: Implement support for other languages.
        value = value.lower()
        translation_dict = {
            "en": {
                "außsentemperatur": "outside_temperature",
                "aussentemperatur": "outside_temperature",
                "raumtemperatur": "room_temperature",
                "warmwassertemperatur": "hot_water_temperature",
                "betriebsart": "operation_mode",
                "vorlauftemperatur": "flow_temperature",
                "anlagendruck": "system_pressure",
                "kollektortemperatur": "collector_temperature",
                "wärmeleistung": "heat_output",
                "raumsolltemperatur": "room_setpoint_temperature",
                "warmwasser_push": "hot_water_push",
                "absenktemperatur": "reduced_temperature",
                "absenk_warmwasser_temperatur": "reduced_hot_water_temperature",
                "normal_warmwasser_temperatur": "normal_hot_water_temperature",
                "komforttemperatur": "comfort_temperature",
                "normaltemperatur": "normal_temperature",
            }
        }
        try:
            out = translation_dict[language][value.casefold()]
        except KeyError:
            out = value.casefold()
        return out

START_URLS = ["https://www.wemportal.com/Web/login.aspx"]
class WemPortalSpider(Spider):
    name = "WemPortalSpider"
    start_urls = START_URLS

    custom_settings = {
        "USER_AGENT": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36",
        "LOG_LEVEL": "ERROR",
    }

    def __init__(self, username, password, cookie=None, **kw):
        self.username = username
        self.password = password
        self.cookie = cookie if cookie else {}
        self.retry = None
        super().__init__(**kw)

    def start_requests(self):
        # Check if we have a cookie/session. Skip to main website if we do.
        if ".ASPXAUTH" in self.cookie:
            return [
                Request(
                    "https://www.wemportal.com/Web/Default.aspx",
                    headers={
                        "Accept-Language": "en-US,en;q=0.5",
                        "Connection": "keep-alive",
                    },
                    cookies=self.cookie,
                    callback=self.check_valid_login,
                )
            ]
        return [
            Request("https://www.wemportal.com/Web/Login.aspx", callback=self.login)
        ]

    def login(self, response):
        return [
            FormRequest.from_response(
                response,
                formdata={
                    "ctl00$content$tbxUserName": self.username,
                    "ctl00$content$tbxPassword": self.password,
                    "Accept-Language": "en-US,en;q=0.5",
                },
                callback=self.check_valid_login,
            )
        ]

    # Extract cookies from response.request.headers and convert them to dict
    def get_cookies(self, response):
        cookies = {}
        response_cookies = response.request.headers.getlist("Cookie")
        if len(response_cookies) > 0:
            for cookie_entry in response_cookies[0].decode("utf-8").split("; "):
                parts = cookie_entry.split("=")
                if len(parts) == 2:
                    cookie_name, cookie_value = parts
                    cookies[cookie_name] = cookie_value
            self.cookie = cookies

    # Check if login was successful. If not, return authErrorFlag
    def check_valid_login(self, response):
        if (
            response.url.lower() == "https://www.wemportal.com/Web/Login.aspx".lower()
            and not self.retry
        ):
            raise ExpiredSessionError(
                "Scrapy spider session expired. Skipping one update cycle."
            )

        elif (
            response.url.lower()
            == "https://www.wemportal.com/Web/Login.aspx?AspxAutoDetectCookieSupport=1".lower()
            or response.status != 200
        ):
            raise AuthError(
                f"Authentication Error: Encountered an unknown authentication error. Received response code: {response.status_code}, response: {response.content}"
            )

        self.retry = None
        # Wait 2 seconds so everything loads
        time.sleep(2)
        form_data = self.generate_form_data(response)
        self.get_cookies(response)
        cookie_string = ";".join(
            [f"{key}={value}" for key, value in self.cookie.items()]
        )
        return FormRequest(
            url="https://www.wemportal.com/Web/default.aspx",
            formdata=form_data,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Cookie": cookie_string,
                "Accept-Language": "en-US,en;q=0.5",
            },
            method="POST",
            callback=self.scrape_pages,
        )

    def generate_form_data(self, response):
        """prepares form data for request, which simulates a click on "Expert" element in submenu"""
        return {
            "__EVENTVALIDATION": response.xpath("//*[@id='__EVENTVALIDATION']/@value")[
                0
            ].extract(),
            "__VIEWSTATE": response.xpath("//*[@id='__VIEWSTATE']/@value")[0].extract(),
            "__ECNPAGEVIEWSTATE": response.xpath(
                "//*[@id='__ECNPAGEVIEWSTATE']/@value"
            )[0].extract(),
            "__EVENTTARGET": "ctl00$SubMenuControl1$subMenu",
            "__EVENTARGUMENT": "3",
            "ctl00_rdMain_ClientState": '{"Top":0,"Left":0,"DockZoneID":"ctl00_RDZParent","Collapsed":false,'
            '"Pinned":false,"Resizable":false,"Closed":false,"Width":"99%","Height":null,'
            '"ExpandedHeight":0,"Index":0,"IsDragged":false}',
            "ctl00_SubMenuControl1_subMenu_ClientState": '{"logEntries":[{"Type":3},{"Type":1,"Index":"0","Data":{'
            '"text":"Overview","value":"110"}},{"Type":1,"Index":"1",'
            '"Data":{"text":"System:+dom","value":""}},{"Type":1,'
            '"Index":"2","Data":{"text":"User","value":"222"}},'
            '{"Type":1,"Index":"3","Data":{"text":"Expert",'
            '"value":"223","selected":true}},{"Type":1,"Index":"4",'
            '"Data":{"text":"Statistics","value":"225"}},{"Type":1,'
            '"Index":"5","Data":{"text":"Data+Loggers","value":"224"}}],'
            '"selectedItemIndex":"3"} ',
        }

    def scrape_pages(self, response):
        # sleep for 5 seconds to get proper language and updated data
        time.sleep(5)
        _LOGGER.debug("Print expert page HTML: %s", response.text)
        # if self.authErrorFlag != 0:
        #     yield {"authErrorFlag": self.authErrorFlag}
        output = {}
        for div in response.xpath('//div[contains(@class, "RadPanelBar RadPanelBar_Default rpbSimpleData")]'):
            header = div.xpath('.//th[contains(@class, "simpleDataHeaderTextCell")]/span/text()').get()
            if header is not None:
                header = (
                    header.replace("/#", "")
                    .replace("  ", "")
                    .replace(" - ", "_")
                    .replace("/*+/*", "_")
                    .replace(" ", "_")
                    .casefold()
                )
            else:
                header = "unknown"
                continue
            for td in div.xpath('.//div[contains(@class, "rpTemplate")]/table[contains(@class, "simpleDataTable")]/tbody/tr'):
                try:
                    name = td.xpath('.//td[contains(@class, "simpleDataNameCell")]/span/text()').get()
                    value = td.xpath('.//td[contains(@class, "simpleDataValueCell") or contains(@class, "simpleDataValueEnumCell")]/span/text()').get()
                    if name is not None and value is not None:
                        name = name.replace("  ", "").replace(" ", "_").casefold()
                        name = header + "-" + name
                        split_value = value.split(" ")
                        unit = ""
                        if len(split_value) >= 2:
                            value = split_value[0]
                            unit = split_value[1]
                        else:
                            value = split_value[0]
                        try:
                            value = ".".join(value.split(","))
                            value = float(value)
                        except ValueError:
                            if value in [
                                "off",
                                "Aus",
                                "--",
                                "Label ist null",
                                "Label ist null ",
                            ]:
                                value = 0.0
                            elif value in [
                                "Ein"
                            ]:
                                value = 1.0
                            else:
                                unit = None

                        if(name.endswith('leistungsanforderung')):
                            unit = '%'

                        icon_mapper = defaultdict(lambda: "mdi:flash")
                        icon_mapper["°C"] = "mdi:thermometer"

                        output[name] = {
                            "value": value,
                            "name": name,
                            "icon": icon_mapper[unit],
                            "unit": unit,
                            "platform": "sensor",
                            "friendlyName": name,
                            "ParameterID": name,
                        }
                except (IndexError, ValueError):
                    continue

        output["cookie"] = self.cookie

        yield output


def extract_viewstate(response_text: str) -> str:
    """
    Extracts the __VIEWSTATE value from the HTML of the login page.
    """
    import re
    match = re.search(r'id="__VIEWSTATE" value="(.*?)"', response_text)
    if not match:
        raise UnknownAuthError("Failed to extract __VIEWSTATE from login page.")
    return match.group(1)


def extract_eventvalidation(response_text: str) -> str:
    """
    Extracts the __EVENTVALIDATION value from the HTML of the login page.
    """
    import re
    match = re.search(r'id="__EVENTVALIDATION" value="(.*?)"', response_text)
    if not match:
        raise UnknownAuthError("Failed to extract __EVENTVALIDATION from login page.")
    return match.group(1)