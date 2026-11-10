"""Web scraping scraper for WEM Portal using curl_cffi."""

import asyncio
import logging

from curl_cffi import requests
from lxml import html

from custom_components.wemportal.const import (
    BOOLEAN_OFF_STRINGS,
    BOOLEAN_ON_STRINGS,
    MISSING_DATA_STRINGS,
    PERCENTAGE_KEYWORDS,
    TEMPERATURE_KEYWORDS,
    WEB_LOGIN_URL,
    WEB_MAIN_URL,
)
from custom_components.wemportal.exceptions import AuthError, WemPortalError

_LOGGER = logging.getLogger(__name__)


def _parse_value(raw_value: str, name: str) -> tuple[float | str | None, str | None]:
    """Split a value cell like "12,5 °C" into its value and unit."""
    number, _, unit = raw_value.partition(" ")
    lowered = raw_value.lower()
    if lowered in BOOLEAN_OFF_STRINGS:
        value, unit = 0.0, None
    elif lowered in BOOLEAN_ON_STRINGS:
        value, unit = 1.0, None
    elif lowered == "--" and "anforderung" in name and "leistung" not in name:
        # "Anforderung" is "--" outside the regenerative mode, not a missing sensor
        value, unit = 0.0, "°C"
    elif lowered == "--" and "soll" in name and "leistung" not in name:
        # Setpoint is "--" by design in regenerative mode, not a missing sensor
        value, unit = 0.0, None
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

    def __init__(self, username, password):
        self.username = username
        self.password = password

    async def login(self):
        """Log in to check the credentials."""
        async with requests.AsyncSession(impersonate="chrome110") as session:
            await self._login(session)

    async def scrape(self):
        """Perform the scraping process and return the extracted data."""
        async with requests.AsyncSession(impersonate="chrome110") as session:
            await self._login(session)
            return await self._scrape_expert_page(session)

    async def _login(self, session):
        """Log in to the web portal with a browser-like session.

        Only a rejected login raises AuthError, as that stops the polling. Anything
        else raises WemPortalError, so the next poll tries again.
        """
        try:
            r1 = await session.get(WEB_LOGIN_URL)
        except requests.RequestsError as exc:
            raise WemPortalError(f"Could not open the login page: {exc}") from exc
        if r1.status_code != 200:
            raise WemPortalError(f"Received {r1.status_code} on the login page")

        tree = html.fromstring(r1.text)
        viewstate_elem = tree.xpath("//*[@id='__VIEWSTATE']/@value")
        eventval_elem = tree.xpath("//*[@id='__EVENTVALIDATION']/@value")
        if not viewstate_elem or not eventval_elem:
            raise WemPortalError("Could not find VIEWSTATE or EVENTVALIDATION on the login page")

        login_data = {
            "__VIEWSTATE": viewstate_elem[0],
            "__EVENTVALIDATION": eventval_elem[0],
            "ctl00$content$tbxUserName": self.username,
            "ctl00$content$tbxPassword": self.password,
            "ctl00$content$btnLogin": "Anmelden",
        }
        try:
            r2 = await session.post(WEB_LOGIN_URL, data=login_data, allow_redirects=True)
        except requests.RequestsError as exc:
            raise WemPortalError(f"Could not submit the login form: {exc}") from exc
        if r2.status_code != 200:
            raise WemPortalError(f"Received {r2.status_code} after logging in")

        if "AspxAutoDetectCookieSupport" in r2.url:
            raise WemPortalError(f"The portal didn't detect the session cookies. URL: {r2.url}")
        if WEB_LOGIN_URL.lower() not in r2.url.lower():
            return
        # The portal shows the login form again when it rejects the credentials
        if html.fromstring(r2.text).xpath("//input[@name='ctl00$content$tbxUserName']"):
            raise AuthError("Authentication Error: The WEM Portal rejected the username or password")
        raise WemPortalError(f"Login failed with an unexpected page. URL: {r2.url}")

    async def _scrape_expert_page(self, session):
        """Open the expert page and return the extracted data."""
        # Wait a moment
        await asyncio.sleep(2)

        # 3. GET Default.aspx
        r_main = await session.get(WEB_MAIN_URL)
        tree_main = html.fromstring(r_main.text)
        
        viewstate_main_elem = tree_main.xpath("//*[@id='__VIEWSTATE']/@value")
        eventval_main_elem = tree_main.xpath("//*[@id='__EVENTVALIDATION']/@value")
        pageview_main_elem = tree_main.xpath("//*[@id='__ECNPAGEVIEWSTATE']/@value")
        
        if not viewstate_main_elem or not eventval_main_elem:
            raise WemPortalError("Scraping Error: Could not find VIEWSTATE on main page.")

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
        r_expert = await session.post(WEB_MAIN_URL, data=form_data, allow_redirects=True)
        
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

        return output
