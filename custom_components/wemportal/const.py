""" Constants for the WEM Portal Integration """
import logging
from typing import Final

_LOGGER = logging.getLogger("custom_components.wemportal")
DOMAIN = "wemportal"
DEFAULT_NAME = "Weishaupt WEM Portal"
DEFAULT_TIMEOUT = 360
START_URLS = ["https://www.wemportal.com/Web/login.aspx"]
CONF_SCAN_INTERVAL_API: Final = "api_scan_interval"
CONF_LANGUAGE: Final = "language"
CONF_MODE: Final = "mode"
PLATFORMS = ["sensor", "number", "select", "switch"]
REFRESH_WAIT_TIME: int = 360
DATA_GATHERING_ERROR: Final = "An error occurred while gathering parameters data. \
                    This issue should resolve by itself. If this problem persists, \
                    open an issue at https://github.com/erikkastelec/hass-WEM-Portal/issues "
