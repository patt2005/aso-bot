"""Mapping between ISO country codes (from our seed endpoint) and upup country_id.

upup uses internal numeric ids (e.g. 24 = US, 37 = Korea). We discover these by
switching country in the upup UI and watching the network — see tools/inspect_upup.py.

TODO: discover Romania's upup country_id and any others not yet listed.
Known so far comes from aso-sheets-service/google_sheets_integration.py.
"""

ISO_TO_UPUP: dict[str, int] = {
    "US": 24,
    "GB": 4,
    "CA": 78,
    "AU": 41,
    "DE": 13,
    "FR": 2,
    "KR": 37,
    "RO": 25,
}

UPUP_TO_ISO: dict[int, str] = {v: k for k, v in ISO_TO_UPUP.items()}


def to_upup_country(iso_code: str, default: int = 24) -> int:
    return ISO_TO_UPUP.get(iso_code.upper(), default)
