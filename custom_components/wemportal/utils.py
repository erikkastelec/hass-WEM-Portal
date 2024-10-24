def fix_unit_of_measurement(uom: str) -> str:
    """Fix the unit of measurement. WEM Portal uses "kW (W)" for "W" and "kW (W)h" for "Wh"."""

    return {
        "kW (W)": "W",
        "kW (W)h": "Wh",
    }.get(uom, uom)
