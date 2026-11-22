"""Record expression classes instantiated by each pinned test (offline only)."""

from __future__ import annotations

import json
import os
import sys
from collections import defaultdict
from concurrent.futures import Future


_current = None
_uses = defaultdict(set)
_original_init = None


class ImmediateExecutor:
    def __init__(self, **kwargs):
        initializer = kwargs.get("initializer")
        if initializer is not None:
            initializer(*kwargs.get("initargs", ()))

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def submit(self, function, *args, **kwargs):
        future = Future()
        try:
            future.set_result(function(*args, **kwargs))
        except BaseException as error:
            future.set_exception(error)
        return future

    def shutdown(self, **kwargs):
        pass


def pytest_sessionstart(session):
    global _original_init
    from sqlglot.expressions.core import Expr

    _original_init = Expr.__init__

    def traced_init(self, **args):
        if _current:
            for klass in type(self).__mro__:
                if klass.__module__.startswith("sqlglot.expressions"):
                    _uses[f"{klass.__module__}:{klass.__name__}"].add(_current)
        _original_init(self, **args)

    Expr.__init__ = traced_init


def pytest_runtest_setup(item):
    global _current
    _current = item.nodeid


def pytest_runtest_teardown(item):
    global _current
    _current = None


def pytest_collection_modifyitems(items):
    if os.environ.get("BLAST_IN_PROCESS_OPTIMIZER") == "1":
        module = sys.modules.get("tests.test_optimizer")
        if module is not None:
            module.ProcessPoolExecutor = ImmediateExecutor
    if os.environ.get("BLAST_IN_PROCESS_EXECUTOR") == "1":
        module = sys.modules.get("tests.test_executor")
        if module is not None:
            module.ProcessPoolExecutor = ImmediateExecutor


def pytest_sessionfinish(session, exitstatus):
    path = os.environ["BLAST_EXPRESSION_FILE"]
    with open(path, "w", encoding="utf-8") as stream:
        json.dump({key: sorted(values) for key, values in _uses.items()}, stream, separators=(",", ":"))
