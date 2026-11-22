"""Find tests whose pinned implementation exchanges Expr objects across processes."""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path


def self_calls(method: ast.FunctionDef) -> set[str]:
    return {
        node.func.attr
        for node in ast.walk(method)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id in {"self", "cls"}
    }


def uses_pool(method: ast.FunctionDef) -> bool:
    for node in ast.walk(method):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name) and node.func.id == "ProcessPoolExecutor":
            return True
        if (
            isinstance(node.func, ast.Attribute)
            and node.func.attr == "submit"
            and isinstance(node.func.value, ast.Attribute)
            and node.func.value.attr == "pool"
        ):
            return True
    return False


def main() -> None:
    source_root, tests_file, output_file = map(Path, sys.argv[1:4])
    known_ids = {
        test["id"] for test in json.loads(tests_file.read_text(encoding="utf-8"))["tests"]
    }
    index = set()
    for source in (source_root / "tests").rglob("test_*.py"):
        relative = source.relative_to(source_root).as_posix()
        tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        for klass in (node for node in tree.body if isinstance(node, ast.ClassDef)):
            methods = {
                node.name: node for node in klass.body if isinstance(node, ast.FunctionDef)
            }
            roots = {name for name, method in methods.items() if uses_pool(method)}
            if not roots:
                continue
            calls = {name: self_calls(method) for name, method in methods.items()}
            for name in methods:
                test_id = f"{relative}::{klass.name}::{name}"
                if test_id not in known_ids:
                    continue
                reachable = {name}
                frontier = [name]
                while frontier:
                    for callee in calls.get(frontier.pop(), ()) - reachable:
                        reachable.add(callee)
                        if callee in methods:
                            frontier.append(callee)
                if reachable & roots:
                    index.add(test_id)
    output_file.write_text(json.dumps(sorted(index), separators=(",", ":")), encoding="utf-8")
    print(f"process tests={len(index)} bytes={output_file.stat().st_size}")


if __name__ == "__main__":
    main()
