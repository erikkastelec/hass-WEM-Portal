# hass-WEM-Portal

[![buy me a coffee](https://img.shields.io/badge/If%20you%20like%20it-Buy%20me%20a%20coffee-yellow.svg?style=for-the-badge)](https://www.buymeacoffee.com/erikkastelec)

Custom component for retrieving sensor information from Weishaupt WEM Portal.  
Component uses webscraping to get all the sensor data from the Weishaupt WEM Portal (Expert view) and makes it available
in [Home Assistant](https://home-assistant.io/).

## Installation

Full restart of the Home Assistant is required. Restarting from GUI won't work, due to missing dependencies.

## Configuration

Entities specified under resources are added to home-assistant.  
Make sure to copy the exact name of the entity from the config example below, as some of them are misspelled (they are
also misspelled on the Weishaupt WEM Portal).

Configuration variables:

- `username`: Email address used for login into WEM Portal
- `password`: : Email address used for login into WEM Portal
- `scan_interval (Optional)`: Defines update frequency. Optional and in seconds (defaults to 30 min, minimum value is 15
  min).
- `resources`: list of entities, which will be added to home-assistant

Add the following to your `configuration.yaml` file:

```yaml
# Example configuration.yaml entry
sensor:
  - platform: wemportal
    #scan_interval: 1800
    username: your_username
    password: your_password
    resources:
      - heating_circuit_1-outside_temperature
      - heating_circuit_1-long_term_outside
      - heating_circuit_1-room_temperature
      - heating_circuit_1-flow_set_temperature
      - heating_circuit_1-flow_temperature
      - heating_circuit_1-version_R130
      - heating_circuit_2-outside_temperature
      - heating_circuit_2-outside_average
      - heating_circuit_2-long_term_outside
      - heating_circuit_2-room_setpoint
      - heating_circuit_2-flow_temperature
      - heating_circuit_2-pump
      - heating_circuit_2-flow_set_temperature
      - heating_circuit_2-version_WWP-EM-HK
      - heat_pump-hot_water_temperature
      - heat_pump-power_requirement
      - heat_pump-dynamic_switching
      - heat_pump-LWT
      - heat_pump-return_temperature
      - heat_pump-pump_speed
      - heat_pump-volume_flow
      - heat_pump-change_valve
      - heat_pump-version_WWP-SG
      - heat_pump-version_CPU
      - heat_pump-set_frequency_compressor
      - heat_pump-frequency_compressor
      - heat_pump-outside_OAT
      - heat_pump-heat_exchanger_ODU_entry
      - heat_pump-OMT
      - heat_pump-outside_CTT
      - heat_pump-hydraulic_unit_ICT
      - heat_pump-hydraulic_unit_IRT
      - heat_pump-operating_hours_compresso
      - heat_pump-switchings_compressor
      - heat_pump-switching_defrost
      - heat_pump-variant
      - 2.WEZ-EP_1
      - 2.WEZ-EP_2
      - 2.WEZ-operating_hours_E1
      - 2.WEZ-operating_hours_E2
      - 2.WEZ-switchings_E1
      - 2.WEZ-switching_E2
      - statistics-consuption_day
      - statistics-consuption_months
      - statistics-consuption_year
      - statistics-heat_consuption_day
      - statistics-heat_consuption_month
      - statistics-heat_consuption_year
      - statistics-hot_water_consuption_day
      - statistics-hot_water_consuption_mont
      - statistics-hot_water_consuption_year
      - statistics-cool_consuption_day
      - statistics-cool_consuption_month
      - statistics-cool_consuption_year
```

## Troubleshooting

Please set your logging for the custom_component to debug:

```yaml
logger:
  default: warn
  logs:
    custom_components.wemportal: debug
```