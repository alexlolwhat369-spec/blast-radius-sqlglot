from __future__ import annotations

import sys
import json
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from patch_model import FileChange, parse_patch
from scheduler import split
from semantic import changed_mapping_values, proven_equivalent
from selector import impacted_tests


INDEX = json.loads((Path(__file__).resolve().parents[1] / "semantic_index.json").read_text(encoding="utf-8"))


def edit(path: str, line: int, old: str, new: str) -> FileChange:
    return FileChange(path=path, old_lines={line}, removed=[old], added=[new])


class CoreTests(unittest.TestCase):
    def test_patch_line_numbers_and_content_that_looks_like_header(self):
        patch = """diff --git a/tests/fixtures/x.sql b/tests/fixtures/x.sql
--- a/tests/fixtures/x.sql
+++ b/tests/fixtures/x.sql
@@ -8,3 +8,3 @@
 keep
--- comment
+++ added
 tail
"""
        change = parse_patch(patch)[0]
        self.assertEqual(change.path, "tests/fixtures/x.sql")
        self.assertEqual(change.old_lines, {9})
        self.assertEqual(change.anchors, {9})
        self.assertEqual(change.removed, ["-- comment"])
        self.assertEqual(change.added, ["++ added"])

    def test_scheduler_chooses_cheaper_worker_count(self):
        durations = {0: 3000, 1: 3000, 2: 1000}
        workers = split(set(durations), durations)
        self.assertEqual(len(workers), 2)
        self.assertEqual({n for worker in workers for n in worker}, set(durations))

    def test_diff_tracks_insertions_in_a_second_hunk(self):
        patch = """diff --git a/sqlglot/x.py b/sqlglot/x.py
--- a/sqlglot/x.py
+++ b/sqlglot/x.py
@@ -10 +10 @@
-value = 1
+value = 2
@@ -20,0 +21 @@
+another = 3
"""
        change = parse_patch(patch)[0]
        self.assertEqual(change.old_lines, {10})
        self.assertEqual(change.anchors, {10, 20})

    def test_proven_identity_equivalence_requires_a_known_type(self):
        self.assertTrue(proven_equivalent(edit(
            "sqlglot/executor/context.py", 53,
            "if self._table is None:", "if self._table == None:",
        ), INDEX))
        self.assertFalse(proven_equivalent(edit(
            "sqlglot/executor/context.py", 53,
            "if self.unknown is None:", "if self.unknown == None:",
        ), INDEX))

    def test_version_boundary_is_not_assumed_equivalent(self):
        self.assertFalse(proven_equivalent(edit(
            "sqlglot/generators/clickhouse.py", 811,
            "if self.dialect.version < (23, 12):", "if self.dialect.version <= (23, 12):",
        ), INDEX))
        self.assertFalse(proven_equivalent(edit(
            "sqlglot/generators/clickhouse.py", 811,
            "if self.dialect.version < (23, 12, 0):", "if self.dialect.version <= (23, 12, 0):",
        ), INDEX))

    def test_copy_proof_requires_a_fresh_argument(self):
        self.assertTrue(proven_equivalent(edit(
            "sqlglot/optimizer/eliminate_subqueries.py", 176,
            "result = exp.alias_(exp.table_(name), copy=False)",
            "result = exp.alias_(exp.table_(name), copy=True)",
        ), INDEX))
        self.assertFalse(proven_equivalent(edit(
            "sqlglot/optimizer/eliminate_subqueries.py", 176,
            "result = exp.alias_(table, copy=False)",
            "result = exp.alias_(table, copy=True)",
        ), INDEX))

    def test_mapping_delta_needs_stable_keys(self):
        self.assertEqual(changed_mapping_values('X = {"u": (16, 4), "x": (16, 2)}', 'X = {"u": (17, 4), "x": (16, 2)}'), {"u"})
        self.assertIsNone(changed_mapping_values('X = {"u": (16, 4)}', 'X = {"u": (17, 4), "x": (16, 2)}'))

    def test_source_edit_and_addition_cover_both_hunks(self):
        change = FileChange(
            path="sqlglot/x.py", old_lines={10}, anchors={10, 20},
            removed=["value = 1"], added=["value = 2", "value = 3"],
        )
        selected = impacted_tests(
            [change], {"sqlglot/x.py": {"10": [0], "20": [1]}},
            ["A", "B"], {}, [], {},
            {"class_assignment_lines": {}, "condition_starts": {}},
            {}, {}, {}, {}, {}, {}, {"A": 0, "B": 1},
        )
        self.assertEqual(selected, {"A", "B"})

    def test_uncovered_line_uses_narrowest_enclosing_function(self):
        change = edit("sqlglot/x.py", 20, "if value:", "if not value:")
        selected = impacted_tests(
            [change], {"sqlglot/x.py": {}}, ["A", "B"], {}, [], {},
            {"class_assignment_lines": {}, "condition_starts": {}},
            {}, {}, {}, {}, {}, {}, {"A": 0, "B": 1},
            function_index={"sqlglot/x.py": [[1, 50, [0, 1]], [15, 25, [1]]]},
        )
        self.assertEqual(selected, {"B"})

    def test_import_time_parser_table_reaches_dialect_tests(self):
        change = edit("sqlglot/parsers/snowflake.py", 20, '"X": old', '"X": new')
        selected = impacted_tests(
            [change], {}, [], {}, [], {},
            {"class_assignment_lines": {"sqlglot/parsers/snowflake.py": [20]},
             "class_assignment_classes": {"sqlglot/parsers/snowflake.py": {"20": "SnowflakeParser"}},
             "condition_starts": {}},
            {"primary": {"A": ["snowflake"]}, "secondary": {}},
            {}, {}, {}, {}, {}, {"A": 0, "B": 1},
        )
        self.assertEqual(selected, {"A"})

    def test_core_class_table_reaches_runtime_attribute_reader(self):
        change = edit("sqlglot/parser.py", 20, 'FUNCTIONS = {"X": old}', 'FUNCTIONS = {"X": new}')
        selected = impacted_tests(
            [change], {"sqlglot/parser.py": {"100": [0]}}, ["A", "B"], {}, [], {},
            {"class_assignment_lines": {"sqlglot/parser.py": [20]},
             "class_assignment_symbols": {"sqlglot/parser.py": {"20": "FUNCTIONS"}},
             "attribute_reads": {"FUNCTIONS": [["sqlglot/parser.py", 100]]},
             "condition_starts": {}},
            {}, {}, {}, {}, {}, {}, {"A": 0, "B": 1},
        )
        self.assertEqual(selected, {"A"})

    def test_module_constant_reaches_runtime_reader(self):
        change = edit("sqlglot/constants.py", 20, 'THING = "old"', 'THING = "new"')
        selected = impacted_tests(
            [change], {}, ["A", "B"], {}, [], {},
            {"class_assignment_lines": {}, "condition_starts": {}},
            {}, {}, {}, {}, {}, {}, {"A": 0, "B": 1},
            module_index={
                "declarations": {"sqlglot/constants.py": {"20": ["THING"]}},
                "reads": {"sqlglot/constants.py:THING": [1]},
            },
        )
        self.assertEqual(selected, {"B"})

    def test_typing_metadata_reads_are_selected(self):
        change = edit("sqlglot/typing/snowflake.py", 260, "exp.Sign: value", "exp.HexString: value")
        selected = impacted_tests(
            [change], {}, [], {}, [], {},
            {"class_assignment_lines": {}, "condition_starts": {}},
            {}, {}, {},
            {"sqlglot/typing/snowflake.py": {"260": ["Sign"]}},
            {"snowflake:Sign": ["A"], "snowflake:HexString": ["B"]},
            {}, {"A": 0, "B": 1},
        )
        self.assertTrue({"A", "B"} <= selected)

    def test_test_file_edit_covers_module_import_failures(self):
        change = edit("tests/test_x.py", 42, "assert True", "assert )")
        selected = impacted_tests(
            [change], {}, [], {}, [], {}, {}, {}, {}, {}, {}, {},
            {"tests/test_x.py": ["A", "B"]}, {"A": 0, "B": 1},
        )
        self.assertEqual(selected, {"A", "B"})

    def test_base_typing_metadata_reaches_all_dialects(self):
        change = edit("sqlglot/typing/__init__.py", 60, "exp.Sign: old", "exp.Sign: new")
        selected = impacted_tests(
            [change], {}, [], {}, [], {},
            {"class_assignment_lines": {}, "condition_starts": {}},
            {}, {}, {},
            {"sqlglot/typing/__init__.py": {"60": ["Sign"]}},
            {"snowflake:Sign": ["A"], "postgres:Sign": ["B"]},
            {}, {"A": 0, "B": 1},
        )
        self.assertTrue({"A", "B"} <= selected)



if __name__ == "__main__":
    unittest.main()
