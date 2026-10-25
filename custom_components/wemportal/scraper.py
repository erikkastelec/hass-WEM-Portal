"""Web scraping scraper for WEM Portal using curl_cffi."""

import logging
import time
from collections import defaultdict

from curl_cffi import requests
from lxml import html

from custom_components.wemportal.const import (
    BOOLEAN_OFF_STRINGS,
    BOOLEAN_ON_STRINGS,
    ENERGY_POWER_KEYWORDS,
    MISSING_DATA_STRINGS,
    PERCENTAGE_KEYWORDS,
    TEMPERATURE_KEYWORDS,
    WEB_LOGIN_URL,
    WEB_MAIN_URL,
)
from custom_components.wemportal.exceptions import AuthError

_LOGGER = logging.getLogger(__name__)


def _parse_value(raw_value: str, name: str) -> tuple[float | str | None, str | None]:
    """Split a value cell like "12,5 °C" into its value and unit."""
    number, _, unit = raw_value.partition(" ")
    lowered = raw_value.lower()
    if lowered in BOOLEAN_OFF_STRINGS:
        value, unit = 0.0, None
    elif lowered in BOOLEAN_ON_STRINGS:
        value, unit = 1.0, None
    elif lowered in MISSING_DATA_STRINGS:
        value, unit = None, None
    elif not number.strip("-"):
        # A placeholder like "--- °C" means the value is unavailable (e.g. sensor not connected)
        value = None
    else:
        try:
            value = float(number.replace(",", "."))
        except ValueError:
            # Text like "Nein" has no unit
            return raw_value, None

    if not unit:
        if any(x in name for x in TEMPERATURE_KEYWORDS):
            unit = "°C"
        elif any(x in name for x in PERCENTAGE_KEYWORDS):
            unit = "%"
    return value, unit


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
            if not header_elems:
                continue
            # "/*+/*" separates the levels of nested headers
            header_raw = " ".join(
                header_elems[0].replace("/#", "").replace("/*+/*", "-").split()
            )
            header = (
                header_elems[0].replace("/#", "")
                .replace("  ", "")
                .replace(" - ", "_")
                .replace("/*+/*", "_")
                .replace(" ", "_")
                .casefold()
            )

            for td in div.xpath('.//div[contains(@class, "rpTemplate")]/table[contains(@class, "simpleDataTable")]/tbody/tr'):
                name_elems = td.xpath('.//td[contains(@class, "simpleDataNameCell")]/span/text()')
                val_elems = td.xpath('.//td[contains(@class, "simpleDataValueCell") or contains(@class, "simpleDataValueEnumCell")]/span/text()')
                if not name_elems or not val_elems:
                    continue

                name = f'{header}-{name_elems[0].replace("  ", "").replace(" ", "_").casefold()}'
                value, unit = _parse_value(val_elems[0].strip(), name)
                output[name] = {
                    "value": value,
                    "name": name,
                    "icon": "mdi:thermometer" if unit == "°C" else "mdi:flash",
                    "unit": unit,
                    "platform": "sensor",
                    "friendlyName": f"{header_raw} - {name_elems[0].strip().lstrip('- ')}",
                    "ParameterID": name,
                }

        # Save cookies for next run (extracted from requests Session)
        cookies_dict = dict(self.session.cookies)
        output["cookie"] = cookies_dict
        return [output]
