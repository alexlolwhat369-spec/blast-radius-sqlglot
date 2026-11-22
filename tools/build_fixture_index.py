"""Map immutable SQL fixture files to test IDs using the pinned test source."""

from __future__ import annotations

import ast
import json
import sys
from collections import defaultdict
from pathlib import Path


def main() -> None:
    source_root, tests_file, output_file = map(Path, sys.argv[1:4])
    known_ids = {
        test["id"] for test in json.loads(tests_file.read_text(encoding="utf-8"))["tests"]
    }
    index = defaultdict(set)
    method_sources = []
    for source in (source_root / "tests").rglob("test_*.py"):
        relative = source.relative_to(source_root).as_posix()
        source_text = source.read_text(encoding="utf-8")
        tree = ast.parse(source_text, filename=str(source))
        for klass in (node for node in tree.body if isinstance(node, ast.ClassDef)):
            class_tests = {
                f"{relative}::{klass.name}::{method.name}"
                for method in klass.body
                if isinstance(method, ast.FunctionDef)
                and f"{relative}::{klass.name}::{method.name}" in known_ids
            }
            for method in (node for node in klass.body if isinstance(node, ast.FunctionDef)):
                test_id = f"{relative}::{klass.name}::{method.name}"
                recipients = {test_id} if test_id in known_ids else (
                    class_tests if method.name in {"setUpClass", "setUp", "setup_class", "setup_method"} else set()
                )
                if not recipients:
                    continue
                if test_id in known_ids:
                    method_sources.append((test_id, ast.get_source_segment(source_text, method) or ""))
                for call in (node for node in ast.walk(method) if isinstance(node, ast.Call)):
                    if not call.args or not isinstance(call.args[0], ast.Constant):
                        continue
                    arg = call.args[0].value
                    if not isinstance(arg, str):
                        continue
                    func_name = call.func.attr if isinstance(call.func, ast.Attribute) else (
                        call.func.id if isinstance(call.func, ast.Name) else ""
                    )
                    if func_name == "check_file":
                        index[f"tests/fixtures/optimizer/{arg}.sql"].update(recipients)
                    elif func_name in {"load_sql_fixtures", "load_sql_fixture_pairs"}:
                        index[f"tests/fixtures/{arg}"].update(recipients)
    for fixture in (source_root / "tests" / "fixtures").rglob("*"):
        if not fixture.is_file():
            continue
        relative = fixture.relative_to(source_root).as_posix()
        if relative in index:
            continue
        for test_id, source_text in method_sources:
            if fixture.name in source_text:
                index[relative].add(test_id)
        if not index[relative] and "tpc-ds" in fixture.parts:
            index[relative].update(test_id for test_id in known_ids if "tpcds" in test_id.lower())
        if not index[relative] and "tpc-h" in fixture.parts:
            index[relative].update(test_id for test_id in known_ids if "tpch" in test_id.lower())
    output_file.write_text(
        json.dumps({key: sorted(value) for key, value in sorted(index.items())}, separators=(",", ":")),
        encoding="utf-8",
    )
    print(f"fixture paths={len(index)} bytes={output_file.stat().st_size}")


if __name__ == "__main__":
    main()
