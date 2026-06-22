"""Data mapper for mapping API values to Home Assistant platforms."""

from collections import defaultdict
from .translations import friendly_name_mapper, translate
from .const import WemDataType


def sanitize_value(value_str):
    """Sanitize typical German strings or off states to numeric values."""
    if value_str in ["off", "Aus", "Label ist null", "Label ist null ", "--"]:
        return 0.0
    if value_str in ["Ein"]:
        return 1.0
    try:
        return float(value_str)
    except ValueError:
        return value_str


def get_min_max(param_id: str, data_type: int, min_val, max_val) -> tuple[float, float]:
    try:
        if min_val is not None and max_val is not None:
            return float(min_val), float(max_val)
    except (ValueError, TypeError):
        pass

    if data_type == WemDataType.SWITCH:
        return 0.0, 1.0

    param_lower = param_id.lower()
    if "ww" in param_lower or "warmwasser" in param_lower:
        return 30.0, 65.0
    if any(k in param_lower for k in ["raum", "komfort", "absenk", "normal"]):
        return 5.0, 35.0

    return 0.0, 100.0


class WemPortalDataMapper:
    """Handles mapping of raw API and Scraped data into Home Assistant platforms."""

    @staticmethod
    def process_api_values(
        device_id: str,
        values_json: dict,
        modules_dict: dict,
        language: str,
        scraping_mapper: dict,
        mode: str,
        api_data: dict,
    ):
        """Processes the read values JSON and maps it to api_data."""
        icon_mapper = defaultdict(lambda: "mdi:flash")
        icon_mapper["°C"] = "mdi:thermometer"

        parsed_sensors = {}

        for module in values_json.get("Modules", []):
            module_tuple = (module["ModuleIndex"], module["ModuleType"])
            if module_tuple not in modules_dict[device_id]:
                continue

            device_module = modules_dict[device_id][module_tuple]

            for value in module.get("Values", []):
                param_id = value["ParameterID"]
                if param_id not in device_module["parameters"]:
                    continue

                parameter = device_module["parameters"][param_id]
                name = f"{device_module['Name']}-{parameter['ParameterID']}"

                numeric_val = value.get("NumericValue")
                string_val = value.get("StringValue", "")

                final_value = numeric_val if numeric_val is not None else string_val

                if parameter.get("EnumValues"):
                    final_value = sanitize_value(string_val)
                else:
                    if isinstance(final_value, str):
                        final_value = sanitize_value(final_value)

                is_writeable = parameter.get("IsWriteable", False)
                data_type = parameter.get("DataType")

                translated_name = translate(
                    language,
                    friendly_name_mapper(param_id),
                )
                translated_module_name = translate(language, device_module['Name'].strip())
                
                module_words = set(translated_module_name.lower().split())
                entity_words = set(translated_name.lower().split())
                
                if module_words.issubset(entity_words):
                    friendly_name = translated_name
                else:
                    friendly_name = f"{translated_module_name} {translated_name}"

                parsed_sensors[name] = {
                    "friendlyName": friendly_name,
                    "ParameterID": param_id,
                    "unit": value.get("Unit"),
                    "value": final_value,
                    "IsWriteable": is_writeable,
                    "DataType": data_type,
                    "ModuleIndex": module["ModuleIndex"],
                    "ModuleType": module["ModuleType"],
                }

                if is_writeable:
                    common_attrs = {
                        "friendlyName": parsed_sensors[name]["friendlyName"],
                        "ParameterID": param_id,
                        "unit": value.get("Unit"),
                        "icon": icon_mapper[value.get("Unit")],
                        "value": final_value,
                        "DataType": data_type,
                        "ModuleIndex": module["ModuleIndex"],
                        "ModuleType": module["ModuleType"],
                    }

                    min_val, max_val = get_min_max(
                        param_id, 
                        data_type, 
                        parameter.get("MinValue"), 
                        parameter.get("MaxValue")
                    )

                    if data_type in (WemDataType.NUMBER_STEP_HALF, WemDataType.NUMBER_STEP_ONE):
                        api_data[device_id][name] = {
                            **common_attrs,
                            "platform": "number",
                            "min_value": min_val,
                            "max_value": max_val,
                            "step": 0.5 if data_type == WemDataType.NUMBER_STEP_HALF else 1,
                        }
                    elif data_type == WemDataType.SELECT:
                        api_data[device_id][name] = {
                            **common_attrs,
                            "platform": "select",
                            "options": [x["Value"] for x in parameter.get("EnumValues", [])],
                            "optionsNames": [x["Name"] for x in parameter.get("EnumValues", [])],
                        }
                    elif data_type == WemDataType.SWITCH:
                        if isinstance(final_value, str) and final_value.startswith("{"):
                            pass  # It's a JSON schedule, fallback to sensor
                        elif int(min_val) == 0 and int(max_val) == 1:
                            api_data[device_id][name] = {
                                **common_attrs,
                                "platform": "switch",
                            }
                        else:
                            api_data[device_id][name] = {
                                **common_attrs,
                                "platform": "number",
                                "min_value": min_val,
                                "max_value": max_val,
                                "step": 1,
                            }

        # Process read-only sensors and fallback for unknown writeable datatypes
        for key, sensor in parsed_sensors.items():
            if not sensor["IsWriteable"] or key not in api_data.get(device_id, {}):
                if mode == "both" and len(api_data.keys()) < 2:
                    param_id = sensor["ParameterID"]
                    if param_id not in scraping_mapper:
                        for scraped_entity, scraped_data in api_data[device_id].items():
                            if not isinstance(scraped_data, dict):
                                continue
                            scraped_entity_id = scraped_data.get("ParameterID", "")
                            try:
                                import re
                                scraped_part = scraped_entity_id.split("-")[1]
                                translated_scraped = translate(language, friendly_name_mapper(scraped_part))
                                
                                def tokenize(text):
                                    return set(re.sub(r'[^a-zA-Z0-9äöüß]', ' ', text.lower()).split())
                                    
                                sensor_words = tokenize(sensor["friendlyName"])
                                scraped_words = tokenize(translated_scraped)
                                
                                if scraped_words and scraped_words.issubset(sensor_words):
                                    scraping_mapper.setdefault(param_id, []).append(scraped_entity_id)
                            except IndexError:
                                pass

                        if param_id not in scraping_mapper:
                            scraping_mapper[param_id] = [key]

                    for scraped_entity in scraping_mapper[param_id]:
                        sensor_dict = {
                            "value": sensor.get("value"),
                            "name": api_data[device_id].get(scraped_entity, {}).get("name"),
                            "unit": api_data[device_id].get(scraped_entity, {}).get("unit", sensor.get("unit")),
                            "icon": api_data[device_id].get(scraped_entity, {}).get("icon", icon_mapper[sensor.get("unit")]),
                            "friendlyName": api_data[device_id].get(scraped_entity, {}).get("friendlyName", sensor.get("friendlyName")),
                            "ParameterID": scraped_entity,
                            "platform": "sensor",
                        }
                        if scraped_entity in api_data[device_id]:
                            api_data[device_id][scraped_entity].update(sensor_dict)
                        else:
                            api_data[device_id][scraped_entity] = sensor_dict
                else:
                    new_unit = sensor.get("unit")
                    old_unit = api_data[device_id].get(key, {}).get("unit")
                    final_unit = new_unit if new_unit not in (None, "") else old_unit
                    
                    api_data[device_id][key] = {
                        "value": sensor["value"],
                        "ParameterID": sensor["ParameterID"],
                        "unit": final_unit,
                        "icon": icon_mapper.get(final_unit, "mdi:flash"),
                        "friendlyName": sensor["friendlyName"],
                        "platform": "sensor",
                    }
