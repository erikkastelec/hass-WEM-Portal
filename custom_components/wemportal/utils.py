def fix_unit_of_measurement(uom: str) -> str:
    """Fix the unit of measurement. WEM Portal uses "kW (W)" for "W" and "kW (W)h" for "Wh". Also fix the casing of some units."""

    return {
        "w": "W",
        "kw": "kW",
        "kwh": "kWh",
        "kw (w)": "W",
        "kw (w)h": "Wh",
    }.get(uom.lower(), uom)
