"""Record tests with numeric escape input literals in the pinned suite."""

from __future__ import annotations

import ast
import json
import re
import sys
from collections import defaultdict
from pathlib import Path


ESCAPE = re.compile(r"\\+[A-Za-z0-9]")


def keys(text: str) -> set[str]:
    return {match.group()[-1] for match in ESCAPE.finditer(text)}


def main() -> None:
    source_root, tests_file, fixture_file, output_file = map(Path, sys.argv[1:5])
    known = {test["id"] for test in json.loads(tests_file.read_text(encoding="utf-8"))["tests"]}
    fixtures = json.loads(fixture_file.read_text(encoding="utf-8"))
    dialects = {path.stem for path in (source_root / "sqlglot" / "dialects").glob("*.py")} - {"dialect", "__init__"}
    by_key = defaultdict(set)
    by_dialect_key = defaultdict(set)
    for source in (source_root / "tests").rglob("test_*.py"):
        relative = source.relative_to(source_root).as_posix()
        text = source.read_text(encoding="utf-8")
        tree = ast.parse(text, filename=str(source))
        lines = text.splitlines(keepends=True)
        for klass in (node for node in tree.body if isinstance(node, ast.ClassDef)):
            for method in (node for node in klass.body if isinstance(node, ast.FunctionDef)):
                test_id = f"{relative}::{klass.name}::{method.name}"
                if test_id not in known:
                    continue
                body = "".join(lines[method.lineno - 1:method.end_lineno])
                method_dialects = set()
                if relative.startswith("tests/dialects/test_"):
                    method_dialects.add(source.stem.removeprefix("test_"))
                method_dialects.update(
                    dialect for dialect in dialects
                    if re.search(rf"(?<![a-z0-9_]){re.escape(dialect)}(?![a-z0-9_])", body.lower())
                )
                for key in keys(body):
                    by_key[key].add(test_id)
                    for dialect in method_dialects:
                        by_dialect_key[f"{dialect}:{key}"].add(test_id)
                if any(ord(character) > 127 for character in body):
                    by_key["<unicode>"].add(test_id)
                    for dialect in method_dialects:
                        by_dialect_key[f"{dialect}:<unicode>"].add(test_id)
    for fixture, test_ids in fixtures.items():
        path = source_root / fixture
        if not path.exists() or path.suffix != ".sql":
            continue
        body = path.read_text(encoding="utf-8")
        for key in keys(body):
            by_key[key].update(test_ids)
        if any(ord(character) > 127 for character in body):
            by_key["<unicode>"].update(test_ids)
        statements = body.split(";")
        for index in range(0, len(statements) - 1, 2):
            pair = statements[index] + ";" + statements[index + 1]
            match = re.search(r"(?m)^#\s*dialect:\s*([a-z0-9_]+)", statements[index].lower())
            if not match:
                continue
            dialect = match.group(1)
            for key in keys(pair):
                by_dialect_key[f"{dialect}:{key}"].update(test_ids)
            if any(ord(character) > 127 for character in pair):
                by_dialect_key[f"{dialect}:<unicode>"].update(test_ids)
    output_file.write_text(
        json.dumps({"all": {key: sorted(value) for key, value in sorted(by_key.items())}, "dialect_key": {key: sorted(value) for key, value in sorted(by_dialect_key.items())}}, separators=(",", ":")),
        encoding="utf-8",
    )
    print(f"escape keys={len(by_key)} bytes={output_file.stat().st_size}")


if __name__ == "__main__":
    main()
