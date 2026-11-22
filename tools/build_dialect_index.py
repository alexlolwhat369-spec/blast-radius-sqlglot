"""Derive dialect usage by test from pinned test bodies and SQL fixtures."""

from __future__ import annotations

import ast
import json
import re
import sys
from collections import defaultdict
from pathlib import Path


def main() -> None:
    source_root, tests_file, fixture_file, output_file = map(Path, sys.argv[1:5])
    tests = json.loads(tests_file.read_text(encoding="utf-8"))["tests"]
    fixture_index = json.loads(fixture_file.read_text(encoding="utf-8"))
    dialects = {
        path.stem for path in (source_root / "sqlglot" / "dialects").glob("*.py")
    } - {"dialect", "__init__"}
    primary = defaultdict(set)
    secondary = defaultdict(set)
    for test in tests:
        file = test["file"]
        if file.startswith("tests/dialects/test_"):
            dialect = Path(file).stem.removeprefix("test_")
            if dialect in dialects:
                primary[test["id"]].add(dialect)
    for source in (source_root / "tests").rglob("test_*.py"):
        relative = source.relative_to(source_root).as_posix()
        tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        for klass in (node for node in tree.body if isinstance(node, ast.ClassDef)):
            for method in (node for node in klass.body if isinstance(node, ast.FunctionDef)):
                test_id = f"{relative}::{klass.name}::{method.name}"
                if not method.name.startswith("test_"):
                    continue
                constants = [node.value.lower() for node in ast.walk(method) if isinstance(node, ast.Constant) and isinstance(node.value, str)]
                for dialect in dialects:
                    pattern = rf"(?<![a-z0-9_]){re.escape(dialect)}(?![a-z0-9_])"
                    if any(re.search(pattern, value) for value in constants):
                        secondary[test_id].add(dialect)
    for fixture, test_ids in fixture_index.items():
        path = source_root / fixture
        if not path.exists() or path.suffix != ".sql":
            continue
        declared = set(re.findall(r"(?m)^#\s*dialect:\s*([a-z0-9_]+)", path.read_text(encoding="utf-8").lower()))
        for test_id in test_ids:
            primary[test_id].update(declared & dialects)
    packed = {
        "primary": {key: sorted(value) for key, value in sorted(primary.items()) if value},
        "secondary": {key: sorted(value) for key, value in sorted(secondary.items()) if value},
    }
    output_file.write_text(
        json.dumps(packed, separators=(",", ":")),
        encoding="utf-8",
    )
    print(f"primary users={len(primary)} secondary users={len(secondary)} bytes={output_file.stat().st_size}")


if __name__ == "__main__":
    main()
