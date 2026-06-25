"""Utility functions for WEM Portal."""

from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import (
    UnitOfEnergy,
    UnitOfPower,
    UnitOfVolumeFlowRate,
    UnitOfTemperature,
    UnitOfTime,
    UnitOfFrequency,
)

from .const import (
    MISSING_DATA_STRINGS,
    BOOLEAN_OFF_STRINGS,
    BOOLEAN_ON_STRINGS,
    ENERGY_POWER_KEYWORDS
)

def sanitize_value(value_str, unit=None, name=""):
    """Sanitize typical German strings or off states to numeric values based on constants."""
    if not isinstance(value_str, str):
        return value_str
        
    val_lower = value_str.lower().strip()
    
    if val_lower in [x.strip() for x in MISSING_DATA_STRINGS]:
        name_lower = name.lower()
        if any(x in name_lower for x in ENERGY_POWER_KEYWORDS):
            return None
        return 0.0
    
    if val_lower in BOOLEAN_OFF_STRINGS:
        return 0.0 if unit else "Off"
    if val_lower in BOOLEAN_ON_STRINGS:
        return 1.0 if unit else "On"
        
    try:
        return float(value_str)
    except ValueError:
        return value_str

def fix_value_and_uom(val, uom):
    """
    Translate WEM specific values and units of measurement to Home Assistant.

    This function returns:
      * a valid Home Assistant UoM if it can be mapped 
        (see: https://github.com/home-assistant/core/blob/dev/homeassistant/const.py)
      * an empty string as UoM if the value is a number without any indication 
        of its unit of measurement (e.g., a counter)
      * None as UoM if the value is a string without any indication 
        of its unit of measurement (e.g., a status text)
    """

    # special case: volume flow rate
    if isinstance(val, str) and val.endswith("m3/h"):
        return float(val.replace("m3/h", "")), UnitOfVolumeFlowRate.CUBIC_METERS_PER_HOUR

    # special case: no unit of measurement
    if uom is None:
        return val, None

    # special case: empty string for unit of measurement for a number
    if uom == "":
        try:
            return float(val), ""
        except (ValueError, TypeError):
            return val, None

    uom = {
        "":         None,
        "w":        UnitOfPower.WATT,
        "kw (w)":   UnitOfPower.WATT,
        "kw":       UnitOfPower.KILO_WATT,
        "kwh":      UnitOfEnergy.KILO_WATT_HOUR,
        "kw (w)h":  UnitOfEnergy.WATT_HOUR,
        "h":        UnitOfTime.HOURS,
        "hz":       UnitOfFrequency.HERTZ,
        "m3/h":     UnitOfVolumeFlowRate.CUBIC_METERS_PER_HOUR
    }.get(uom.lower(), uom)
    return val, uom

def uom_to_device_class(uom):
    """Return the device_class of this unit of measurement, if any."""

    # see: <https://developers.home-assistant.io/docs/core/entity/sensor/#available-device-classes>
    return {
        "%": SensorDeviceClass.POWER_FACTOR,
        UnitOfTemperature.CELSIUS:                  SensorDeviceClass.TEMPERATURE,
        UnitOfTemperature.KELVIN:                   SensorDeviceClass.TEMPERATURE,
        UnitOfEnergy.KILO_WATT_HOUR:                SensorDeviceClass.ENERGY,
        UnitOfEnergy.WATT_HOUR:                     SensorDeviceClass.ENERGY,
        UnitOfPower.KILO_WATT:                      SensorDeviceClass.POWER,
        UnitOfPower.WATT:                           SensorDeviceClass.POWER,
        UnitOfTime.HOURS:                           SensorDeviceClass.DURATION,
        UnitOfFrequency.HERTZ:                      SensorDeviceClass.FREQUENCY,
        UnitOfVolumeFlowRate.CUBIC_METERS_PER_HOUR: SensorDeviceClass.VOLUME_FLOW_RATE,
    }.get(uom, None) # return None if no device class is available

def uom_to_state_class(uom):
    """Return the state class of this unit of measurement, if any."""

    # see: <https://developers.home-assistant.io/docs/core/entity/sensor/#available-state-classes>
    return {
        "":                                         SensorStateClass.MEASUREMENT,
        "%":                                        SensorStateClass.MEASUREMENT,
        UnitOfTemperature.CELSIUS:                  SensorStateClass.MEASUREMENT,
        UnitOfTemperature.KELVIN:                   SensorStateClass.MEASUREMENT,
        UnitOfEnergy.KILO_WATT_HOUR:                SensorStateClass.TOTAL_INCREASING,
        UnitOfEnergy.WATT_HOUR:                     SensorStateClass.TOTAL_INCREASING,
        UnitOfPower.KILO_WATT:                      SensorStateClass.MEASUREMENT,
        UnitOfPower.WATT:                           SensorStateClass.MEASUREMENT,
        UnitOfTime.HOURS:                           SensorStateClass.TOTAL_INCREASING,
        UnitOfFrequency.HERTZ:                      SensorStateClass.MEASUREMENT,
        UnitOfVolumeFlowRate.CUBIC_METERS_PER_HOUR: SensorStateClass.MEASUREMENT,
    }.get(uom, None) # return None if no state class is available
