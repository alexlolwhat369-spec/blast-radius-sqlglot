"""Measure the public-sample cost of a function-scope recall fallback."""

from __future__ import annotations

import gzip
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from patch_model import parse_patch


root = Path(__file__).resolve().parents[1]
data = Path(sys.argv[1])
with gzip.open(root / "coverage.json.gz", "rt", encoding="utf-8") as stream:
    coverage_index = json.load(stream)
with gzip.open(root / "function_index.json.gz", "rt", encoding="utf-8") as stream:
    functions = json.load(stream)
coverage = coverage_index["lines"]
ids = coverage_index["test_ids"]
for patch_file in sorted((data / "commits").glob("*.patch")):
    additions = set()
    details = []
    for change in parse_patch(patch_file.read_text(encoding="utf-8")):
        if not change.path.startswith("sqlglot/") or change.comment_only:
            continue
        lines = coverage.get(change.path, {})
        for touched in sorted(change.old_lines | change.anchors):
            if lines.get(str(touched)):
                continue
            containing = [entry for entry in functions.get(change.path, []) if entry[0] <= touched <= entry[1]]
            if not containing:
                continue
            start, end, tests = min(containing, key=lambda entry: entry[1] - entry[0])
            additions.update(ids[i] for i in tests)
            details.append(f"{change.path}:{touched}->{start}-{end}({len(tests)})")
    if details:
        print(patch_file.stem, len(additions), "; ".join(details))
