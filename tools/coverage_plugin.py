"""Collect per-test coverage from the pinned sqlglot checkout (offline build tool)."""

from __future__ import annotations

import os
import sys
from concurrent.futures import Future

import coverage
import pytest


_coverage = None


class ImmediateExecutor:
    """Run optimizer fixture tasks in process so their source lines are traced."""

    def __init__(self, **kwargs):
        initializer = kwargs.get("initializer")
        if initializer is not None:
            initializer(*kwargs.get("initargs", ()))

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.shutdown()

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
    global _coverage
    _coverage = coverage.Coverage(
        data_file=os.environ.get("BLAST_COVERAGE_FILE", ".coverage.blast"),
        source=["sqlglot"],
        branch=False,
        concurrency=["thread"],
    )
    _coverage.start()


@pytest.hookimpl(tryfirst=True)
def pytest_runtest_setup(item):
    _coverage.switch_context(item.nodeid)


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
    _coverage.stop()
    _coverage.save()
