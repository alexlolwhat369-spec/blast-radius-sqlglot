"""Minimize the scorer's measured worker cost for a set of tests."""

from __future__ import annotations

import heapq
import math


def split(test_numbers: set[int], milliseconds: dict[int, int]) -> list[list[int]]:
    if not test_numbers:
        return []
    ordered = sorted(test_numbers, key=lambda number: (-milliseconds[number], number))
    best_workers: list[list[int]] | None = None
    best_cost = math.inf
    for worker_count in range(1, min(8, len(ordered)) + 1):
        workers = [[] for _ in range(worker_count)]
        heap = [(0, index) for index in range(worker_count)]
        heapq.heapify(heap)
        for number in ordered:
            load, index = heapq.heappop(heap)
            workers[index].append(number)
            heapq.heappush(heap, (load + milliseconds[number], index))
        cost = max(load for load, _ in heap) + 2000 * worker_count
        if cost < best_cost:
            best_cost = cost
            best_workers = workers
    return best_workers or []
