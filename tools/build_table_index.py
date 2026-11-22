"""Index literal dictionary entry lines in pinned class declarations."""

from __future__ import annotations

import ast
import gzip
import json
import sys
from collections import defaultdict
from pathlib import Path


def main() -> None:
    source_root, output_file = map(Path, sys.argv[1:3])
    index = {}
    for source in (source_root / "sqlglot").rglob("*.py"):
        relative = source.relative_to(source_root).as_posix()
        entries = defaultdict(list)
        tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        for klass in (node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)):
            for part in klass.body:
                if not isinstance(part, (ast.Assign, ast.AnnAssign)) or not isinstance(part.value, ast.Dict):
                    continue
                targets = part.targets if isinstance(part, ast.Assign) else [part.target]
                names = [target.id for target in targets if isinstance(target, ast.Name)]
                if len(names) != 1:
                    continue
                for key, value in zip(part.value.keys, part.value.values):
                    if not isinstance(key, ast.Constant) or not isinstance(key.value, str):
                        continue
                    for line in range(key.lineno, value.end_lineno + 1):
                        entries[str(line)].append([klass.name, names[0], key.value])
        if entries:
            index[relative] = {line: values for line, values in entries.items()}
    with gzip.open(output_file, "wt", encoding="utf-8", compresslevel=9) as stream:
        json.dump(index, stream, separators=(",", ":"), sort_keys=True)
    print(f"files={len(index)} bytes={output_file.stat().st_size}")


if __name__ == "__main__":
    main()
