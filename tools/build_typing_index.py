"""Map source lines of dialect metadata declarations to expression classes."""

from __future__ import annotations

import ast
import gzip
import json
import sys
from collections import defaultdict
from pathlib import Path


def expression_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "exp":
        return node.attr
    return None


def entries(node: ast.Dict, lines: dict[int, set[str]]) -> None:
    for key, value in zip(node.keys, node.values):
        if key is None and isinstance(value, ast.Dict):
            entries(value, lines)
            continue
        names = set()
        if key is not None:
            name = expression_name(key)
            if name:
                names.add(name)
        elif isinstance(value, ast.DictComp):
            for generator in value.generators:
                names.update(
                    name for child in ast.walk(generator.iter)
                    if (name := expression_name(child))
                )
        if names:
            start = key.lineno if key is not None else value.lineno
            for line in range(start, value.end_lineno + 1):
                lines[line].update(names)


def main() -> None:
    source_root, output_file = map(Path, sys.argv[1:3])
    index = {}
    for source in (source_root / "sqlglot" / "typing").glob("*.py"):
        tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        lines: dict[int, set[str]] = defaultdict(set)
        for node in tree.body:
            if isinstance(node, ast.Assign) and any(
                isinstance(target, ast.Name) and target.id == "EXPRESSION_METADATA"
                for target in node.targets
            ) and isinstance(node.value, ast.Dict):
                entries(node.value, lines)
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == "EXPRESSION_METADATA" and isinstance(node.value, ast.Dict):
                entries(node.value, lines)
        if lines:
            index[source.relative_to(source_root).as_posix()] = {
                str(line): sorted(names) for line, names in lines.items()
            }
    with gzip.open(output_file, "wt", encoding="utf-8", compresslevel=9) as stream:
        json.dump(index, stream, separators=(",", ":"), sort_keys=True)
    print(f"files={len(index)} bytes={output_file.stat().st_size}")


if __name__ == "__main__":
    main()
