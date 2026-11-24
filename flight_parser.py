"""Flight Schedule Parser and Query Tool - command-line entry point.

Run from the project folder, for example:
    python flight_parser.py -i data/db.csv -a data/airports.txt
"""
import argparse
import json
import logging
import os
import sys
from datetime import datetime

from csv_loader import parse_files
from query import run_queries
from validator import load_airports

# TODO: fill in your details: plain ASCII, no spaces or underscores.
STUDENT_ID = "260AEM008"
FIRST_NAME = "Emre"
LAST_NAME = "Kiyak"

LOGGER_NAME = "flight_parser"


class RuntimeProblem(Exception):
    """An expected runtime problem (missing file, bad JSON...). Exit code 1."""


def build_parser() -> argparse.ArgumentParser:
    """Create the command-line argument parser."""
    parser = argparse.ArgumentParser(
        prog="flight_parser.py",
        description="Validate flight schedule CSV files and query the result.",
        allow_abbrev=False,
    )
    parser.add_argument("-i", dest="input_file", help="one CSV file to parse")
    parser.add_argument("-d", dest="input_dir", help="folder with CSV files to parse")
    parser.add_argument("-j", dest="json_db", help="existing JSON database to load")
    parser.add_argument("-a", dest="airports", help="airport list file (needed with -i / -d)")
    parser.add_argument("-o", dest="output", help="output database path (default: db.json)")
    parser.add_argument("-q", dest="query_file", help="JSON file with queries")
    parser.add_argument("-r", dest="response_dir", default=".",
                        help="folder for the response file (default: current folder)")
    return parser


def parse_arguments(argv: list[str] | None) -> argparse.Namespace:
    """Parse and check the arguments. Usage errors raise SystemExit(2)."""
    parser = build_parser()
    args = parser.parse_args(argv)

    # Exactly one data source must be given
    sources = [args.input_file, args.input_dir, args.json_db]
    source_count = len([s for s in sources if s is not None])
    if source_count == 0:
        parser.error("one data source is required: -i, -d or -j")
    if source_count > 1:
        parser.error("only one data source is allowed: -i, -d or -j")

    # Rules that argparse cannot express by itself
    if (args.input_file is not None or args.input_dir is not None) and args.airports is None:
        parser.error("-a is required with -i and -d")
    if args.json_db is not None and args.output is not None:
        parser.error("-o cannot be used with -j")

    if args.output is None:
        args.output = "db.json"
    return args


def find_csv_files(folder: str) -> list[str]:
    """Return the .csv files directly inside folder, sorted by name."""
    if not os.path.isdir(folder):
        raise RuntimeProblem(f"folder not found: {folder}")
    try:
        names = sorted(os.listdir(folder))
    except OSError as e:
        raise RuntimeProblem(f"cannot read folder {folder}: {e}")

    # Sub-folders and other file types are ignored
    paths = []
    for name in names:
        path = os.path.join(folder, name)
        if name.endswith(".csv") and os.path.isfile(path):
            paths.append(path)

    if not paths:
        raise RuntimeProblem(f"no .csv files found in {folder}")
    return paths


def read_json_file(path: str, what: str):
    """Read a JSON file and return the parsed data."""
    if not os.path.isfile(path):
        raise RuntimeProblem(f"{what} not found: {path}")
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except OSError as e:
        raise RuntimeProblem(f"cannot read {what} {path}: {e}")
    except ValueError as e:
        # json.JSONDecodeError and UnicodeDecodeError are both ValueErrors
        raise RuntimeProblem(f"{what} is not valid JSON: {path} ({e})")


def load_database(path: str) -> list[dict]:
    """Load a JSON database. It must be an array of objects."""
    data = read_json_file(path, "JSON database")
    if not isinstance(data, list) or not all(isinstance(item, dict) for item in data):
        raise RuntimeProblem(f"JSON database must be an array of objects: {path}")
    return data


def load_queries(path: str) -> dict | list:
    """Load a query file: one query object or an array of query objects."""
    data = read_json_file(path, "query file")
    if isinstance(data, dict):
        return data
    if isinstance(data, list) and all(isinstance(item, dict) for item in data):
        return data
    raise RuntimeProblem(f"query file must hold an object or an array of objects: {path}")


def write_json_file(path: str, data) -> None:
    """Write data as a JSON file."""
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.write("\n")
    except OSError as e:
        raise RuntimeProblem(f"cannot write {path}: {e}")


def setup_logger(log_path: str) -> logging.FileHandler:
    """Attach a file handler for errors.log and return it (so it can be removed)."""
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.INFO)
    try:
        handler = logging.FileHandler(log_path, mode="w", encoding="utf-8")
    except OSError as e:
        raise RuntimeProblem(f"cannot create {log_path}: {e}")
    handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)s %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
    logger.addHandler(handler)
    return handler


def parse_csv_input(args: argparse.Namespace) -> list[dict]:
    """Handle -i / -d: parse the CSV files, write errors.log and the database."""
    logger = logging.getLogger(LOGGER_NAME)

    # Find the input files first, so a missing input is reported early
    if args.input_file is not None:
        if not os.path.isfile(args.input_file):
            raise RuntimeProblem(f"file not found: {args.input_file}")
        paths = [args.input_file]
    else:
        paths = find_csv_files(args.input_dir)

    if not os.path.isfile(args.airports):
        raise RuntimeProblem(f"airport file not found: {args.airports}")
    try:
        airports = load_airports(args.airports)
    except (OSError, UnicodeDecodeError) as e:
        raise RuntimeProblem(f"cannot read airport file {args.airports}: {e}")

    try:
        records, errors = parse_files(paths, airports)
    except (OSError, UnicodeDecodeError) as e:
        raise RuntimeProblem(f"cannot read CSV file: {e}")

    # One WARNING line per invalid row, in input order
    for message in errors:
        logger.warning(message)
    logger.info("%d valid rows, %d invalid rows in %d file(s)",
                len(records), len(errors), len(paths))

    write_json_file(args.output, records)
    print(f"Wrote {len(records)} valid flights to {args.output} ({len(errors)} invalid rows)")
    return records


def answer_queries(db: list[dict], args: argparse.Namespace) -> None:
    """Handle -q: run the queries and write one response file to the -r folder."""
    queries = load_queries(args.query_file)
    responses = run_queries(db, queries)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    file_name = f"response_{STUDENT_ID}_{FIRST_NAME}_{LAST_NAME}_{timestamp}.json"
    path = os.path.join(args.response_dir, file_name)
    write_json_file(path, responses)
    print(f"Wrote {len(responses)} query result(s) to {path}")


def main(argv: list[str] | None = None) -> int:
    """Run the whole program and return the exit code (0, 1 or 2).

    argv is the argument list without the program name.
    None means use sys.argv[1:] (argparse does this for you).
    Do not call sys.exit() inside main(); return the code instead.
    """
    # argparse calls sys.exit() on usage errors (code 2) and on --help (code 0),
    # so the SystemExit is caught here and turned into a return value
    try:
        args = parse_arguments(argv)
    except SystemExit as e:
        return e.code if isinstance(e.code, int) else 2

    logger = logging.getLogger(LOGGER_NAME)
    handler = None
    try:
        if args.json_db is not None:
            # -j: no database and no errors.log are written
            db = load_database(args.json_db)
        else:
            # errors.log goes into the same folder as the database file
            output_folder = os.path.dirname(os.path.abspath(args.output))
            handler = setup_logger(os.path.join(output_folder, "errors.log"))
            db = parse_csv_input(args)

        if args.query_file is not None:
            answer_queries(db, args)
        return 0

    except RuntimeProblem as e:
        if handler is not None:
            logger.error(str(e))
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        # Safety net: never show a traceback to the user
        print(f"Error: unexpected problem: {e}", file=sys.stderr)
        return 1
    finally:
        # Always remove and close the handler, otherwise a second call
        # of main() in the same process would write into the old log file
        if handler is not None:
            logger.removeHandler(handler)
            handler.close()


if __name__ == "__main__":
    sys.exit(main())
