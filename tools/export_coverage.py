"""Export compact line-to-test coverage used by the runtime selector."""

from __future__ import annotations

import gzip
import json
import sys
from pathlib import Path

from coverage import CoverageData


def main() -> None:
    data_file, tests_file, output_file, source_root = map(Path, sys.argv[1:5])
    tests = json.loads(tests_file.read_text(encoding="utf-8"))["tests"]
    test_by_id = {test["id"]: test["number"] for test in tests}
    data = CoverageData(basename=str(data_file))
    data.read()
    for additional_path in map(Path, sys.argv[5:]):
        additional = CoverageData(basename=str(additional_path))
        additional.read()
        data.update(additional)
    result = {}
    seen = set()
    for filename in data.measured_files():
        path = Path(filename)
        try:
            relative = path.relative_to(source_root).as_posix()
        except ValueError:
            continue
        if not relative.startswith("sqlglot/"):
            continue
        lines = {}
        for line, contexts in data.contexts_by_lineno(filename).items():
            numbers = sorted({test_by_id[c] for c in contexts if c in test_by_id})
            if numbers:
                lines[str(line)] = numbers
                seen.update(numbers)
        if lines:
            result[relative] = lines
    packed = {"test_ids": [test["id"] for test in tests], "lines": result}
    with gzip.open(output_file, "wt", encoding="utf-8", compresslevel=9) as stream:
        json.dump(packed, stream, separators=(",", ":"), sort_keys=True)
    print(f"files={len(result)} tests={len(seen)} bytes={output_file.stat().st_size}")


if __name__ == "__main__":
    main()
