"""Propagate pinned per-test table reads through class inheritance."""

from __future__ import annotations

import gzip
import json
import sys
from collections import defaultdict
from pathlib import Path


def main() -> None:
    trace_file, mro_file, output_file = map(Path, sys.argv[1:4])
    if trace_file.suffix == ".gz":
        with gzip.open(trace_file, "rt", encoding="utf-8") as stream:
            trace = json.load(stream)
    else:
        trace = json.loads(trace_file.read_text(encoding="utf-8"))
    with gzip.open(mro_file, "rt", encoding="utf-8") as stream:
        mro = json.load(stream)
    users = defaultdict(set)
    for trace_key, tests in trace.items():
        module, klass, attribute, key = trace_key.split(":", 3)
        class_key = f"{module}:{klass}"
        for ancestor in mro.get(class_key, [class_key]):
            if ancestor.startswith("sqlglot."):
                users[f"{ancestor}:{attribute}:{key}"].update(tests)
    with gzip.open(output_file, "wt", encoding="utf-8", compresslevel=9) as stream:
        json.dump(
            {key: sorted(value) for key, value in users.items()},
            stream, separators=(",", ":"), sort_keys=True,
        )
    print(f"keys={len(users)} bytes={output_file.stat().st_size}")


if __name__ == "__main__":
    main()
