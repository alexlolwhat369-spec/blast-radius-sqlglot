"""Select tests from a patch using pinned-commit impact maps."""

from __future__ import annotations

import gzip
import json
import math
import os
import re
import sys
from pathlib import Path

from patch_model import parse_patch
from scheduler import split
from semantic import changed_mapping_values, proven_equivalent


ROOT = Path(__file__).resolve().parent
DATA = Path(os.environ.get("BLAST_DATA", "/data"))


def read_index(path: Path) -> dict:
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        return json.load(stream)


def impacted_tests(changes, coverage: dict, coverage_ids: list[str], fixtures: dict, process_tests: list[str], semantic_index: dict, code_index: dict, dialect_index: dict, escape_index: dict, test_index: dict, tests_by_file: dict[str, list[str]], test_by_id: dict[str, int]) -> set[str]:
    selected: set[str] = set()
    executable_source_changes = [change for change in changes if change.path.startswith("sqlglot/") and change.path.endswith(".py") and not change.comment_only]
    single_source_change = len(executable_source_changes) == 1
    for change in changes:
        if change.path.startswith("tests/fixtures/"):
            fixture_tests = fixtures.get(change.path)
            if fixture_tests is None:
                fixture_tests = list(test_by_id)
            selected.update(fixture_tests)
            continue
        if change.path.startswith("tests/") and change.path.endswith(".py"):
            file_tests = set()
            for line in change.old_lines or change.anchors:
                entries = [entry for entry in test_index.get(change.path, []) if entry[0] <= line <= entry[1]]
                if entries:
                    file_tests.update(min(entries, key=lambda entry: entry[1] - entry[0])[2])
            if not file_tests:
                file_tests.update(tests_by_file.get(change.path, test_by_id))
            selected.update(file_tests)
            continue
        if change.path.startswith("sqlglot/") and change.path.endswith(".py"):
            if change.comment_only:
                if (change.old_lines | change.anchors) & set(code_index["unsafe_comment_lines"].get(change.path, [])):
                    selected.update(test_by_id)
                continue
            if single_source_change and proven_equivalent(change, semantic_index):
                continue
            lines = coverage.get(change.path, {})
            touched = change.old_lines or change.anchors
            selected_before = len(selected)
            assignment_lines = set(code_index["class_assignment_lines"].get(change.path, []))
            if touched and touched <= assignment_lines:
                symbol_match = re.match(r"\s*([A-Z][A-Z0-9_]*)\s*=", change.removed[0]) if change.removed else None
                if symbol_match and change.path.startswith("sqlglot/dialects/"):
                    symbol = symbol_match.group(1)
                    dialect = Path(change.path).stem
                    if single_source_change and symbol == "NUMERIC_ESCAPES" and len(change.removed) == len(change.added) == 1:
                        keys = changed_mapping_values(change.removed[0], change.added[0])
                        if keys is not None:
                            relevant_ids = {
                                test_id
                                for key in keys
                                for test_id in escape_index["dialect_key"].get(f"{dialect}:{key}", [])
                                if dialect in dialect_index["primary"].get(test_id, [])
                            }
                            selected.update(relevant_ids)
                            continue
                    relevant_ids = {
                        test_id
                        for source, line in code_index["attribute_reads"].get(symbol, [])
                        for index in coverage.get(source, {}).get(str(line), [])
                        if (test_id := coverage_ids[index]) and dialect in dialect_index["primary"].get(test_id, [])
                    }
                    if 0 < len(relevant_ids) <= 16:
                        selected.update(relevant_ids)
                        continue
            for line in touched:
                selected.update(coverage_ids[index] for index in lines.get(str(line), []))
                start = code_index["condition_starts"].get(change.path, {}).get(str(line))
                if start is not None:
                    selected.update(coverage_ids[index] for index in lines.get(str(start), []))
            if change.path == "sqlglot/serde.py":
                selected.update(process_tests)
            if len(selected) == selected_before and (
                not change.old_lines
                or not change.added
                or any(re.match(r"\s*(?:from\s+|import\s+|def\s+|class\s+|@)", line) for line in change.removed + change.added)
            ):
                selected.update(test_by_id)
    return selected


def main() -> None:
    tests = json.loads((DATA / "tests.json").read_text(encoding="utf-8"))["tests"]
    test_by_id = {test["id"]: test["number"] for test in tests}
    milliseconds = {
        test["number"]: math.floor(test["seconds"] * 1000 + 0.5) for test in tests
    }
    coverage_index = read_index(ROOT / "coverage.json.gz")
    coverage_ids = coverage_index["test_ids"]
    coverage = coverage_index["lines"]
    fixtures = json.loads((ROOT / "fixture_index.json").read_text(encoding="utf-8"))
    process_tests = json.loads((ROOT / "process_index.json").read_text(encoding="utf-8"))
    semantic_index = json.loads((ROOT / "semantic_index.json").read_text(encoding="utf-8"))
    code_index = read_index(ROOT / "code_index.json.gz")
    dialect_index = json.loads((ROOT / "dialect_index.json").read_text(encoding="utf-8"))
    escape_index = json.loads((ROOT / "escape_index.json").read_text(encoding="utf-8"))
    test_index = read_index(ROOT / "test_index.json.gz")
    tests_by_file = {}
    for test in tests:
        tests_by_file.setdefault(test["file"], []).append(test["id"])
    for patch_file in sorted((DATA / "commits").glob("*.patch")):
        changes = parse_patch(patch_file.read_text(encoding="utf-8"))
        selected_ids = impacted_tests(changes, coverage, coverage_ids, fixtures, process_tests, semantic_index, code_index, dialect_index, escape_index, test_index, tests_by_file, test_by_id)
        selected = {test_by_id[test_id] for test_id in selected_ids if test_id in test_by_id}
        workers = split(selected, milliseconds)
        sys.stdout.write(json.dumps({"commit": patch_file.stem, "workers": workers}, separators=(",", ":")) + "\n")


if __name__ == "__main__":
    main()
