""" Constants for the WEM Portal Integration """
import logging
from typing import Final

_LOGGER = logging.getLogger("custom_components.wemportal")
DOMAIN: Final = "wemportal"
GITHUB_PROJECT_URL: Final = "https://github.com/erikkastelec/hass-WEM-Portal/issues"
DEFAULT_NAME: Final = "Weishaupt WEM Portal"
DEFAULT_TIMEOUT: Final = 360
WEB_MAIN_URL: Final = "https://www.wemportal.com/Web/Default.aspx"
WEB_LOGIN_URL: Final = "https://www.wemportal.com/Web/Login.aspx"
CONF_SCAN_INTERVAL_API: Final = "api_scan_interval"
CONF_LANGUAGE: Final = "language"
CONF_MODE: Final = "mode"
PLATFORMS = ["number", "select", "sensor", "switch"]
REFRESH_WAIT_TIME: Final = 360
DATA_GATHERING_ERROR: Final = "An error occurred while gathering data.This issue should resolve by itself. If this problem persists,open an issue at https://github.com/erikkastelec/hass-WEM-Portal/issues"
DEFAULT_CONF_SCAN_INTERVAL_API_VALUE: Final = 300
DEFAULT_CONF_SCAN_INTERVAL_VALUE: Final = 1800
DEFAULT_CONF_LANGUAGE_VALUE: Final = "en"
DEFAULT_CONF_MODE_VALUE: Final = "api"
API_LOGIN_URL: Final = "https://www.wemportal.com/app/Account/Login"
API_DEVICE_READ_URL: Final = "https://www.wemportal.com/app/Device/Read"
API_EVENT_TYPE_READ_URL: Final = "https://www.wemportal.com/app/EventType/Read"
API_DATA_ACCESS_WRITE_URL: Final = "https://www.wemportal.com/app/DataAccess/Write"
API_DATA_ACCESS_READ_URL: Final = "https://www.wemportal.com/app/DataAccess/Read"
API_REFRESH_URL: Final = "https://www.wemportal.com/app/DataAccess/Refresh"
