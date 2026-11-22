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


def impacted_tests(changes, coverage: dict, coverage_ids: list[str], fixtures: dict, process_tests: list[str], semantic_index: dict, code_index: dict, dialect_index: dict, escape_index: dict, expression_usage: dict, typing_index: dict, typing_usage: dict, tests_by_file: dict[str, list[str]], test_by_id: dict[str, int], function_index: dict | None = None) -> set[str]:
    selected: set[str] = set()
    function_index = function_index or {}
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
            selected.update(tests_by_file.get(change.path, test_by_id))
            continue
        if change.path.startswith("sqlglot/") and change.path.endswith(".py"):
            if change.comment_only:
                if (change.old_lines | change.anchors) & set(code_index["unsafe_comment_lines"].get(change.path, [])):
                    selected.update(test_by_id)
                continue
            if single_source_change and proven_equivalent(change, semantic_index):
                continue
            if change.path.startswith("sqlglot/typing/"):
                selected.add("tests/test_typing.py::TestTyping::test_no_redundant_expression_metadata")
                dialect = Path(change.path).stem
                metadata_lines = typing_index.get(change.path, {})
                metadata_classes = set()
                for line in change.old_lines | change.anchors:
                    metadata_classes.update(metadata_lines.get(str(line), []))
                metadata_classes.update(
                    re.findall(r"\bexp\.([A-Z]\w+)\b", "\n".join(change.removed + change.added))
                )
                for class_name in metadata_classes:
                    if dialect == "__init__":
                        for key, test_ids in typing_usage.items():
                            if key.endswith(f":{class_name}"):
                                selected.update(test_ids)
                    else:
                        selected.update(typing_usage.get(f"{dialect}:{class_name}", []))
            if change.path in {"sqlglot/__init__.py", "sqlglot/dialects/__init__.py", "sqlglot/dialects/dialect.py"}:
                selected.add("tests/dialects/test_dialect.py::TestDialect::test_lazy_load")
            lines = coverage.get(change.path, {})
            touched = change.old_lines | change.anchors
            file_selected: set[str] = set()
            assignment_lines = set(code_index["class_assignment_lines"].get(change.path, []))
            if touched and touched <= assignment_lines:
                if os.environ.get("BLAST_CLASS_PROBE") == "1":
                    selected.update(test_by_id)
                    continue
                if change.path.startswith("sqlglot/expressions/"):
                    module = change.path.removesuffix(".py").replace("/", ".")
                    class_names = {
                        code_index["class_assignment_classes"].get(change.path, {}).get(str(line))
                        for line in touched
                    }
                    for class_name in class_names - {None}:
                        file_selected.update(expression_usage.get(f"{module}:{class_name}", []))
                    if file_selected:
                        selected.update(file_selected)
                        continue
                if change.path.startswith(("sqlglot/parsers/", "sqlglot/generators/")):
                    dialect = Path(change.path).stem
                    dialect_tests = {
                        test_id for test_id in test_by_id
                        if dialect in dialect_index["primary"].get(test_id, [])
                        or dialect in dialect_index["secondary"].get(test_id, [])
                    }
                    if dialect_tests:
                        selected.update(dialect_tests)
                        continue
                symbol_match = re.match(r"\s*([A-Z][A-Z0-9_]*)\s*=", change.removed[0]) if change.removed else None
                if change.path.startswith("sqlglot/dialects/"):
                    symbols = {
                        code_index.get("class_assignment_symbols", {}).get(change.path, {}).get(str(line))
                        for line in touched
                    } - {None}
                    if symbol_match:
                        symbols.add(symbol_match.group(1))
                    dialect = Path(change.path).stem
                    if single_source_change and symbols == {"NUMERIC_ESCAPES"} and len(change.removed) == len(change.added) == 1:
                        keys = changed_mapping_values(change.removed[0], change.added[0])
                        if keys is not None:
                            relevant_ids = {
                                test_id
                                for key in keys
                                for test_id in escape_index["dialect_key"].get(f"{dialect}:{key}", [])
                            }
                            selected.update(relevant_ids)
                            continue
                    relevant_ids = {
                        test_id
                        for symbol in symbols
                        for source, line in code_index["attribute_reads"].get(symbol, [])
                        for index in coverage.get(source, {}).get(str(line), [])
                        if (test_id := coverage_ids[index]) and (
                            dialect in dialect_index["primary"].get(test_id, [])
                            or dialect in dialect_index["secondary"].get(test_id, [])
                        )
                    }
                    if relevant_ids:
                        selected.update(relevant_ids)
                        continue
                    selected.update(
                        test_id for test_id in test_by_id
                        if dialect in dialect_index["primary"].get(test_id, [])
                        or dialect in dialect_index["secondary"].get(test_id, [])
                    )
                    continue
                symbols = {
                    code_index.get("class_assignment_symbols", {}).get(change.path, {}).get(str(line))
                    for line in touched
                } - {None}
                readers = {
                    coverage_ids[index]
                    for symbol in symbols
                    for source, read_line in code_index["attribute_reads"].get(symbol, [])
                    for index in coverage.get(source, {}).get(str(read_line), [])
                }
                if readers:
                    selected.update(readers)
                    continue
                module_users = {
                    coverage_ids[index]
                    for indexes in coverage.get(change.path, {}).values()
                    for index in indexes
                }
                if module_users:
                    selected.update(module_users)
                    continue
            for line in touched:
                direct = lines.get(str(line), [])
                file_selected.update(coverage_ids[index] for index in direct)
                start = code_index["condition_starts"].get(change.path, {}).get(str(line))
                if start is not None:
                    file_selected.update(coverage_ids[index] for index in lines.get(str(start), []))
                if not direct and start is None:
                    containing = [
                        entry for entry in function_index.get(change.path, [])
                        if entry[0] <= line <= entry[1]
                    ]
                    if containing:
                        narrowest = min(containing, key=lambda entry: entry[1] - entry[0])
                        file_selected.update(coverage_ids[index] for index in narrowest[2])
            selected.update(file_selected)
            if change.path == "sqlglot/serde.py":
                selected.update(process_tests)
            if not file_selected and (
                not change.old_lines
                or not change.added
                or any(re.match(r"\s*(?:from\s+|import\s+|def\s+|class\s+|@)", line) for line in change.removed + change.added)
            ):
                selected.update(test_by_id)
        if change.path.startswith("sqlglotc/") or change.path in {"setup.py", "pyproject.toml"}:
            selected.update(test_id for test_id in test_by_id if test_id.startswith("tests/test_sqlglotc.py::"))
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
    expression_usage = read_index(ROOT / "expression_usage.json.gz")
    typing_index = read_index(ROOT / "typing_index.json.gz")
    typing_usage = read_index(ROOT / "typing_usage.json.gz")
    function_index = read_index(ROOT / "function_index.json.gz")
    tests_by_file = {}
    for test in tests:
        tests_by_file.setdefault(test["file"], []).append(test["id"])
    for patch_file in sorted((DATA / "commits").glob("*.patch")):
        changes = parse_patch(patch_file.read_text(encoding="utf-8"))
        selected_ids = impacted_tests(changes, coverage, coverage_ids, fixtures, process_tests, semantic_index, code_index, dialect_index, escape_index, expression_usage, typing_index, typing_usage, tests_by_file, test_by_id, function_index=function_index)
        selected = {test_by_id[test_id] for test_id in selected_ids if test_id in test_by_id}
        workers = split(selected, milliseconds)
        sys.stdout.write(json.dumps({"commit": patch_file.stem, "workers": workers}, separators=(",", ":")) + "\n")


if __name__ == "__main__":
    main()
