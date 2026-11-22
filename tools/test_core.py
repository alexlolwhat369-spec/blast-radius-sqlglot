from __future__ import annotations

import sys
import json
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from patch_model import FileChange, parse_patch
from scheduler import split
from semantic import changed_mapping_values, proven_equivalent


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
        self.assertEqual(change.anchors, {10})
        self.assertEqual(change.removed, ["-- comment"])
        self.assertEqual(change.added, ["++ added"])

    def test_scheduler_chooses_cheaper_worker_count(self):
        durations = {0: 3000, 1: 3000, 2: 1000}
        workers = split(set(durations), durations)
        self.assertEqual(len(workers), 2)
        self.assertEqual({n for worker in workers for n in worker}, set(durations))

    def test_proven_identity_equivalence_requires_a_known_type(self):
        self.assertTrue(proven_equivalent(edit(
            "sqlglot/executor/context.py", 53,
            "if self._table is None:", "if self._table == None:",
        ), INDEX))
        self.assertFalse(proven_equivalent(edit(
            "sqlglot/executor/context.py", 53,
            "if self.unknown is None:", "if self.unknown == None:",
        ), INDEX))

    def test_tuple_length_proof_has_a_negative_case(self):
        self.assertTrue(proven_equivalent(edit(
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


if __name__ == "__main__":
    unittest.main()
