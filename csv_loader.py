"""Reading CSV files into flight records and error messages."""
import csv
import os

from validator import to_record, validate_row


def split_line(line: str) -> list[str]:
    """Split one CSV line into fields with the csv module."""
    try:
        return next(csv.reader([line]))
    except csv.Error:
        # A line the csv module cannot read is kept as one single field,
        # so it is reported as WRONG_FIELD_COUNT instead of crashing.
        return [line]


def parse_files(paths: list[str], airports: set[str]) -> tuple[list[dict], list[str]]:
    """Process the CSV files in the order given.

    Return (records, errors):
      records - valid flight records, in input order
      errors  - one message per invalid row, in input order, formatted as
                "<file name>:<line number>: <ERROR_CODE> | <free text>"
                (base file name only, no timestamp or level, no newline)

    Also performs the DUPLICATE_FLIGHT check across all the files.
    Does not write any files and does not log anything itself.
    """
    records = []
    errors = []
    # (flight_id, departure_datetime) pairs of valid rows seen so far,
    # shared by all files so duplicates are found across files too
    seen = set()

    for path in paths:
        file_name = os.path.basename(path)
        with open(path, encoding="utf-8") as f:
            # Python's text mode turns both \n and \r\n into \n
            for line_number, raw_line in enumerate(f, start=1):
                line = raw_line.rstrip("\r\n")

                # Line 1 is the header: skip it without checking
                if line_number == 1:
                    continue
                # Blank lines and comment lines are skipped and not logged
                stripped = line.strip()
                if stripped == "" or stripped.startswith("#"):
                    continue

                fields = split_line(line)
                error_code = validate_row(fields, airports)

                # Duplicate check only runs when checks 1-11 passed
                if error_code is None:
                    record = to_record(fields)
                    key = (record["flight_id"], record["departure_datetime"])
                    if key in seen:
                        error_code = "DUPLICATE_FLIGHT"
                    else:
                        seen.add(key)
                        records.append(record)

                if error_code is not None:
                    # The original line is used as the free text
                    errors.append(f"{file_name}:{line_number}: {error_code} | {line}")

    return records, errors
