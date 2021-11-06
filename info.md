# hass-WEM-Portal

[![buy me a coffee](https://img.shields.io/badge/If%20you%20like%20it-Buy%20me%20a%20coffee-yellow.svg?style=for-the-badge)](https://www.buymeacoffee.com/erikkastelec)

Custom component for retrieving sensor information from Weishaupt WEM Portal.  
Component uses webscraping, as well as Weishaupt mobile API, to get all the sensor data from the Weishaupt WEM Portal (
Expert view) and makes it available in [Home Assistant](https://home-assistant.io/).

## Installation

Full restart of the Home Assistant is required. Restarting from GUI won't work, due to missing dependencies.

## Configuration

Configuration variables:

- `username`: Email address used for logging into WEM Portal
- `password`: Password used for logging into WEM Portal
- `scan_interval (Optional)`: Defines update frequency of web scraping. Optional and in seconds (defaults to 30 min).
  Setting update frequency bellow 15 min is not recommended.
- `api_scan_interval (Optional)`: Defines update frequency for API data fetching. Optional and in seconds (defaults to 5
  min).
- `language (
  Optional)`: Defines preferred language. Use `en` for English translation or `de` for German. (defaults to en (
  English))
- `mode (Optional)`: Defines the mode of data fetching. Defaults to `both`, which queries website and api and provides
  all the available data. Option `web` gets only the data on the website, while option `api` gets only the data
  available through the mobile API.

Add the following to your `configuration.yaml` file:

```yaml
# Example configuration.yaml entry
sensor:
  - platform: wemportal
    #scan_interval: 1800
    #api_scan_interval: 300
    #language: en
    #mode: both
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