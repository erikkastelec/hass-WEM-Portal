"""
Gets sensor data from Weishaupt WEM portal using web scraping.
Author: erikkastelec
https://github.com/erikkastelec/hass-WEM-Portal
"""
import time
from collections import defaultdict

import scrapyscript
from scrapy import FormRequest, Spider

from .const import (
    START_URLS, _LOGGER
)


class WemPortalApi(object):
    """ Wrapper class for Weishaupt WEM Portal"""

    def __init__(self, username, password):
        self.data = None
        self.username = username
        self.password = password

    def fetch_data(self):
        """Call spider to crawl WEM Portal"""
        wemportalJob = scrapyscript.Job(WemPortalSpider, self.username, self.password)
        processor = scrapyscript.Processor(settings=None)
        data = None
        try:
            data = processor.run([wemportalJob])[0]
        except IndexError:
            _LOGGER.exception('There was a problem with getting data from WEM Portal. If this problem persists, '
                              'open an issue at https://github.com/erikkastelec/hass-WEM-Portal/issues')
        try:
            if data['authErrorFlag']:
                _LOGGER.exception('AuthenticationError: Could not login with provided username and password. Check if '
                                  'your config contains the right credentials')
        except KeyError:
            """If authentication was successful"""
            pass
        return data


class WemPortalSpider(Spider):
    name = 'WemPortalSpider'
    start_urls = START_URLS

    def __init__(self, username, password, **kw):
        self.username = username
        self.password = password
        self.authErrorFlag = False
        super().__init__(**kw)

    def parse(self, response):
        """Login to WEM Portal"""
        return FormRequest.from_response(response,
                                         formdata={
                                             'ctl00$content$tbxUserName': self.username,
                                             'ctl00$content$tbxPassword': self.password,
                                             'Accept-Language': 'en-US,en;q=0.5'
                                         },
                                         callback=self.navigate_to_expert_page)

    def navigate_to_expert_page(self, response):
        # sleep for 5 seconds to get proper language and updated data
        time.sleep(5)
        _LOGGER.debug("Print user page HTML: %s", response.text)
        if response.url == 'https://www.wemportal.com/Web/login.aspx?AspxAutoDetectCookieSupport=1':
            _LOGGER.debug("Authentication failed")
            self.authErrorFlag = True
            form_data = {}
        else:
            _LOGGER.debug("Authentication successful")
            form_data = self.generate_form_data(response)
            _LOGGER.debug("Form data processed")
        return FormRequest(url='https://www.wemportal.com/Web/default.aspx',
                           formdata=form_data,
                           headers={
                               'Content-Type': 'application/x-www-form-urlencoded',
                               'Cookie': response.request.headers.getlist('Cookie')[0].decode("utf-8"),
                               'Accept-Language': 'en-US,en;q=0.5'
                           },
                           method='POST',
                           callback=self.scrape_pages)

    def generate_form_data(self, response):
        """prepares form data for request, which simulates a click on "Expert" element in submenu"""
        return {
            "__EVENTVALIDATION": response.xpath("//*[@id='__EVENTVALIDATION']/@value")[0].extract(),
            "__VIEWSTATE": response.xpath("//*[@id='__VIEWSTATE']/@value")[0].extract(),
            "__ECNPAGEVIEWSTATE": response.xpath("//*[@id='__ECNPAGEVIEWSTATE']/@value")[0].extract(),
            "__EVENTTARGET": 'ctl00$SubMenuControl1$subMenu',
            "__EVENTARGUMENT": '3',
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
                                                         '"selectedItemIndex":"3"} '
        }

    def scrape_pages(self, response):
        # sleep for 2 seconds to get proper language and updated data
        time.sleep(2)
        _LOGGER.debug("Print expert page HTML: %s", response.text)
        if self.authErrorFlag:
            yield {'authErrorFlag': True}
        _LOGGER.debug("Scraping page")
        output = {}
        for i, div in enumerate(response.xpath('//div[@class="RadPanelBar RadPanelBar_Default rpbSimpleData"]')):
            header_query = "//span[@id='ctl00_rdMain_C_controlExtension_rptDisplayContent_ctl0" + str(
                i) + "_ctl00_rpbGroupData_i0_HeaderTemplate_lblHeaderText']/text() "
            # Catch heading not starting at 0
            try:
                header = div.xpath(header_query).extract()[0]
                header = header.replace("  ", "").replace(" ", "_").lower()
            except IndexError:
                header = "unknown"
                continue
            for td in div.xpath('.//table[@class="simpleDataTable"]//tr'):
                try:
                    name = td.xpath('.//td//span[@class="simpleDataName"]/text()').extract()[0]
                    value = td.xpath('.//td//span[@class="simpleDataValue"]/text()').extract()[0]
                    name = name.replace("  ", "").replace(" ", "_").lower()
                    name = header + '-' + name
                    split_value = value.split(' ')
                    unit = ""
                    if len(split_value) >= 2:
                        value = split_value[0]
                        unit = split_value[1]
                    else:
                        value = split_value[0]
                    try:
                        value = int(value)
                    except ValueError:
                        pass

                    icon_mapper = defaultdict(lambda: "mdi:flash")
                    icon_mapper['°C'] = "mdi:thermometer"

                    output[name] = (value, icon_mapper[unit], unit)
                except IndexError:
                    continue

        yield output
