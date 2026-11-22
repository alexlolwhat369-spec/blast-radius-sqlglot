"""Record pinned tests that read each dialect expression-metadata entry."""

from __future__ import annotations

import json
import os
import sys
from collections import defaultdict

import pytest

from tools.expression_plugin import ImmediateExecutor


_current = None
_reads = defaultdict(set)


def pytest_sessionstart(session):
    from sqlglot.optimizer.annotate_types import TypeAnnotator

    original = TypeAnnotator.__init__

    class TrackingMetadata(dict):
        def __init__(self, values, dialect):
            super().__init__(values)
            self.dialect = dialect

        def get(self, key, default=None):
            if _current and isinstance(key, type):
                _reads[f"{self.dialect}:{key.__name__}"].add(_current)
            return super().get(key, default)

    def traced_init(self, *args, **kwargs):
        original(self, *args, **kwargs)
        self.expression_metadata = TrackingMetadata(
            self.expression_metadata, type(self.dialect).__name__.lower()
        )

    TypeAnnotator.__init__ = traced_init


@pytest.hookimpl(tryfirst=True)
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
    with open(os.environ["BLAST_TYPING_FILE"], "w", encoding="utf-8") as stream:
        json.dump({key: sorted(value) for key, value in _reads.items()}, stream, separators=(",", ":"))
