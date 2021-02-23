# hass-WEM-Portal

[![buy me a coffee](https://img.shields.io/badge/If%20you%20like%20it-Buy%20me%20a%20coffee-yellow.svg?style=for-the-badge)](https://www.buymeacoffee.com/erikkastelec)

Custom component for retrieving sensor information from Weishaupt WEM Portal.  
Component uses webscraping to get all the sensor data from the Weishaupt WEM Portal (Expert view) and makes it available
in [Home Assistant](https://home-assistant.io/).

## Installation

Full restart of the Home Assistant is required. Restarting from GUI won't work, due to missing dependencies.

## Configuration

Configuration variables:
- `username`: Email address used for login into WEM Portal
- `password`: : Email address used for login into WEM Portal
- `scan_interval (Optional)`: Defines update frequency. Optional and in seconds (defaults to 30 min, minimum value is 15
  min).

Add the following to your `configuration.yaml` file:

```yaml
# Example configuration.yaml entry
sensor:
  - platform: wemportal
    #scan_interval: 1800
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