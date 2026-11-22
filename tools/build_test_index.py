"""Map pinned test source ranges to numbered test IDs."""

from __future__ import annotations

import ast
import gzip
import json
import sys
from pathlib import Path


def main() -> None:
    source_root, tests_file, output_file = map(Path, sys.argv[1:4])
    tests = json.loads(tests_file.read_text(encoding="utf-8"))["tests"]
    known = {test["id"] for test in tests}
    result = {}
    for source in (source_root / "tests").rglob("*.py"):
        relative = source.relative_to(source_root).as_posix()
        tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        entries = []
        for klass in (node for node in tree.body if isinstance(node, ast.ClassDef)):
            class_ids = sorted(
                test["id"] for test in tests
                if test["file"] == relative and test["id"].startswith(f"{relative}::{klass.name}::")
            )
            if not class_ids:
                continue
            entries.append([klass.lineno, klass.end_lineno, class_ids])
            for method in (node for node in klass.body if isinstance(node, ast.FunctionDef)):
                test_id = f"{relative}::{klass.name}::{method.name}"
                if test_id in known:
                    entries.append([method.lineno, method.end_lineno, [test_id]])
        if entries:
            result[relative] = entries
    with gzip.open(output_file, "wt", encoding="utf-8", compresslevel=9) as stream:
        json.dump(result, stream, separators=(",", ":"), sort_keys=True)
    print(f"test source files={len(result)} bytes={output_file.stat().st_size}")


if __name__ == "__main__":
    main()
