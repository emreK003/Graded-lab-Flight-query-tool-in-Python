"""Extra edge-case tests for the Flight Schedule Parser and Query Tool.

These are NOT the official tests. They add harder data in the style of the
public tests, to catch problems the hidden test set is likely to probe.

Put this folder at tests/extra/ in your project and run from the project root:

    python tests/extra/run_extra_tests.py

Group Z holds cases where the assignment text can be read more than one way.
A failure there is worth a second look at the spec, not proof of a bug.
"""
import contextlib
import importlib
import io
import json
import logging
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
DATA = HERE / "data"
EXPECTED = HERE / "expected"
AIRPORTS = DATA / "airports.txt"
EDGE = DATA / "edge.csv"
FOLDER = DATA / "folder"
QDB = DATA / "query_db.json"
ODD = DATA / "json_inputs"
TIMEOUT = 10
HEADER = "flight_id,origin,destination,departure_datetime,arrival_datetime,price\n"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

WARNING_RE = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} WARNING (\S+:\d+: [A-Z_]+)(?: \|.*)?$")
FOLDER_FILES = ["10_late.csv", "2_early.csv", "3_header_only.csv", "A_upper.csv", "a_lower.csv"]


def mod(name):
    return importlib.import_module(name)


def run_cli(args, cwd):
    return subprocess.run(
        [sys.executable, str(ROOT / "flight_parser.py"), *[str(a) for a in args]],
        cwd=str(cwd), capture_output=True, text=True, timeout=TIMEOUT)


def read_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def exp_lines(name):
    return (EXPECTED / name).read_text(encoding="utf-8").splitlines()


def graded_log(path):
    out = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        m = WARNING_RE.match(line)
        if m:
            out.append(m.group(1))
    return out


def graded_message(message):
    return message.split(" | ", 1)[0].rstrip(" |")


def ids(entries):
    return [r["flight_id"] for r in entries]


def airports():
    return set(read_json(EXPECTED / "airports_expected.json"))


class TempDirTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="flightlab_extra_"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def assertCleanExit(self, proc, code):
        self.assertNotIn("Traceback", proc.stderr, "traceback on stderr:\n" + proc.stderr)
        self.assertEqual(proc.returncode, code,
                         f"expected exit code {code}, got {proc.returncode}\nstderr:\n{proc.stderr}")

    def assertErrorLine(self, proc):
        self.assertTrue(any(l.startswith("Error:") for l in proc.stderr.splitlines()),
                        "print a line starting with 'Error:' to stderr")

    def call_main(self, argv):
        """Call main() in this process, hiding its output."""
        main = mod("flight_parser").main
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main([str(a) for a in argv])
        return code, err.getvalue()


# ================================================================ B. Row validation

class B_RowValidation(unittest.TestCase):
    def test_load_airports(self):
        self.assertEqual(mod("validator").load_airports(str(AIRPORTS)), airports(),
                         "codes are stripped (also tabs); blank and # lines are skipped; "
                         "codes are kept exactly as written")

    def test_every_edge_row(self):
        """Each row of edge.csv, passed straight to validate_row."""
        validate_row = mod("validator").validate_row
        ap = airports()
        for case in read_json(EXPECTED / "edge_rows.json"):
            with self.subTest(line=case["line"], fields=case["fields"]):
                self.assertEqual(validate_row(list(case["fields"]), ap), case["expect"])

    def test_validate_row_does_not_modify_input(self):
        validate_row = mod("validator").validate_row
        fields = [" EV1 ", "RIX", "HEL", "2026-01-10 08:00", "2026-01-10 09:00", " 5 "]
        before = list(fields)
        validate_row(fields, airports())
        self.assertEqual(fields, before, "validate_row should not change the list it is given")

    def test_to_record_edge_prices(self):
        to_record = mod("validator").to_record
        cases = {"1e2": 100.0, "+50": 50.0, ".5": 0.5, "5.": 5.0, "1_000": 1000.0, " 120 ": 120.0}
        for raw, value in cases.items():
            with self.subTest(price=raw):
                rec = to_record(["\tEV1 ", " RIX", "HEL ", " 2026-01-10 08:00", "2026-01-10 09:00 ", raw])
                self.assertEqual(rec, {"flight_id": "EV1", "origin": "RIX", "destination": "HEL",
                                       "departure_datetime": "2026-01-10 08:00",
                                       "arrival_datetime": "2026-01-10 09:00", "price": value})
                self.assertIsInstance(rec["price"], float)
                self.assertEqual(len(rec), 6)


# ================================================================ C. Parsing a file

class C_ParsingAFile(TempDirTest):
    def parse_edge(self, path=EDGE):
        proc = run_cli(["-i", path, "-a", AIRPORTS, "-o", self.tmp / "db.json"], self.tmp)
        self.assertCleanExit(proc, 0)

    def test_edge_database(self):
        self.parse_edge()
        self.assertEqual(read_json(self.tmp / "db.json"), read_json(EXPECTED / "edge_db.json"))

    def test_edge_errors_log(self):
        self.parse_edge()
        self.assertEqual(graded_log(self.tmp / "errors.log"), exp_lines("edge_errors.txt"))

    def test_edge_crlf(self):
        crlf = self.tmp / "edge.csv"
        crlf.write_bytes(EDGE.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
        self.parse_edge(crlf)
        self.assertEqual(read_json(self.tmp / "db.json"), read_json(EXPECTED / "edge_db.json"))
        self.assertEqual(graded_log(self.tmp / "errors.log"), exp_lines("edge_errors.txt"))

    def test_edge_parse_files(self):
        records, errors = mod("csv_loader").parse_files([str(EDGE)], airports())
        self.assertEqual(records, read_json(EXPECTED / "edge_db.json"))
        self.assertEqual([graded_message(e) for e in errors], exp_lines("edge_errors.txt"))
        for e in errors:
            self.assertNotIn("\n", e, "error messages must be single lines")
            self.assertRegex(e, r"^edge\.csv:\d+: [A-Z_]+ \| ", "format: '<file>:<line>: <CODE> | <text>'")

    def test_parse_files_does_not_log(self):
        logger = logging.getLogger("flight_parser")
        before = list(logger.handlers)
        mod("csv_loader").parse_files([str(EDGE)], airports())
        self.assertEqual(logger.handlers, before, "parse_files must not add logging handlers")

    def test_errors_log_created_without_errors(self):
        proc = run_cli(["-i", DATA / "clean.csv", "-a", AIRPORTS, "-o", self.tmp / "db.json"], self.tmp)
        self.assertCleanExit(proc, 0)
        self.assertTrue((self.tmp / "errors.log").is_file(), "errors.log must exist even with no errors")
        self.assertEqual(graded_log(self.tmp / "errors.log"), [])
        self.assertEqual(read_json(self.tmp / "db.json"), read_json(EXPECTED / "clean_db.json"))

    def test_only_header_gives_empty_array(self):
        proc = run_cli(["-i", FOLDER / "3_header_only.csv", "-a", AIRPORTS, "-o", self.tmp / "db.json"], self.tmp)
        self.assertCleanExit(proc, 0)
        self.assertEqual(read_json(self.tmp / "db.json"), [])

    def test_log_goes_next_to_output_not_cwd(self):
        out = self.tmp / "out"
        out.mkdir()
        cwd = self.tmp / "cwd"
        cwd.mkdir()
        proc = run_cli(["-i", EDGE, "-a", AIRPORTS, "-o", out / "flights.json"], cwd)
        self.assertCleanExit(proc, 0)
        self.assertTrue((out / "flights.json").is_file())
        self.assertTrue((out / "errors.log").is_file(), "errors.log goes in the same folder as the -o file")
        self.assertEqual(sorted(p.name for p in cwd.iterdir()), [], "nothing should be written to the cwd")

    def test_relative_output_path(self):
        (self.tmp / "sub").mkdir()
        proc = run_cli(["-i", EDGE, "-a", AIRPORTS, "-o", "sub/x.json"], self.tmp)
        self.assertCleanExit(proc, 0)
        self.assertTrue((self.tmp / "sub" / "x.json").is_file())
        self.assertTrue((self.tmp / "sub" / "errors.log").is_file())

    def test_handler_removed_after_early_error(self):
        """main() fails after it has set up logging (bad -q file): the handler must still go."""
        bad = self.tmp / "bad.json"
        bad.write_text("{oops", encoding="utf-8")
        logger = logging.getLogger("flight_parser")
        code, err = self.call_main(["-i", EDGE, "-a", AIRPORTS, "-o", self.tmp / "db.json",
                                    "-q", bad, "-r", self.tmp])
        self.assertEqual(code, 1)
        self.assertIn("Error:", err)
        self.assertEqual(logger.handlers, [], "handler left behind after main() returned 1")

    def test_three_runs_in_one_process(self):
        logger = logging.getLogger("flight_parser")
        logs = []
        for n in range(3):
            out = self.tmp / f"run{n}"
            out.mkdir()
            code, _ = self.call_main(["-i", EDGE, "-a", AIRPORTS, "-o", out / "db.json"])
            self.assertEqual(code, 0)
            self.assertEqual(logger.handlers, [])
            logs.append(out / "errors.log")
        for path in logs:
            with self.subTest(log=path.parent.name):
                self.assertEqual(graded_log(path), exp_lines("edge_errors.txt"),
                                 "a log has extra or missing lines: handler not removed between runs?")

    def test_no_basicconfig_side_effects(self):
        self.call_main(["-i", EDGE, "-a", AIRPORTS, "-o", self.tmp / "db.json"])
        self.assertEqual(logging.getLogger().handlers, [],
                         "the root logger got a handler: do not use logging.basicConfig()")


# ================================================================ D. CLI and folders

class D_CliAndFolders(TempDirTest):
    def test_folder_mode(self):
        proc = run_cli(["-d", FOLDER, "-a", AIRPORTS, "-o", self.tmp / "db.json"], self.tmp)
        self.assertCleanExit(proc, 0)
        db = read_json(self.tmp / "db.json")
        self.assertNotIn("TRAP1", ids(db), "parsed a file that is not a .csv file (or a sub-folder)")
        self.assertEqual(db, read_json(EXPECTED / "folder_db.json"))
        self.assertEqual(graded_log(self.tmp / "errors.log"), exp_lines("folder_errors.txt"),
                         "files must be read in sorted() order: 10_late, 2_early, 3_header_only, A_upper, a_lower")

    def test_folder_path_with_trailing_slash(self):
        proc = run_cli(["-d", str(FOLDER) + "/", "-a", AIRPORTS, "-o", self.tmp / "db.json"], self.tmp)
        self.assertCleanExit(proc, 0)
        self.assertEqual(read_json(self.tmp / "db.json"), read_json(EXPECTED / "folder_db.json"))

    def test_folder_parse_files_order(self):
        paths = [str(FOLDER / n) for n in FOLDER_FILES]
        records, errors = mod("csv_loader").parse_files(paths, airports())
        self.assertEqual(records, read_json(EXPECTED / "folder_db.json"))
        self.assertEqual([graded_message(e) for e in errors], exp_lines("folder_errors.txt"))

    def test_runtime_errors_exit_1(self):
        missing_airports = self.tmp / "nope.txt"
        cases = {
            "-a file does not exist": ["-i", EDGE, "-a", missing_airports],
            "-i is a folder": ["-i", FOLDER, "-a", AIRPORTS],
            "-d is a file": ["-d", EDGE, "-a", AIRPORTS],
            "-d folder has only a sub-folder named sub.csv": ["-d", DATA / "no_csv_folder", "-a", AIRPORTS],
            "-j array of numbers": ["-j", ODD / "db_array_of_numbers.json"],
            "-j null": ["-j", ODD / "db_null.json"],
            "-j number": ["-j", ODD / "db_number.json"],
            "-j string": ["-j", ODD / "db_string.json"],
            "-j truncated JSON": ["-j", ODD / "db_truncated.json"],
            "-j empty file": ["-j", ODD / "db_empty_file.json"],
            "-q number": ["-j", QDB, "-q", ODD / "q_number.json", "-r", self.tmp],
            "-q string": ["-j", QDB, "-q", ODD / "q_string.json", "-r", self.tmp],
            "-q null": ["-j", QDB, "-q", ODD / "q_null.json", "-r", self.tmp],
            "-q empty file": ["-j", QDB, "-q", ODD / "q_empty_file.json", "-r", self.tmp],
            "-q file does not exist": ["-j", QDB, "-q", self.tmp / "nope.json", "-r", self.tmp],
            "-q bad after -i parse": ["-i", EDGE, "-a", AIRPORTS, "-o", self.tmp / "db.json",
                                      "-q", ODD / "q_number.json", "-r", self.tmp],
        }
        for name, args in cases.items():
            with self.subTest(case=name):
                proc = run_cli(args, self.tmp)
                self.assertCleanExit(proc, 1)
                self.assertErrorLine(proc)
        self.assertEqual(list(self.tmp.glob("response_*.json")), [],
                         "no response file should be written when the query file is bad")

    def test_usage_errors_exit_2(self):
        cases = {
            "-i and -d": ["-i", EDGE, "-d", FOLDER, "-a", AIRPORTS],
            "-d and -j": ["-d", FOLDER, "-j", QDB, "-a", AIRPORTS],
            "all three sources": ["-i", EDGE, "-d", FOLDER, "-j", QDB, "-a", AIRPORTS],
            "-q without a source": ["-q", DATA / "queries.json"],
            "only -a": ["-a", AIRPORTS],
            "-o with -j and -q": ["-j", QDB, "-q", DATA / "queries.json", "-o", self.tmp / "x.json"],
            "-d without -a": ["-d", FOLDER, "-o", self.tmp / "x.json"],
            "stray positional argument": ["-i", EDGE, "-a", AIRPORTS, "extra"],
            "-i with no value": ["-a", AIRPORTS, "-i"],
        }
        for name, args in cases.items():
            with self.subTest(case=name):
                self.assertCleanExit(run_cli(args, self.tmp), 2)
        self.assertEqual([p.name for p in self.tmp.iterdir()], [],
                         "a usage error must not write any files")

    def test_main_returns_2_instead_of_exiting(self):
        """argparse raises SystemExit; main() must turn it into a return value."""
        try:
            code, _ = self.call_main([])
        except SystemExit as e:
            self.fail(f"main([]) raised SystemExit({e.code}) instead of returning 2")
        self.assertEqual(code, 2)

    def test_help_exits_0(self):
        proc = run_cli(["-h"], self.tmp)
        self.assertCleanExit(proc, 0)
        self.assertIn("-i", proc.stdout)

    def test_a_is_ignored_with_j(self):
        proc = run_cli(["-j", QDB, "-a", self.tmp / "does_not_exist.txt"], self.tmp)
        self.assertCleanExit(proc, 0)

    def test_j_writes_no_database_or_log(self):
        proc = run_cli(["-j", QDB, "-q", DATA / "queries.json"], self.tmp)
        self.assertCleanExit(proc, 0)
        names = [p.name for p in self.tmp.iterdir()]
        self.assertNotIn("db.json", names)
        self.assertNotIn("errors.log", names)
        self.assertEqual(len(names), 1, f"only the response file should be written, found {names}")


# ================================================================ E. Duplicates

class E_Duplicates(TempDirTest):
    def test_duplicate_of_earlier_invalid_row_across_files(self):
        """10_late has F10B with price 0 (invalid). 2_early's F10B is therefore valid,
        and a_lower's F10B is a duplicate of the 2_early one."""
        paths = [str(FOLDER / n) for n in FOLDER_FILES]
        _, errors = mod("csv_loader").parse_files(paths, airports())
        got = [graded_message(e) for e in errors]
        self.assertIn("A_upper.csv:2: DUPLICATE_FLIGHT", got)
        self.assertIn("a_lower.csv:3: DUPLICATE_FLIGHT", got)
        self.assertIn("a_lower.csv:4: DUPLICATE_FLIGHT", got)
        self.assertNotIn("2_early.csv:2: DUPLICATE_FLIGHT", got)

    def test_state_is_not_shared_between_calls(self):
        """Calling parse_files twice must not treat the second call's rows as duplicates."""
        parse_files = mod("csv_loader").parse_files
        first = parse_files([str(EDGE)], airports())
        second = parse_files([str(EDGE)], airports())
        self.assertEqual(first, second, "parse_files keeps state between calls (global 'seen' set?)")

    def test_same_file_twice(self):
        parse_files = mod("csv_loader").parse_files
        path = self.tmp / "one.csv"
        path.write_text(HEADER + "AB1,RIX,HEL,2026-01-01 08:00,2026-01-01 09:00,10\n", encoding="utf-8")
        records, errors = parse_files([str(path), str(path)], airports())
        self.assertEqual(len(records), 1)
        self.assertEqual([graded_message(e) for e in errors], ["one.csv:2: DUPLICATE_FLIGHT"])


# ================================================================ F/G. Queries

class G_Queries(TempDirTest):
    def setUp(self):
        super().setUp()
        self.db = read_json(QDB)
        self.cases = read_json(EXPECTED / "queries_expected.json")

    def check(self, entry, case):
        q, exp = case["query"], case["expect"]
        self.assertEqual(entry["query"], q, "'query' must be the query exactly as given")
        if exp == "INVALID_QUERY":
            self.assertEqual(entry, {"query": q, "error": "INVALID_QUERY", "matches": []})
        else:
            self.assertNotIn("error", entry)
            self.assertEqual(ids(entry["matches"]), exp)
            by_id = {r["flight_id"]: r for r in self.db}
            self.assertEqual(entry["matches"], [by_id[i] for i in exp], "matches must be full records")

    def test_run_queries_function(self):
        results = mod("query").run_queries(self.db, [c["query"] for c in self.cases])
        self.assertEqual(len(results), len(self.cases))
        for case, entry in zip(self.cases, results):
            with self.subTest(query=case["query"]):
                self.check(entry, case)

    def test_run_query_one_by_one(self):
        run_query = mod("query").run_query
        for case in self.cases:
            with self.subTest(query=case["query"]):
                self.check(run_query(self.db, case["query"]), case)

    def test_queries_do_not_modify_db(self):
        before = json.loads(json.dumps(self.db))
        mod("query").run_queries(self.db, [c["query"] for c in self.cases])
        self.assertEqual(self.db, before, "a query changed the database (sorted in place?)")

    def test_run_queries_single_object(self):
        res = mod("query").run_queries(self.db, {"origin": "TLL"})
        self.assertIsInstance(res, list)
        self.assertEqual(len(res), 1)
        self.assertEqual(ids(res[0]["matches"]), ["Q4"])

    def test_cli_queries(self):
        (self.tmp / "out").mkdir()
        proc = run_cli(["-j", QDB, "-q", DATA / "queries.json", "-r", self.tmp / "out"], self.tmp)
        self.assertCleanExit(proc, 0)
        files = list((self.tmp / "out").glob("response_*.json"))
        self.assertEqual(len(files), 1)
        result = read_json(files[0])
        self.assertEqual(len(result), len(self.cases))
        for case, entry in zip(self.cases, result):
            with self.subTest(query=case["query"]):
                self.check(entry, case)

    def test_cli_parse_then_query(self):
        """Queries run on the freshly parsed edge.csv database."""
        q = self.tmp / "q.json"
        q.write_text(json.dumps([{"origin": "RIX", "sort_by": "price", "order": "desc"}]), encoding="utf-8")
        proc = run_cli(["-i", EDGE, "-a", AIRPORTS, "-o", self.tmp / "db.json", "-q", q, "-r", self.tmp], self.tmp)
        self.assertCleanExit(proc, 0)
        res = read_json(next(self.tmp.glob("response_*.json")))
        self.assertEqual(ids(res[0]["matches"]), ["EV100", "EV100", "EV106", "A1", "EV320", "EV101", "EV105"])

    def test_empty_db_and_empty_query_list(self):
        cases = [
            (["-j", ODD / "db_empty.json", "-q", ODD / "q_single.json"], [{"query": {"origin": "RIX", "sort_by": "price"}, "matches": []}]),
            (["-j", QDB, "-q", ODD / "q_empty_array.json"], []),
        ]
        for args, expected in cases:
            with self.subTest(args=[str(a) for a in args]):
                out = Path(tempfile.mkdtemp(dir=self.tmp))
                proc = run_cli([*args, "-r", out], self.tmp)
                self.assertCleanExit(proc, 0)
                files = list(out.glob("response_*.json"))
                self.assertEqual(len(files), 1, "write the response file even when it is empty")
                self.assertEqual(read_json(files[0]), expected)


# ================================================================ H. Response file

class H_ResponseFile(TempDirTest):
    def test_name_and_timestamp(self):
        fp = mod("flight_parser")
        before = datetime.now().replace(second=0, microsecond=0)
        proc = run_cli(["-j", QDB, "-q", ODD / "q_single.json", "-r", self.tmp], self.tmp)
        after = datetime.now()
        self.assertCleanExit(proc, 0)
        files = [p.name for p in self.tmp.iterdir()]
        self.assertEqual(len(files), 1, files)
        m = re.fullmatch(rf"response_{re.escape(fp.STUDENT_ID)}_{re.escape(fp.FIRST_NAME)}_"
                         rf"{re.escape(fp.LAST_NAME)}_(\d{{8}}_\d{{4}})\.json", files[0])
        self.assertIsNotNone(m, f"bad response file name: {files[0]}")
        stamp = datetime.strptime(m.group(1), "%Y%m%d_%H%M")
        self.assertTrue(before <= stamp <= after, "timestamp should be the current LOCAL time")

    def test_single_object_still_gives_array(self):
        proc = run_cli(["-j", QDB, "-q", ODD / "q_single.json", "-r", self.tmp], self.tmp)
        self.assertCleanExit(proc, 0)
        res = read_json(next(self.tmp.glob("response_*.json")))
        self.assertIsInstance(res, list)
        self.assertEqual(set(res[0]), {"query", "matches"})
        self.assertEqual(ids(res[0]["matches"]), ["q8", "Q2", "Q1", "Q5"])

    def test_one_file_with_parse_and_query(self):
        out = self.tmp / "o"
        resp = self.tmp / "r"
        out.mkdir()
        resp.mkdir()
        proc = run_cli(["-d", FOLDER, "-a", AIRPORTS, "-o", out / "db.json",
                        "-q", DATA / "queries.json", "-r", resp], self.tmp)
        self.assertCleanExit(proc, 0)
        self.assertEqual(len(list(resp.iterdir())), 1, "exactly one file in the -r folder")
        self.assertEqual(sorted(p.name for p in out.iterdir()), ["db.json", "errors.log"])


# ================================================================ P. Performance

class P_Performance(TempDirTest):
    N = 60_000
    DUPS = 500

    def test_large_file_under_time_limit(self):
        start = datetime(2026, 1, 1)
        lines = [HEADER.rstrip("\n")]
        for i in range(self.N):
            dep = start + timedelta(minutes=i)
            price = "0" if i % 100 == 0 else f"{10 + i % 400}.50"
            lines.append(f"P{i},RIX,HEL,{dep:%Y-%m-%d %H:%M},{dep + timedelta(minutes=90):%Y-%m-%d %H:%M},{price}")
        for i in range(1, 2 * self.DUPS, 2):
            dep = start + timedelta(minutes=i)
            lines.append(f"P{i},RIX,HEL,{dep:%Y-%m-%d %H:%M},{dep + timedelta(minutes=60):%Y-%m-%d %H:%M},5")
        big = self.tmp / "big.csv"
        big.write_text("\n".join(lines) + "\n", encoding="utf-8")
        q = self.tmp / "q.json"
        q.write_text(json.dumps([{"sort_by": "price", "order": "desc", "limit": 5}, {"min_price": 400}] * 20), encoding="utf-8")
        t0 = time.monotonic()
        proc = run_cli(["-i", big, "-a", AIRPORTS, "-o", self.tmp / "db.json", "-q", q, "-r", self.tmp], self.tmp)
        elapsed = time.monotonic() - t0
        self.assertCleanExit(proc, 0)
        self.assertEqual(len(read_json(self.tmp / "db.json")), self.N - self.N // 100)
        log = graded_log(self.tmp / "errors.log")
        self.assertEqual(len(log), self.N // 100 + self.DUPS)
        self.assertEqual(sum(1 for l in log if l.endswith("DUPLICATE_FLIGHT")), self.DUPS,
                         "duplicates must be found with a set/dict, not a list scan")
        self.assertLess(elapsed, 5, f"took {elapsed:.1f}s; the limit is 10s on the grader")


# ================================================================ Z. Interpretation

class Z_Interpretation(TempDirTest):
    """Cases the assignment text does not spell out word for word.
    The expected answer is the most literal reading; check the spec if one fails."""

    def test_duplicate_check_is_case_sensitive(self):
        p = self.tmp / "case.csv"
        p.write_text(HEADER + "AB100,RIX,HEL,2026-01-01 08:00,2026-01-01 09:00,10\n"
                              "ab100,RIX,HEL,2026-01-01 08:00,2026-01-01 09:00,10\n", encoding="utf-8")
        records, errors = mod("csv_loader").parse_files([str(p)], airports())
        self.assertEqual(ids(records), ["AB100", "ab100"])
        self.assertEqual(errors, [])

    def test_query_date_that_does_not_exist(self):
        res = mod("query").run_query(read_json(QDB), {"departure_datetime": "2026-02-30 10:00"})
        self.assertEqual(res.get("error"), "INVALID_QUERY")

    def test_query_array_with_non_object_exits_1(self):
        proc = run_cli(["-j", QDB, "-q", ODD / "q_array_with_non_object.json", "-r", self.tmp], self.tmp)
        self.assertCleanExit(proc, 1)

    def test_upper_case_extension_is_not_csv(self):
        """UPPER.CSV does not end in '.csv' (this test assumes a case-sensitive file system)."""
        proc = run_cli(["-d", FOLDER, "-a", AIRPORTS, "-o", self.tmp / "db.json"], self.tmp)
        self.assertCleanExit(proc, 0)
        self.assertNotIn("TRAP1", ids(read_json(self.tmp / "db.json")))


# ================================================================ runner

class TallyResult(unittest.TextTestResult):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.passed = []

    def addSuccess(self, test):
        super().addSuccess(test)
        self.passed.append(test)


def all_tests(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from all_tests(item)
        else:
            yield item


def main():
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    totals = {}
    for t in all_tests(suite):
        totals[type(t).__name__] = totals.get(type(t).__name__, 0) + 1
    result = unittest.TextTestRunner(verbosity=2, resultclass=TallyResult).run(suite)
    passed = {}
    for t in result.passed:
        passed[type(t).__name__] = passed.get(type(t).__name__, 0) + 1
    print("\nSummary (extra tests, not the official grade)")
    for group in sorted(totals):
        print(f"  {group:<24} {passed.get(group, 0)}/{totals[group]} passed")
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
