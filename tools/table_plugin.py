"""Trace keys read from pinned class dictionaries."""

from __future__ import annotations

import importlib
import json
import os
import pkgutil
import sys
from collections import defaultdict

from tools.expression_plugin import ImmediateExecutor


_current = None
_reads = defaultdict(set)
_wrapped = set()


class TracingDict(dict):
    def __init__(self, source: dict, table: str):
        super().__init__(source)
        self._table = table

    def _record(self, key):
        if _current is not None:
            label = key if isinstance(key, str) else "*"
            _reads[f"{self._table}:{label}"].add(_current)

    def __getitem__(self, key):
        self._record(key)
        return super().__getitem__(key)

    def get(self, key, default=None):
        self._record(key)
        return super().get(key, default)

    def __contains__(self, key):
        self._record(key)
        return super().__contains__(key)

    def setdefault(self, key, default=None):
        self._record(key)
        return super().setdefault(key, default)

    def pop(self, key, *default):
        self._record(key)
        return super().pop(key, *default)

    def __iter__(self):
        self._record("*")
        return super().__iter__()

    def keys(self):
        self._record("*")
        return super().keys()

    def values(self):
        self._record("*")
        return super().values()

    def items(self):
        self._record("*")
        return super().items()


def pytest_collection_modifyitems(items):
    def wrap_class(value, module_name):
        if not isinstance(value, type) or value.__module__ != module_name or id(value) in _wrapped:
            return
        _wrapped.add(id(value))
        for name, original in vars(value).items():
            if type(original) is dict:
                setattr(value, name, TracingDict(original, f"{module_name}:{value.__name__}:{name}"))
            elif isinstance(original, type):
                wrap_class(original, module_name)

    for package_name in (
        "sqlglot.parsers", "sqlglot.generators", "sqlglot.dialects",
        "sqlglot.expressions", "sqlglot.typing",
    ):
        package = importlib.import_module(package_name)
        for info in pkgutil.iter_modules(package.__path__, package_name + "."):
            module = importlib.import_module(info.name)
            for value in vars(module).values():
                wrap_class(value, module.__name__)
    if os.environ.get("BLAST_IN_PROCESS_OPTIMIZER") == "1":
        module = sys.modules.get("tests.test_optimizer")
        if module is not None:
            module.ProcessPoolExecutor = ImmediateExecutor
    if os.environ.get("BLAST_IN_PROCESS_EXECUTOR") == "1":
        module = sys.modules.get("tests.test_executor")
        if module is not None:
            module.ProcessPoolExecutor = ImmediateExecutor


def pytest_runtest_setup(item):
    global _current
    _current = item.nodeid


def pytest_runtest_teardown(item):
    global _current
    _current = None


def pytest_sessionfinish(session, exitstatus):
    with open(os.environ["BLAST_TABLE_FILE"], "w", encoding="utf-8") as stream:
        json.dump({key: sorted(value) for key, value in _reads.items()}, stream, separators=(",", ":"))
