"""Local diagnostics only. Never imported by the submission selector."""

from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import time
from pathlib import Path


def schedule_cost(numbers: set[int], durations: dict[int, int]) -> int:
    from scheduler import split

    workers = split(numbers, durations)
    return max((sum(durations[number] for number in worker) for worker in workers), default=0) + 2000 * len(workers)


def main() -> None:
    data = Path(sys.argv[1]).resolve()
    os.environ["BLAST_DATA"] = str(data)
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    import selector

    stream = io.StringIO()
    start = time.process_time()
    with contextlib.redirect_stdout(stream):
        selector.main()
    cpu_seconds = time.process_time() - start
    predictions = {
        row["commit"]: {number for worker in row["workers"] for number in worker}
        for row in map(json.loads, stream.getvalue().splitlines())
    }
    answers = json.loads((data / "answers.json").read_text(encoding="utf-8"))["commits"]
    tests = json.loads((data / "tests.json").read_text(encoding="utf-8"))["tests"]
    durations = {test["number"]: round(test["seconds"] * 1000) for test in tests}
    total = misses = oracle = 0
    print("commit  selected  failing  missed  cost_s  oracle_s  excess_s")
    for commit, answer in sorted(answers.items()):
        selected = predictions[commit]
        failing = set(answer["failing"])
        missed = failing - selected
        cost = schedule_cost(selected, durations)
        ideal = schedule_cost(failing, durations)
        total += cost + 300000 * bool(missed)
        oracle += ideal
        misses += bool(missed)
        print(f"{commit:6} {len(selected):8} {len(failing):8} {len(missed):7} {cost/1000:7.3f} {ideal/1000:9.3f} {(cost-ideal)/1000:8.3f}")
    print(f"simulated={total/1000:.3f}s cpu={cpu_seconds:.3f}s total={total/1000+cpu_seconds:.3f}s misses={misses} oracle={oracle/1000:.3f}s")
    for commit, answer in sorted(answers.items()):
        missing = set(answer["failing"]) - predictions[commit]
        if missing:
            print(f"MISSED {commit}: {', '.join(tests[number]['id'] for number in sorted(missing))}")


if __name__ == "__main__":
    main()
