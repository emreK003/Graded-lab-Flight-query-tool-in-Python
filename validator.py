"""Row validation: airport list loading, single-row checks, record building."""
import math
import re
from datetime import datetime

# Number of columns every data row must have
FIELD_COUNT = 6

# Allowed formats. [0-9] is used instead of \d because \d also accepts
# non-ASCII digits, and fullmatch() is used so nothing extra can follow.
FLIGHT_ID_PATTERN = re.compile(r"[A-Za-z0-9]{2,8}")
AIRPORT_PATTERN = re.compile(r"[A-Z]{3}")
DATETIME_PATTERN = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}")
DATETIME_FORMAT = "%Y-%m-%d %H:%M"


def load_airports(path: str) -> set[str]:
    """Read an airport list file and return the set of codes.

    One code per line. Strip whitespace; skip blank lines and lines
    starting with '#'.
    """
    airports = set()
    with open(path, encoding="utf-8") as f:
        for line in f:
            code = line.strip()
            # Skip empty lines and comment lines
            if code == "" or code.startswith("#"):
                continue
            airports.add(code)
    return airports


def is_valid_datetime(text: str) -> bool:
    """Return True if text is a real date and time written as YYYY-MM-DD HH:MM."""
    # strptime alone is not enough: it also accepts "2025-1-5 9:3",
    # so the exact shape is checked with a regex first.
    if not DATETIME_PATTERN.fullmatch(text):
        return False
    try:
        # This catches impossible values such as month 13 or hour 24
        datetime.strptime(text, DATETIME_FORMAT)
    except ValueError:
        return False
    return True


def is_valid_airport(code: str, airports: set[str]) -> bool:
    """Return True if code is 3 uppercase ASCII letters and in the airport list."""
    return AIRPORT_PATTERN.fullmatch(code) is not None and code in airports


def validate_row(fields: list[str], airports: set[str]) -> str | None:
    """Check one CSV row (fields as returned by csv.reader, not yet stripped).

    Return None if the row is valid, otherwise the error code of the
    FIRST failing check (checks 1-11 in the specification, in order).
    Does not check for duplicates.
    """
    # 1. The row must have exactly 6 fields
    if len(fields) != FIELD_COUNT:
        return "WRONG_FIELD_COUNT"

    # Strip whitespace from every field before checking it
    values = [field.strip() for field in fields]
    flight_id, origin, destination, departure, arrival, price_text = values

    # 2. No field may be empty
    for value in values:
        if value == "":
            return "MISSING_FIELD"

    # 3. Flight id: 2-8 ASCII letters or digits
    if not FLIGHT_ID_PATTERN.fullmatch(flight_id):
        return "INVALID_FLIGHT_ID"

    # 4. and 5. Airport codes
    if not is_valid_airport(origin, airports):
        return "INVALID_ORIGIN"
    if not is_valid_airport(destination, airports):
        return "INVALID_DESTINATION"

    # 6. A flight cannot go to the airport it starts from
    if origin == destination:
        return "SAME_ORIGIN_DESTINATION"

    # 7. and 8. Date and time format
    if not is_valid_datetime(departure):
        return "INVALID_DEPARTURE"
    if not is_valid_datetime(arrival):
        return "INVALID_ARRIVAL"

    # 9. Arrival must be strictly after departure
    departure_time = datetime.strptime(departure, DATETIME_FORMAT)
    arrival_time = datetime.strptime(arrival, DATETIME_FORMAT)
    if arrival_time <= departure_time:
        return "ARRIVAL_NOT_AFTER_DEPARTURE"

    # 10. Price must be a finite number (float() accepts "nan" and "inf")
    try:
        price = float(price_text)
    except ValueError:
        return "INVALID_PRICE"
    if not math.isfinite(price):
        return "INVALID_PRICE"

    # 11. Price must be greater than zero
    if price <= 0:
        return "NON_POSITIVE_PRICE"

    return None


def to_record(fields: list[str]) -> dict:
    """Turn a valid row into a flight record dictionary.

    Keys: flight_id, origin, destination, departure_datetime,
    arrival_datetime (stripped strings) and price (float).
    """
    values = [field.strip() for field in fields]
    return {
        "flight_id": values[0],
        "origin": values[1],
        "destination": values[2],
        "departure_datetime": values[3],
        "arrival_datetime": values[4],
        "price": float(values[5]),
    }
