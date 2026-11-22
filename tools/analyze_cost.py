"""List the largest public-sample contributors to selected test cost."""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

data = Path(sys.argv[1])
output = Path(sys.argv[2])
tests = json.loads((data / "tests.json").read_text(encoding="utf-8"))["tests"]
by_number = {test["number"]: test for test in tests}
contribution = defaultdict(float)
commits = defaultdict(list)
for line in output.read_text(encoding="utf-8").splitlines():
    record = json.loads(line)
    for worker in record["workers"]:
        for number in worker:
            test = by_number[number]
            contribution[test["id"]] += test["seconds"]
            commits[test["id"]].append(record["commit"])
for test_id, seconds in sorted(contribution.items(), key=lambda pair: -pair[1])[:30]:
    print(f"{seconds:8.3f} {len(commits[test_id]):2d} {test_id} {','.join(commits[test_id])}")
