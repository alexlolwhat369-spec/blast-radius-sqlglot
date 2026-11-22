"""Record pinned class inheritance for table read attribution."""

from __future__ import annotations

import gzip
import importlib
import json
import pkgutil
import sys
from pathlib import Path


def main() -> None:
    source_root, output_file = map(Path, sys.argv[1:3])
    sys.path.insert(0, str(source_root.resolve()))
    result = {}
    seen = set()

    def add_class(value, module_name):
        if not isinstance(value, type) or value.__module__ != module_name or id(value) in seen:
            return
        seen.add(id(value))
        key = f"{value.__module__}:{value.__name__}"
        result[key] = [
            f"{base.__module__}:{base.__name__}"
            for base in value.__mro__
        ]
        for nested in vars(value).values():
            add_class(nested, module_name)

    for package_name in (
        "sqlglot.parsers", "sqlglot.generators", "sqlglot.dialects",
        "sqlglot.expressions", "sqlglot.typing",
    ):
        package = importlib.import_module(package_name)
        for info in pkgutil.iter_modules(package.__path__, package_name + "."):
            module = importlib.import_module(info.name)
            for value in vars(module).values():
                add_class(value, module.__name__)
    with gzip.open(output_file, "wt", encoding="utf-8", compresslevel=9) as stream:
        json.dump(result, stream, separators=(",", ":"), sort_keys=True)
    print(f"classes={len(result)} bytes={output_file.stat().st_size}")


if __name__ == "__main__":
    main()
