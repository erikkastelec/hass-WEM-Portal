"""Translations for WEM Portal."""

def friendly_name_mapper(value: str) -> str:
    friendly_name_dict = {
        "pp_beginn": "party_beginn",
        "pp_ende": "party_ende",
        "pp_funktion": "party_funktion",
        "pp_raumsoll": "party_raumsoll",
        "aktraumsoll": "raumsolltemperatur",
        "u_beginn": "urlaub_beginn",
        "u_ende": "urlaub_ende",
        "u_funktion": "urlaub_funktion",
        "u_raumsoll": "urlaub_raumsoll",
        "ww-push": "warmwasser_push",
        "ww-program": "warmwasser_programm",
        "ww-programm": "warmwasser_programm",
        "aktwwsoll": "warmwassersolltemperatur",
        "leistung": "wärmeleistung",
        "absenk": "absenktemperatur",
        "absenkww": "absenk_warmwasser_temperatur",
        "normalww": "normal_warmwasser_temperatur",
        "komfort": "komforttemperatur",
        "normal": "normaltemperatur",
    }
    try:
        out = friendly_name_dict[value.casefold()]
    except KeyError:
        out = value.casefold()
    return out


def translate(language: str, value: str) -> str:
    value = value.lower()
    
    # Safe word fragments and full words, sorted by length later to match longest first
    vocab = {
        "en": {
            "betriebsart": "operating mode",
            "wärmeerzeuger": "heat generator",
            "heizkreis": "heating circuit",
            "warmwasser": "hot water",
            "außentemperatur": "outside temperature",
            "aussentemperatur": "outside temperature",
            "raumtemperatur": "room temperature",
            "vorlauftemperatur": "flow temperature",
            "warmwassertemperatur": "hot water temperature",
            "kollektortemperatur": "collector temperature",
            "anlagendruck": "system pressure",
            "wärmeleistung": "heat output",
            "raumsolltemperatur": "room setpoint temperature",
            "warmwassersolltemperatur": "hot water setpoint temperature",
            "temperatur": "temperature",
            "vorlauf": "flow",
            "rücklauf": "return",
            "raum": "room",
            "außen": "outside",
            "aussen": "outside",
            "anlage": "system",
            "kollektor": "collector",
            "betriebs": "operating",
            "wärme": "heat",
            "1_wez": "1st heat generator",
            "1.wez": "1st heat generator",
            "2_wez": "2nd heat generator",
            "2.wez": "2nd heat generator",
            "wez": "heat generator",
            "erzeuger": "generator",
            "druck": "pressure",
            "leistung": "output",
            "soll": "setpoint",
            "absenk": "reduced",
            "normal": "normal",
            "komfort": "comfort",
            "party": "party",
            "urlaub": "holiday",
            "funktion": "function",
            "beginn": "begin",
            "ende": "end",
            "push": "push",
            "programm": "program",
            "program": "program",
            "gesamt": "total",
            "energie": "energy",
            "el.": "electrical",
            "kühlen": "cooling",
            "heizen": "heating",
            "kühl": "cooling",
            "heiz": "heating",
            "wasser": "water",
            "consuption": "consumption",
            "compresso": "compressor",
            "mont": "month",
            "months": "month",
            "switching_e2": "switchings e2",
            "oat": "outside air temperature",
            "ctt": "compressor discharge temperature",
            "ict": "indoor coil temperature",
            "irt": "indoor return temperature",
            "omt": "outdoor middle temperature",
            "lwt": "leaving water temperature",
            "odu": "outdoor unit",
            "wwp sg": "wwp sg",
            "wwp em hk": "wwp em hk",
            "r130": "r130",
        }
    }
    
    out = value
    
    if language in vocab:
        # Sort replacements by length descending so longer compound words match first
        replacements = sorted(vocab[language].items(), key=lambda x: len(x[0]), reverse=True)
        
        # Use placeholders to prevent cascading translation bugs
        placeholders = {}
        for i, (de_word, en_word) in enumerate(replacements):
            if de_word in out:
                placeholder = f"__TOKEN_{i}__"
                placeholders[placeholder] = f" {en_word} "
                out = out.replace(de_word, placeholder)
                
        # Resolve placeholders back to English words
        for placeholder, en_word in placeholders.items():
            out = out.replace(placeholder, en_word)
                
    out = out.replace("_", " ")
    # Clean up extra spaces caused by multiple replacements
    out = " ".join(out.split()).title()
    out = out.replace("1St ", "1st ").replace("2Nd ", "2nd ")
    
    return out
