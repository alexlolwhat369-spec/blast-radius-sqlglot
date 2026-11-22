"""Map pinned module declarations to tests that execute their readers."""

from __future__ import annotations

import ast
import gzip
import json
import sys
from collections import defaultdict
from pathlib import Path


def assigned_names(node: ast.AST) -> set[str]:
    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
    return {
        child.id
        for target in targets
        for child in ast.walk(target)
        if isinstance(child, ast.Name)
    }


def module_path(name: str, known: set[str]) -> str | None:
    candidate = name.replace(".", "/") + ".py"
    if candidate in known:
        return candidate
    candidate = name.replace(".", "/") + "/__init__.py"
    return candidate if candidate in known else None


def main() -> None:
    source_root, coverage_file, output_file = map(Path, sys.argv[1:4])
    with gzip.open(coverage_file, "rt", encoding="utf-8") as stream:
        coverage = json.load(stream)["lines"]
    sources = {
        path.relative_to(source_root).as_posix(): path
        for path in (source_root / "sqlglot").rglob("*.py")
    }
    declarations: dict[str, dict[str, list[str]]] = {}
    trees = {}
    for relative, source in sources.items():
        tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        trees[relative] = tree
        per_line = defaultdict(set)
        for node in tree.body:
            if isinstance(node, (ast.Assign, ast.AnnAssign)):
                names = assigned_names(node)
                for line in range(node.lineno, node.end_lineno + 1):
                    per_line[str(line)].update(names)
        if per_line:
            declarations[relative] = {
                line: sorted(names) for line, names in per_line.items()
            }
    symbols = {
        f"{path}:{symbol}"
        for path, lines in declarations.items()
        for names in lines.values()
        for symbol in names
    }
    reads = defaultdict(set)
    for relative, tree in trees.items():
        local = {
            symbol for key in symbols if key.startswith(relative + ":")
            for symbol in [key[len(relative) + 1:]]
        }
        imported = {}
        modules = {}
        for node in tree.body:
            if isinstance(node, ast.ImportFrom) and node.module:
                if node.level:
                    package = relative.removesuffix("/__init__.py").removesuffix(".py").replace("/", ".").split(".")[:-1]
                    name = ".".join(package[:len(package) - node.level + 1] + [node.module])
                else:
                    name = node.module
                source = module_path(name, set(sources))
                if source:
                    for alias in node.names:
                        imported[alias.asname or alias.name] = f"{source}:{alias.name}"
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    source = module_path(alias.name, set(sources))
                    if source:
                        modules[alias.asname or alias.name.split(".")[0]] = source
        for node in ast.walk(tree):
            key = None
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                if node.id in local:
                    key = f"{relative}:{node.id}"
                elif node.id in imported:
                    key = imported[node.id]
            elif isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Load) and isinstance(node.value, ast.Name):
                source = modules.get(node.value.id)
                if source:
                    key = f"{source}:{node.attr}"
            if key in symbols:
                reads[key].update(coverage.get(relative, {}).get(str(node.lineno), []))
    packed = {
        "declarations": declarations,
        "reads": {key: sorted(values) for key, values in reads.items() if values},
    }
    with gzip.open(output_file, "wt", encoding="utf-8", compresslevel=9) as stream:
        json.dump(packed, stream, separators=(",", ":"), sort_keys=True)
    print(f"declaration_files={len(declarations)} read_symbols={len(packed['reads'])} bytes={output_file.stat().st_size}")


if __name__ == "__main__":
    main()
