# Extra test data for the flight lab

Harder test data in the same style as the public tests, aimed at the edge cases
the hidden test set is likely to check. These are not the official tests.

## Install and run

Copy this `extra` folder into your project's `tests/` folder, so you have
`tests/extra/run_extra_tests.py`, then run from the project root:

```
python tests/extra/run_extra_tests.py
```

You can also use the data by hand, for example:

```
python flight_parser.py -i tests/extra/data/edge.csv -a tests/extra/data/airports.txt -o out/db.json
python flight_parser.py -d tests/extra/data/folder -a tests/extra/data/airports.txt -o out/db.json
python flight_parser.py -j tests/extra/data/query_db.json -q tests/extra/data/queries.json -r out/
```

Then compare with `expected/edge_errors.txt`, `expected/folder_errors.txt`, and so on.

## What is in it

| Path | What it tests |
| --- | --- |
| `data/airports.txt` | Tabs and spaces around codes, blank lines and comments. It also lists `abc`, `XY`, `ABCD` and `ÅRN`, which must still fail as origins or destinations because they are not 3 uppercase ASCII letters. |
| `data/edge.csv` | 101 data rows (plus comment and blank lines) covering every error code several times, plus check-order traps. It also has full-width digits (`２０２６`), a non-breaking space inside a date, `1e400`, `-nan`, `-0`, `1_000`, quoted commas, leap days, indented comments, and no newline at the end of the file. |
| `data/clean.csv` | No invalid rows: `errors.log` must still be created. |
| `data/folder/` | Sort order (`10_late` < `2_early` < `A_upper` < `a_lower`), mixed `\n`/`\r\n` endings and a header-only file. It also has duplicates across files, including one where the earlier copy was invalid. These must be ignored: a sub-folder named `sub.csv`, `UPPER.CSV`, `backup.csv.bak`, `notes.csv.txt` and `readme.txt`. |
| `data/no_csv_folder/` | Contains no `.csv` files (only a folder named `sub.csv`), so it must exit with code 1. |
| `data/query_db.json` + `queries.json` | 57 queries: boundaries, ties in sort order (asc and desc), limit, mixed-case IDs and 27 invalid queries (`true` as a number, `null`, a wrong-case `sort_by`, `"DESC"`, and more). |
| `data/json_inputs/` | Bad `-j`/`-q` files (null, number, string, truncated JSON, empty file) and an empty database. |
| `expected/` | Expected database, graded log lines, per-row `validate_row` results and query results. |

The runner also checks that:
- exit codes 1 and 2 are correct for 25 bad command lines
- `main()` returns 2 instead of raising `SystemExit`
- the logging handler is removed when `main()` fails part-way through
- three `main()` runs in one process write clean logs
- `logging.basicConfig()` is not used
- `parse_files` keeps no state between calls
- queries don't sort the database in place
- a 60,000-row file is processed in well under the 10-second limit

## Group Z

Group Z tests cases the assignment does not spell out word for word: case-sensitive duplicate IDs, a query date
that doesn't exist (`2026-02-30`), a query array containing a non-object, and
`.CSV` in upper case. Each test expects the most literal reading of the spec. If one
fails, reread the spec before changing your code.

## AI disclosure

This test data was generated with Claude (Anthropic). If you use it, mention it in
`AI_USAGE.md`, for example under "generating test data".
