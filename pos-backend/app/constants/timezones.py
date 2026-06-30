"""IANA timezone reference data, used to populate the timezone dropdown
on Group/Brand/Site create and edit forms."""

from zoneinfo import available_timezones


def list_timezones() -> list[str]:
    """
    Return all known IANA timezone names, sorted alphabetically.

    Returns:
        list[str]: Sorted IANA timezone names, e.g. ["Africa/Abidjan", ...,
        "Australia/Sydney", ..., "Zulu"].
    """
    return sorted(available_timezones())
