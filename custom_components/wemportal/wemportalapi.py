"""
Weishaupt webscraping and API library
"""


import copy
import json
import time
from collections import defaultdict
from datetime import datetime, timedelta

import requests as reqs
import scrapyscript
from fuzzywuzzy import fuzz
from homeassistant.const import (CONF_PASSWORD, CONF_SCAN_INTERVAL,
                                 CONF_USERNAME)
from scrapy import FormRequest, Spider

from .const import (_LOGGER, CONF_LANGUAGE, CONF_MODE, CONF_SCAN_INTERVAL_API,
                    START_URLS)


class WemPortalApi:
    """Wrapper class for Weishaupt WEM Portal"""

    def __init__(self, config):
        self.data = {}
        self.mode = config.get(CONF_MODE)
        self.username = config.get(CONF_USERNAME)
        self.password = config.get(CONF_PASSWORD)
        self.update_interval = min(
            config.get(CONF_SCAN_INTERVAL), config.get(CONF_SCAN_INTERVAL_API)
        )
        self.scan_interval = config.get(CONF_SCAN_INTERVAL)
        self.scan_interval_api = config.get(CONF_SCAN_INTERVAL_API)
        self.language = config.get(CONF_LANGUAGE)
        self.device_id = None
        self.session = None
        self.modules = None
        self.last_scraping_update = None
        # Headers used for all API calls
        self.headers = {
            "User-Agent": "WeishauptWEMApp",
            "X-Api-Version": "2.0.0.0",
            "Accept": "*/*",
        }
        self.scrapingMapper = {}

    def fetch_data(self):

        if self.mode == "web":
            if (
                    self.last_scraping_update is None
                    or (datetime.now() - self.last_scraping_update + timedelta(seconds=5))
                    > self.update_interval
            ):
                self.fetch_webscraping_data()
                self.last_scraping_update = datetime.now()
        elif self.mode == "api":
            self.fetch_api_data()
        else:
            if (
                    self.last_scraping_update is None
                    or (datetime.now() - self.last_scraping_update + timedelta(seconds=5))
                    > self.scan_interval
            ):
                self.fetch_webscraping_data()
                self.fetch_api_data()
                self.last_scraping_update = datetime.now()
            else:
                self.fetch_api_data()
        return self.data

    def fetch_webscraping_data(self):
        """Call spider to crawl WEM Portal"""
        wemportal_job = scrapyscript.Job(WemPortalSpider, self.username, self.password)
        processor = scrapyscript.Processor(settings=None)
        try:
            self.data = processor.run([wemportal_job])[0]
        except IndexError:
            _LOGGER.exception(
                "There was a problem with getting data from WEM Portal. If this problem persists, "
                "open an issue at https://github.com/erikkastelec/hass-WEM-Portal/issues"
            )
        try:
            if self.data["authErrorFlag"]:
                _LOGGER.exception(
                    "AuthenticationError: Could not login with provided username and password. Check if "
                    "your config contains the right credentials"
                )
        except KeyError:
            """If authentication was successful"""
            pass

    def fetch_api_data(self):
        """Get data from the mobile API"""
        if self.session is None:
            self.api_login()
        if self.device_id is None or self.modules is None:
            self.get_devices()
            self.get_parameters()
        self.get_data()
        return self.data

    def api_login(self):

        payload = {
            "Name": self.username,
            "PasswordUTF8": self.password,
            "AppID": "com.weishaupt.wemapp",
            "AppVersion": "2.0.2",
            "ClientOS": "Android",
        }
        self.session = reqs.Session()
        self.session.cookies.clear()
        self.session.headers.update(self.headers)
        response = self.session.post(
            "https://www.wemportal.com/app/Account/Login",
            data=payload,
        )
        if response.status_code != 200:
            _LOGGER.error(
                "Authentication Error: Check if your login credentials are correct. Receive response code: %s, response: %s",
                str(response.status_code),
                str(response.content),
            )

    def get_devices(self):
        _LOGGER.debug("Fetching api device data")
        self.modules = {}
        response = self.session.get(
            "https://www.wemportal.com/app/device/Read",
        )
        # If session expired
        if response.status_code == 401:
            self.api_login()
            response = self.session.get(
                "https://www.wemportal.com/app/device/Read",
            )

        data = response.json()
        # TODO: add multiple device support
        self.device_id = data["Devices"][0]["ID"]
        for module in data["Devices"][0]["Modules"]:
            self.modules[(module["Index"], module["Type"])] = {
                "index": module["Index"],
                "type": module["Type"],
                "name": module["Name"],
            }

    def get_parameters(self):
        _LOGGER.debug("Fetching api parameters data")
        delete_candidates = []
        for key, values in self.modules.items():
            data = {
                "DeviceID": self.device_id,
                "ModuleIndex": values["index"],
                "ModuleType": values["type"],
            }
            response = self.session.post(
                "https://www.wemportal.com/app/EventType/Read",
                data=data,
            )

            # If session expired
            if response.status_code == 401:
                self.api_login()
                response = self.session.post(
                    "https://www.wemportal.com/app/EventType/Read",
                    data=data,
                )
            parameters = {}
            try:
                for parameter in response.json()["Parameters"]:
                    parameters[parameter["ParameterID"]] = parameter
                if not parameters:
                    delete_candidates.append((values["index"], values["type"]))
                else:
                    self.modules[(values["index"], values["type"])][
                        "parameters"
                    ] = parameters
            except KeyError:
                _LOGGER.warning(
                    "An error occurred while gathering parameters data. This issue should resolve by "
                    "itself. If this problem persists, open an issue at "
                    "https://github.com/erikkastelec/hass-WEM-Portal/issues'  "
                )
        for key in delete_candidates:
            del self.modules[key]

    def change_value(
            self, parameter_id, module_index, module_type, numeric_value, login=True
    ):
        """POST request to API to change a specific value"""
        _LOGGER.debug("Changing value for %s", parameter_id)
        data = {
            "DeviceID": self.device_id,
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
        headers = copy.deepcopy(self.headers)
        headers["Content-Type"] = "application/json"
        # _LOGGER.info(data)
        response = self.session.post(
            "https://www.wemportal.com/app/DataAccess/Write",
            headers=headers,
            data=json.dumps(data),
        )
        if response.status_code == 401 and login:
            self.api_login()
            self.change_value(
                parameter_id, module_index, module_type, numeric_value, login=False
            )
        if response.status_code != 200:
            _LOGGER.error("Error changing parameter %s value", parameter_id)
            # _LOGGER.info("Error: %s", response.content)
            # _LOGGER.info(response.__dict__)

    # Refresh data and retrieve new data
    def get_data(self):
        _LOGGER.debug("Fetching fresh api data")
        try:
            data = {
                "DeviceID": self.device_id,
                "Modules": [
                    {
                        "ModuleIndex": module["index"],
                        "ModuleType": module["type"],
                        "Parameters": [
                            {"ParameterID": parameter}
                            for parameter in module["parameters"].keys()
                        ],
                    }
                    for module in self.modules.values()
                ],
            }
        except KeyError as _:
            _LOGGER.warning(
                "An error occurred while gathering data. This issue should resolve by "
                "itself. If this problem persists, open an issue at "
                "https://github.com/erikkastelec/hass-WEM-Portal/issues'  "
            )
            _LOGGER.debug(self.modules)
            return
        headers = copy.deepcopy(self.headers)
        headers["Content-Type"] = "application/json"
        response = self.session.post(
            "https://www.wemportal.com/app/DataAccess/Refresh",
            headers=headers,
            data=json.dumps(data),
        )
        if response.status_code == 401:
            self.api_login()
            response = self.session.post(
                "https://www.wemportal.com/app/DataAccess/Refresh",
                headers=headers,
                data=json.dumps(data),
            )
        values = self.session.post(
            "https://www.wemportal.com/app/DataAccess/Read",
            headers=headers,
            data=json.dumps(data),
        ).json()

        # TODO: CLEAN UP

        # Map values to sensors we got during scraping.
        icon_mapper = defaultdict(lambda: "mdi:flash")
        icon_mapper["°C"] = "mdi:thermometer"
        for module in values["Modules"]:
            for value in module["Values"]:

                # Skip schedules
                if (
                        self.modules[(module["ModuleIndex"], module["ModuleType"])][
                            "parameters"
                        ][value["ParameterID"]]["DataType"]
                        == 2
                ):
                    continue
                # if self.modules[(module["ModuleIndex"], module["ModuleType"])]["parameters"][value["ParameterID"]][
                #     "DataType"] == 1:
                #     print(value)
                name = self.modules[(module["ModuleIndex"], module["ModuleType"])][
                    "parameters"
                ][value["ParameterID"]]["Name"]

                data[name] = {
                    "friendlyName": self.translate(
                        self.language, self.friendly_name_mapper(value["ParameterID"])
                    ),
                    "ParameterID": value["ParameterID"],
                    "unit": value["Unit"],
                    "value": value["NumericValue"],
                    "IsWriteable": self.modules[
                        (module["ModuleIndex"], module["ModuleType"])
                    ]["parameters"][value["ParameterID"]]["IsWriteable"],
                    "DataType": self.modules[
                        (module["ModuleIndex"], module["ModuleType"])
                    ]["parameters"][value["ParameterID"]]["DataType"],
                    "ModuleIndex": module["ModuleIndex"],
                    "ModuleType": module["ModuleType"],
                }
                if not value["NumericValue"]:
                    data[name]["value"] = value["StringValue"]
                if self.modules[(module["ModuleIndex"], module["ModuleType"])][
                    "parameters"
                ][value["ParameterID"]]["EnumValues"]:
                    if value["StringValue"] == "off":
                        data[name]["value"] = 0
                    else:
                        try:
                            data[name]["value"] = int(value["StringValue"])
                        except ValueError:
                            data[name]["value"] = value["StringValue"]

                # Select entities
                if data[name]["IsWriteable"]:
                    if data[name]["DataType"] == -1:
                        self.data[name] = {
                            "friendlyName": data[name]["friendlyName"],
                            "ParameterID": value["ParameterID"],
                            "unit": value["Unit"],
                            "icon": icon_mapper[value["Unit"]],
                            "value": value["NumericValue"],
                            "DataType": data[name]["DataType"],
                            "ModuleIndex": module["ModuleIndex"],
                            "ModuleType": module["ModuleType"],
                            "platform": "number",
                            "min_value": int(
                                self.modules[
                                    (module["ModuleIndex"], module["ModuleType"])
                                ]["parameters"][value["ParameterID"]]["MinValue"]
                            ),
                            "max_value": int(
                                self.modules[
                                    (module["ModuleIndex"], module["ModuleType"])
                                ]["parameters"][value["ParameterID"]]["MaxValue"]
                            ),
                            "step": 0.5,
                        }
                    elif data[name]["DataType"] == 1:
                        self.data[name] = {
                            "friendlyName": data[name]["friendlyName"],
                            "ParameterID": value["ParameterID"],
                            "unit": value["Unit"],
                            "icon": icon_mapper[value["Unit"]],
                            "value": value["NumericValue"],
                            "DataType": data[name]["DataType"],
                            "ModuleIndex": module["ModuleIndex"],
                            "ModuleType": module["ModuleType"],
                            "platform": "select",
                            "options": [
                                x["Value"]
                                for x in self.modules[
                                    (module["ModuleIndex"], module["ModuleType"])
                                ]["parameters"][value["ParameterID"]]["EnumValues"]
                            ],
                            "optionsNames": [
                                x["Name"]
                                for x in self.modules[
                                    (module["ModuleIndex"], module["ModuleType"])
                                ]["parameters"][value["ParameterID"]]["EnumValues"]
                            ],
                        }

                # if self.modules[(module["ModuleIndex"],module["ModuleType"])]["parameters"][value["ParameterID"]]["EnumValues"]:
                #     for entry in self.modules[(module["ModuleIndex"],module["ModuleType"])]["parameters"][value["ParameterID"]]["EnumValues"]:
                #         if entry["Value"] == round(value["NumericValue"]):
                #             self.data[value["ParameterID"]]["value"] = entry["Name"]
                #             break

            for key in data.keys():
                if key not in ["DeviceID", "Modules"]:
                    # Match only values, which are not writable (sensors)
                    if not data[key]["IsWriteable"]:
                        # Only when mode == both. Combines data from web and api
                        if self.mode == "both":
                            try:
                                temp = self.scrapingMapper[key]
                            except KeyError:
                                for scraped_entity in self.data.keys():
                                    try:
                                        if (
                                                fuzz.ratio(
                                                    data[key]["friendlyName"],
                                                    scraped_entity.split("-")[1],
                                                )
                                                >= 85
                                        ):
                                            try:
                                                self.scrapingMapper[key].append(
                                                    scraped_entity
                                                )
                                            except KeyError:
                                                self.scrapingMapper[key] = [
                                                    scraped_entity
                                                ]
                                    except IndexError:
                                        pass
                                # Check if empty
                                try:
                                    temp = self.scrapingMapper[key]
                                except KeyError:
                                    self.scrapingMapper[key] = [
                                        data[key]["friendlyName"]
                                    ]
                            finally:
                                for scraped_entity in self.scrapingMapper[key]:
                                    try:
                                        self.data[scraped_entity] = {
                                            "value": self.data[scraped_entity]["value"],
                                            "name": self.data[scraped_entity]["name"],
                                            "unit": self.data[scraped_entity]["unit"],
                                            "icon": self.data[scraped_entity]["icon"],
                                            "friendlyName": scraped_entity,
                                            "ParameterID": scraped_entity,
                                            "platform": "sensor",
                                        }
                                    except KeyError:
                                        self.data[scraped_entity] = {
                                            "value": data[key]["value"],
                                            "unit": data[key]["unit"],
                                            "icon": icon_mapper[data[key]["unit"]],
                                            "friendlyName": scraped_entity,
                                            "name": scraped_entity,
                                            "ParameterID": scraped_entity,
                                            "platform": "sensor",
                                        }
                        else:
                            self.data[key] = {
                                "value": data[key]["value"],
                                "ParameterID": data[key]["ParameterID"],
                                "unit": data[key]["unit"],
                                "icon": icon_mapper[data[key]["unit"]],
                                "friendlyName": data[key]["friendlyName"],
                                "platform": "sensor",
                            }

    def friendly_name_mapper(self, value):
        friendlyNameDict = {
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
            out = friendlyNameDict[value.casefold()]
        except KeyError:
            out = value.casefold()
        return out

    def translate(self, language, value):
        # TODO: Implement support for other languages.
        translationDict = {
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
            out = translationDict[language][value.casefold()]
        except KeyError:
            out = value.casefold()
        return out


class WemPortalSpider(Spider):
    name = "WemPortalSpider"
    start_urls = START_URLS

    def __init__(self, username, password, **kw):
        self.username = username
        self.password = password
        self.authErrorFlag = False
        super().__init__(**kw)

    def parse(self, response):
        """Login to WEM Portal"""
        return FormRequest.from_response(
            response,
            formdata={
                "ctl00$content$tbxUserName": self.username,
                "ctl00$content$tbxPassword": self.password,
                "Accept-Language": "en-US,en;q=0.5",
            },
            callback=self.navigate_to_expert_page,
        )

    def navigate_to_expert_page(self, response):
        # sleep for 1 seconds to get proper language and updated data
        time.sleep(1)
        # _LOGGER.debug("Print user page HTML: %s", response.text)
        if (
                response.url
                == "https://www.wemportal.com/Web/login.aspx?AspxAutoDetectCookieSupport=1"
        ):
            _LOGGER.debug("Authentication failed")
            self.authErrorFlag = True
            form_data = {}
        else:
            _LOGGER.debug("Authentication successful")
            form_data = self.generate_form_data(response)
            _LOGGER.debug("Form data processed")
        return FormRequest(
            url="https://www.wemportal.com/Web/default.aspx",
            formdata=form_data,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Cookie": response.request.headers.getlist("Cookie")[0].decode("utf-8"),
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
        # sleep for 1 seconds to get proper language and updated data
        time.sleep(1)
        # _LOGGER.debug("Print expert page HTML: %s", response.text)
        if self.authErrorFlag:
            yield {"authErrorFlag": True}
        _LOGGER.debug("Scraping page")
        output = {}
        for i, div in enumerate(
                response.xpath(
                    '//div[@class="RadPanelBar RadPanelBar_Default rpbSimpleData"]'
                )
        ):
            header_query = (
                    "//span[@id='ctl00_rdMain_C_controlExtension_rptDisplayContent_ctl0"
                    + str(i)
                    + "_ctl00_rpbGroupData_i0_HeaderTemplate_lblHeaderText']/text() "
            )
            # Catch heading not starting at 0
            try:
                header = div.xpath(header_query).extract()[0]
                header = (
                    header.replace("/#", "")
                        .replace("  ", "")
                        .replace(" - ", "_")
                        .replace("/*+/*", "_")
                        .replace(" ", "_")
                        .casefold()
                )
            except IndexError:
                header = "unknown"
                continue
            for td in div.xpath('.//table[@class="simpleDataTable"]//tr'):
                try:
                    name = td.xpath(
                        './/td//span[@class="simpleDataName"]/text()'
                    ).extract()[0]
                    value = td.xpath(
                        './/td//span[@class="simpleDataValue"]/text()'
                    ).extract()[0]
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
                        if value == "--" or value == "off":
                            value = 0.0

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
                except IndexError:
                    continue

        yield output
