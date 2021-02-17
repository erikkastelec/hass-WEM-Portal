"""
Gets sensor data from Weishaupt WEM portal using web scraping.
Author: erikkastelec
https://github.com/erikkastelec/hass-WEM-Portal
"""

import scrapyscript
from scrapy import FormRequest, Spider

from .const import (
    START_URLS
)


class WemPortalApi(object):
    """ Wrapper class to the Atag One API """

    def __init__(self, username, password):
        self.data = None
        self.username = username
        self.password = password

    def fetch_data(self):
        """Call spider to crawl WEM Portal"""
        wemportalJob = scrapyscript.Job(WemPortalSpider, self.username, self.password)
        processor = scrapyscript.Processor(settings=None)
        data = processor.run([wemportalJob])[0]
        return data


class WemPortalSpider(Spider):
    name = 'WemPortalSpider'
    start_urls = START_URLS
    custom_settings = {

    }

    def __init__(self, username, password, **kw):
        self.username = username
        self.password = password
        super().__init__(**kw)

    def parse(self, response):
        """Login to WEM Portal"""
        return FormRequest.from_response(response,
                                         formdata={
                                             'ctl00$content$tbxUserName': self.username,
                                             'ctl00$content$tbxPassword': self.password
                                         },
                                         callback=self.navigate_to_expert_page)

    def navigate_to_expert_page(self, response):
        form_data = self.generate_form_data(response)
        return FormRequest(url='https://www.wemportal.com/Web/default.aspx',
                           formdata=form_data,
                           headers={
                               'Content-Type': 'application/x-www-form-urlencoded',
                               'Cookie': response.request.headers.getlist('Cookie')[0].decode("utf-8")
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
        output = {}
        for div in response.xpath('//div[@class="RadPanelBar RadPanelBar_Default rpbSimpleData"]'):
            spans = div.xpath('.//span/text()').extract()
            for i in range(1, len(spans), 2):
                index = spans[0].replace("  ", "").replace(" ", "_").lower() + "-" + spans[i].replace("  ", "").replace(
                    " ", "_").lower()
                try:
                    output[index] = int(spans[i + 1].split(' ')[0])
                except ValueError:
                    output[index] = spans[i + 1].split(' ')[0]

        yield output
