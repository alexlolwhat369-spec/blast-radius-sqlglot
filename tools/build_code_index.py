"""Locate condition starts and named attribute reads in pinned Python source."""

from __future__ import annotations

import ast
import gzip
import io
import json
import sys
import tokenize
from collections import defaultdict
from pathlib import Path


def main() -> None:
    source_root, output_file = map(Path, sys.argv[1:3])
    condition_starts = {}
    reads = defaultdict(list)
    assignments = {}
    unsafe_comment_lines = {}
    for source in (source_root / "sqlglot").rglob("*.py"):
        relative = source.relative_to(source_root).as_posix()
        source_text = source.read_text(encoding="utf-8")
        tree = ast.parse(source_text, filename=str(source))
        unsafe = set()
        for token in tokenize.generate_tokens(io.StringIO(source_text).readline):
            if token.type == tokenize.STRING and token.end[0] > token.start[0]:
                unsafe.update(range(token.start[0] + 1, token.end[0] + 1))
        for line_number, line in enumerate(source_text.splitlines(), start=1):
            if line.rstrip().endswith("\\"):
                unsafe.add(line_number + 1)
        if unsafe:
            unsafe_comment_lines[relative] = sorted(unsafe)
        file_conditions = {}
        file_assignments = {}
        for node in ast.walk(tree):
            if isinstance(node, (ast.If, ast.IfExp, ast.While)):
                test = node.test
                if test.end_lineno > test.lineno:
                    for line in range(test.lineno, test.end_lineno + 1):
                        file_conditions[line] = min(file_conditions.get(line, test.lineno), test.lineno)
            if isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Load) and node.attr.isupper():
                reads[node.attr].append((relative, node.lineno))
        # ast does not retain parents; direct class-body inspection identifies data declarations.
        for klass in (node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)):
            for part in klass.body:
                if isinstance(part, (ast.Assign, ast.AnnAssign)):
                    for line in range(part.lineno, part.end_lineno + 1):
                        file_assignments[line] = True
        if file_conditions:
            condition_starts[relative] = {str(k): v for k, v in file_conditions.items()}
        if file_assignments:
            assignments[relative] = sorted(file_assignments)
    packed = {
        "condition_starts": condition_starts,
        "attribute_reads": {key: sorted(set(value)) for key, value in reads.items()},
        "class_assignment_lines": assignments,
        "unsafe_comment_lines": unsafe_comment_lines,
    }
    with gzip.open(output_file, "wt", encoding="utf-8", compresslevel=9) as stream:
        json.dump(packed, stream, separators=(",", ":"), sort_keys=True)
    print(f"condition files={len(condition_starts)} attributes={len(reads)} bytes={output_file.stat().st_size}")


if __name__ == "__main__":
    main()
