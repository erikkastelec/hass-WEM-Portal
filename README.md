[![hacs_badge](https://img.shields.io/badge/HACS-Default-orange.svg?style=for-the-badge)](https://github.com/custom-components/hacs)
[![buy me a coffee](https://img.shields.io/badge/If%20you%20like%20it-Buy%20me%20a%20coffee-yellow.svg?style=for-the-badge)](https://www.buymeacoffee.com/erikkastelec)
[![License](https://img.shields.io/github/license/toreamun/amshan-homeassistant?style=for-the-badge)](LICENSE)

# hass-WEM-Portal

Custom component for retrieving sensor information from Weishaupt WEM Portal.  
Component uses webscraping, as well as Weishaupt mobile API, to get all the sensor data from the Weishaupt WEM Portal (
Expert view) and makes it available in [Home Assistant](https://home-assistant.io/).

## Installation

### HACS (preferred method)

- In [HACS](https://github.com/hacs/default) Store search for erikkastelec/hass-WEM-Portal and install it
- Activate the component by adding configuration into your `configuration.yaml` file.

### Manual install

Create a directory called `wemportal` in the `<config directory>/custom_components/` directory on your Home Assistant
instance. Install this component by copying all files in `/custom_components/wemportal/` folder from this repo into the
new `<config directory>/custom_components/wemportal/` directory you just created.

This is how your custom_components directory should look like:

```bash
custom_components
├── wemportal
│   ├── __init__.py
│   ├── const.py
│   ├── manifest.json
│   ├── coordinator.py
│   ├── select.py
│   ├── number.py
│   ├── sensor.py
│   └── wemportalapi.py  
```

## Configuration

Configuration variables:

- `username`: Email address used for logging into WEM Portal
- `password`: Password used for logging into WEM Portal
- `scan_interval (Optional)`: Defines update frequency of web scraping. Optional and in seconds (defaults to 30 min).
  Setting update frequency bellow 15 min is not recommended.
- `api_scan_interval (Optional)`: Defines update frequency for API data fetching. Optional and in seconds (defaults to 5
  min, should not be lower than 3 min).
- `language (
  Optional)`: Defines preferred language. Use `en` for English translation or `de` for German. (defaults to en (
  English))
- `mode (Optional)`: Defines the mode of data fetching. Defaults to `api`, which gets the data available through the
  mobile API. Option `web` gets only the data on the website, while option `both` queries website and api and provides
  all the available data from both sources.

Add the following to your `configuration.yaml` file:

```yaml
# Example configuration.yaml entry
wemportal:
  #scan_interval: 1800
  #api_scan_interval: 300
  #language: en
  #mode: api
  username: your_username
    password: your_password
```

## Troubleshooting
Please set your logging for the custom_component to debug:
```yaml
logger:
  default: warn
  logs:
    custom_components.wemportal: debug
```
