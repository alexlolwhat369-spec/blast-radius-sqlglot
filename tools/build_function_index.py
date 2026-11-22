"""Index tests that execute each pinned source function (offline tool)."""

from __future__ import annotations

import ast
import gzip
import json
import sys
from pathlib import Path


def main() -> None:
    source_root, coverage_file, output_file = map(Path, sys.argv[1:4])
    with gzip.open(coverage_file, "rt", encoding="utf-8") as stream:
        coverage = json.load(stream)["lines"]
    index = {}
    for source in (source_root / "sqlglot").rglob("*.py"):
        path = source.relative_to(source_root).as_posix()
        lines = coverage.get(path, {})
        tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        entries = []
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            tests = set()
            for line in range(node.lineno, node.end_lineno + 1):
                tests.update(lines.get(str(line), []))
            if tests:
                entries.append([node.lineno, node.end_lineno, sorted(tests)])
        if entries:
            index[path] = entries
    with gzip.open(output_file, "wt", encoding="utf-8", compresslevel=9) as stream:
        json.dump(index, stream, separators=(",", ":"), sort_keys=True)
    print(f"files={len(index)} bytes={output_file.stat().st_size}")


if __name__ == "__main__":
    main()
