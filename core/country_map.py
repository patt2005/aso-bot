"""Mapping between ISO country codes (from our seed endpoint) and upup country_id.

upup uses internal numeric ids (e.g. 24 = US, 25 = RO, 48 = CZ). Extracted from
the upup web app's JS bundle (country list with id + name_en_addr fields), so
this is the full canonical list — adding a new country in Apple Search Ads
just works without code changes.
"""

ISO_TO_UPUP: dict[str, int] = {
    "AE": 67, "AF": 149, "AG": 123, "AI": 209, "AL": 62, "AM": 106, "AO": 122,
    "AR": 11, "AT": 34, "AU": 41, "AZ": 109, "BA": 35, "BB": 161, "BE": 1,
    "BF": 58, "BG": 51, "BH": 111, "BJ": 91, "BM": 176, "BN": 194, "BO": 64,
    "BR": 3, "BS": 210, "BT": 186, "BW": 148, "BY": 81, "BZ": 164, "CA": 78,
    "CD": 46, "CG": 92, "CH": 8, "CI": 66, "CL": 15, "CM": 54, "CN": 75,
    "CO": 12, "CR": 38, "CV": 76, "CY": 89, "CZ": 48, "DE": 13, "DK": 10,
    "DM": 178, "DO": 154, "DZ": 70, "EC": 59, "EE": 96, "EG": 57, "ES": 9,
    "ET": 150, "FI": 60, "FJ": 165, "FM": 217, "FR": 2, "GA": 90, "GB": 4,
    "GD": 242, "GE": 94, "GH": 49, "GM": 163, "GR": 43, "GT": 145, "GW": 118,
    "GY": 175, "HK": 141, "HN": 61, "HR": 5, "HU": 52, "ID": 159, "IE": 31,
    "IL": 84, "IN": 101, "IR": 22, "IS": 40, "IT": 17, "JM": 56, "JO": 97,
    "JP": 26, "KE": 108, "KG": 95, "KH": 173, "KN": 135, "KR": 37, "KW": 157,
    "KY": 206, "KZ": 116, "LA": 184, "LB": 87, "LC": 219, "LK": 202, "LR": 153,
    "LT": 132, "LU": 86, "LV": 133, "LY": 105, "MA": 45, "MD": 171, "ME": 53,
    "MG": 107, "MK": 68, "ML": 65, "MM": 140, "MN": 187, "MO": 183, "MR": 103,
    "MS": 243, "MT": 180, "MU": 156, "MV": 151, "MW": 128, "MX": 18, "MY": 168,
    "MZ": 117, "NA": 113, "NE": 104, "NG": 42, "NI": 129, "NL": 16, "NO": 50,
    "NP": 162, "NR": 244, "NZ": 119, "OM": 88, "PA": 74, "PE": 21, "PG": 169,
    "PH": 124, "PK": 201, "PL": 20, "PT": 7, "PW": 213, "PY": 36, "QA": 55,
    "RO": 25, "RS": 29, "RU": 47, "RW": 138, "SA": 72, "SB": 139, "SC": 192,
    "SE": 14, "SG": 160, "SI": 63, "SK": 32, "SL": 115, "SN": 23, "SR": 152,
    "ST": 185, "SV": 71, "SZ": 144, "TC": 208, "TD": 177, "TH": 114, "TJ": 120,
    "TM": 137, "TN": 28, "TO": 203, "TR": 39, "TT": 93, "TW": 125, "TZ": 131,
    "UA": 27, "UG": 79, "US": 24, "UY": 6, "UZ": 85, "VC": 218, "VE": 30,
    "VG": 207, "VN": 98, "VU": 166, "YE": 146, "YK": 127, "ZA": 73, "ZM": 80,
    "ZW": 110,
}

UPUP_TO_ISO: dict[int, str] = {v: k for k, v in ISO_TO_UPUP.items()}


def to_upup_country(iso_code: str, default: int = 24) -> int:
    return ISO_TO_UPUP.get(iso_code.upper(), default)
