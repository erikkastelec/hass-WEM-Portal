"""Web scraping scraper for WEM Portal using curl_cffi."""

import time
import logging
from collections import defaultdict
from curl_cffi import requests
from lxml import html
from custom_components.wemportal.exceptions import AuthError, ExpiredSessionError
from custom_components.wemportal.const import (
    WEB_LOGIN_URL,
    WEB_MAIN_URL,
    MISSING_DATA_STRINGS,
    BOOLEAN_OFF_STRINGS,
    BOOLEAN_ON_STRINGS,
    TEMPERATURE_KEYWORDS,
    PERCENTAGE_KEYWORDS,
    ENERGY_POWER_KEYWORDS,
)

_LOGGER = logging.getLogger(__name__)

class WemPortalScraper:
    """Scraper for navigating and extracting data from WEM Portal using curl_cffi."""

    def __init__(self, username, password, cookie=None):
        self.username = username
        self.password = password
        self.cookie = cookie if cookie else {}
        self.session = requests.Session(impersonate="chrome110")
        
    def scrape(self):
        """Perform the scraping process and return the extracted data."""
        # 1. GET Login page
        try:
            r1 = self.session.get(WEB_LOGIN_URL)
            if r1.status_code != 200:
                raise AuthError(f"Authentication Error: Received {r1.status_code} on login page.")
        except Exception as e:
            raise AuthError(f"Authentication Error: {e}")

        tree = html.fromstring(r1.text)
        viewstate_elem = tree.xpath("//*[@id='__VIEWSTATE']/@value")
        eventval_elem = tree.xpath("//*[@id='__EVENTVALIDATION']/@value")
        
        if not viewstate_elem or not eventval_elem:
            raise AuthError("Authentication Error: Could not find VIEWSTATE or EVENTVALIDATION.")
            
        viewstate = viewstate_elem[0]
        eventval = eventval_elem[0]

        # 2. POST Login
        login_data = {
            "__VIEWSTATE": viewstate,
            "__EVENTVALIDATION": eventval,
            "ctl00$content$tbxUserName": self.username,
            "ctl00$content$tbxPassword": self.password,
            "ctl00$content$btnLogin": "Anmelden",
        }
        
        r2 = self.session.post(WEB_LOGIN_URL, data=login_data, allow_redirects=True)
        if r2.status_code != 200:
            raise AuthError(f"Authentication Error: Encountered error after login. Received {r2.status_code}.")

        # Check if we were redirected back to login with an error (like AspxAutoDetectCookieSupport)
        if "AspxAutoDetectCookieSupport" in r2.url or WEB_LOGIN_URL.lower() in r2.url.lower():
            raise AuthError(f"Authentication Error: Login failed or cookies not detected. URL: {r2.url}")

        # Wait a moment
        time.sleep(2)
        
        # 3. GET Default.aspx
        r_main = self.session.get(WEB_MAIN_URL)
        tree_main = html.fromstring(r_main.text)
        
        viewstate_main_elem = tree_main.xpath("//*[@id='__VIEWSTATE']/@value")
        eventval_main_elem = tree_main.xpath("//*[@id='__EVENTVALIDATION']/@value")
        pageview_main_elem = tree_main.xpath("//*[@id='__ECNPAGEVIEWSTATE']/@value")
        
        if not viewstate_main_elem or not eventval_main_elem:
            raise AuthError("Scraping Error: Could not find VIEWSTATE on main page.")

        form_data = {
            "__EVENTVALIDATION": eventval_main_elem[0],
            "__VIEWSTATE": viewstate_main_elem[0],
            "__ECNPAGEVIEWSTATE": pageview_main_elem[0] if pageview_main_elem else "",
            "__EVENTTARGET": "ctl00$SubMenuControl1$subMenu",
            "__EVENTARGUMENT": "3",
            "ctl00_rdMain_ClientState": '{"Top":0,"Left":0,"DockZoneID":"ctl00_RDZParent","Collapsed":false,"Pinned":false,"Resizable":false,"Closed":false,"Width":"99%","Height":null,"ExpandedHeight":0,"Index":0,"IsDragged":false}',
            "ctl00_SubMenuControl1_subMenu_ClientState": '{"logEntries":[{"Type":3},{"Type":1,"Index":"0","Data":{"text":"Overview","value":"110"}},{"Type":1,"Index":"1","Data":{"text":"System:+dom","value":""}},{"Type":1,"Index":"2","Data":{"text":"User","value":"222"}},{"Type":1,"Index":"3","Data":{"text":"Expert","value":"223","selected":true}},{"Type":1,"Index":"4","Data":{"text":"Statistics","value":"225"}},{"Type":1,"Index":"5","Data":{"text":"Data+Loggers","value":"224"}}],"selectedItemIndex":"3"} ',
        }

        # 4. POST to select 'Expert' tab
        r_expert = self.session.post(WEB_MAIN_URL, data=form_data, allow_redirects=True)
        
        # 5. Extract data
        return self.parse_expert_page(r_expert.text)

    def parse_expert_page(self, html_content):
        _LOGGER.debug("Parsing expert page HTML")
        output = {}
        tree = html.fromstring(html_content)
        
        for div in tree.xpath('//div[contains(@class, "RadPanelBar RadPanelBar_Default rpbSimpleData")]'):
            header_elems = div.xpath('.//th[contains(@class, "simpleDataHeaderTextCell")]/span/text()')
            if header_elems:
                header_raw = header_elems[0].strip()
                header = (
                    header_elems[0].replace("/#", "")
                    .replace("  ", "")
                    .replace(" - ", "_")
                    .replace("/*+/*", "_")
                    .replace(" ", "_")
                    .casefold()
                )
            else:
                header_raw = "Unknown"
                header = "unknown"
                continue
                
            for td in div.xpath('.//div[contains(@class, "rpTemplate")]/table[contains(@class, "simpleDataTable")]/tbody/tr'):
                try:
                    name_elems = td.xpath('.//td[contains(@class, "simpleDataNameCell")]/span/text()')
                    val_elems = td.xpath('.//td[contains(@class, "simpleDataValueCell") or contains(@class, "simpleDataValueEnumCell")]/span/text()')
                    
                    if name_elems and val_elems:
                        raw_name = name_elems[0].strip()
                        friendly_name = f"{header_raw} - {raw_name.lstrip('- ')}"
                        
                        name = name_elems[0].replace("  ", "").replace(" ", "_").casefold()
                        name = header + "-" + name
                        original_value = val_elems[0].strip()
                        value = original_value
                        
                        split_value = value.split(" ", 1)
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
                            # If it's not a number, revert to the full string
                            value = original_value
                            unit = None

                        if not unit:
                            name_lower = name.lower()
                            if any(x in name_lower for x in TEMPERATURE_KEYWORDS):
                                unit = '°C'
                            elif any(x in name_lower for x in PERCENTAGE_KEYWORDS):
                                unit = '%'

                        # Handle missing or boolean values
                        value_lower = str(value).lower() if isinstance(value, str) else value
                        if value_lower in MISSING_DATA_STRINGS:
                            # Energy/Power sensors MUST be None to avoid Energy Dashboard spikes.
                            name_lower = name.lower()
                            if any(x in name_lower for x in ENERGY_POWER_KEYWORDS):
                                value = None
                            else:
                                value = 0.0
                        elif value_lower in BOOLEAN_OFF_STRINGS:
                            value = 0.0 if unit else "Off"
                        elif value_lower in BOOLEAN_ON_STRINGS:
                            value = 1.0 if unit else "On"

                        icon_mapper = defaultdict(lambda: "mdi:flash")
                        icon_mapper["°C"] = "mdi:thermometer"

                        output[name] = {
                            "value": value,
                            "name": name,
                            "icon": icon_mapper[unit],
                            "unit": unit,
                            "platform": "sensor",
                            "friendlyName": friendly_name,
                            "ParameterID": name,
                        }
                except (IndexError, ValueError):
                    continue

        # Save cookies for next run (extracted from requests Session)
        cookies_dict = dict(self.session.cookies)
        output["cookie"] = cookies_dict
        return [output]
