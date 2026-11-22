"""Pack pinned source text for syntax checks on independent patches."""

from __future__ import annotations

import gzip
import json
import sys
from pathlib import Path


def main() -> None:
    source_root, output_file = map(Path, sys.argv[1:3])
    sources = {
        path.relative_to(source_root).as_posix(): path.read_text(encoding="utf-8")
        for path in (source_root / "sqlglot").rglob("*.py")
    }
    with gzip.open(output_file, "wt", encoding="utf-8", compresslevel=9) as stream:
        json.dump(sources, stream, separators=(",", ":"), sort_keys=True)
    print(f"files={len(sources)} bytes={output_file.stat().st_size}")


if __name__ == "__main__":
    main()
