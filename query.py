"""Running queries against the flight database."""
from validator import is_valid_datetime

# The six keys of a flight record (also the allowed sort_by values)
RECORD_KEYS = ["flight_id", "origin", "destination",
               "departure_datetime", "arrival_datetime", "price"]

ALLOWED_KEYS = set(RECORD_KEYS) | {"min_price", "sort_by", "order", "limit"}


def is_number(value) -> bool:
    """Return True for int or float values. bool is not a number here."""
    # bool is a subclass of int in Python, so it is excluded on purpose
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def is_valid_query(query) -> bool:
    """Check that a query only uses allowed keys with values of the right type."""
    if not isinstance(query, dict):
        return False

    for key, value in query.items():
        if key not in ALLOWED_KEYS:
            return False

        if key in ("flight_id", "origin", "destination"):
            if not isinstance(value, str):
                return False
        elif key in ("departure_datetime", "arrival_datetime"):
            if not isinstance(value, str) or not is_valid_datetime(value):
                return False
        elif key in ("price", "min_price"):
            if not is_number(value):
                return False
        elif key == "sort_by":
            if value not in RECORD_KEYS:
                return False
        elif key == "order":
            if value not in ("asc", "desc"):
                return False
        elif key == "limit":
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                return False

    # "order" only makes sense together with "sort_by"
    if "order" in query and "sort_by" not in query:
        return False

    return True


def flight_matches(flight: dict, query: dict) -> bool:
    """Return True if the flight passes every condition in the query (AND)."""
    for key in ("flight_id", "origin", "destination"):
        if key in query and flight[key] != query[key]:
            return False

    # Datetimes are always "YYYY-MM-DD HH:MM" (zero-padded), so comparing
    # them as strings gives the same result as comparing real datetimes.
    if "departure_datetime" in query and flight["departure_datetime"] < query["departure_datetime"]:
        return False
    if "arrival_datetime" in query and flight["arrival_datetime"] > query["arrival_datetime"]:
        return False

    if "price" in query and flight["price"] > query["price"]:
        return False
    if "min_price" in query and flight["price"] < query["min_price"]:
        return False

    return True


def run_query(db: list[dict], query: dict) -> dict:
    """Return one response entry for one query object.

    Valid query:   {"query": query, "matches": [...]}
    Invalid query: {"query": query, "error": "INVALID_QUERY", "matches": []}
    """
    if not is_valid_query(query):
        return {"query": query, "error": "INVALID_QUERY", "matches": []}

    # Filtering keeps the database order
    matches = [flight for flight in db if flight_matches(flight, query)]

    if "sort_by" in query:
        descending = query.get("order", "asc") == "desc"
        # sorted() is stable, also with reverse=True, so equal values
        # stay in database order
        matches = sorted(matches, key=lambda flight: flight[query["sort_by"]],
                         reverse=descending)

    # limit is applied after sorting
    if "limit" in query:
        matches = matches[:query["limit"]]

    return {"query": query, "matches": matches}


def run_queries(db: list[dict], queries: dict | list) -> list[dict]:
    """Accept one query object or a list of them; always return a list."""
    if isinstance(queries, dict):
        queries = [queries]
    return [run_query(db, query) for query in queries]
