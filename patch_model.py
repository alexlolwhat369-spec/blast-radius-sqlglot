"""Parse the parts of a unified diff needed for test impact analysis."""

from __future__ import annotations

import re
from dataclasses import dataclass, field


HUNK = re.compile(r"^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@")


@dataclass
class FileChange:
    path: str
    old_lines: set[int] = field(default_factory=set)
    anchors: set[int] = field(default_factory=set)
    removed: list[str] = field(default_factory=list)
    added: list[str] = field(default_factory=list)

    @property
    def comment_only(self) -> bool:
        changed = self.removed + self.added
        return bool(changed) and all(
            not line.strip() or line.lstrip().startswith("#") for line in changed
        )


def parse_patch(patch: str) -> list[FileChange]:
    changes: list[FileChange] = []
    current: FileChange | None = None
    old_line = new_line = 0
    deletion_start: int | None = None
    in_hunk = False
    for line in patch.splitlines():
        if line.startswith("diff --git "):
            match = re.match(r"diff --git a/(.+?) b/(.+)$", line)
            if match:
                current = FileChange(match.group(2))
                changes.append(current)
            in_hunk = False
            deletion_start = None
            continue
        match = HUNK.match(line)
        if match:
            old_line, new_line = map(int, match.groups())
            in_hunk = True
            deletion_start = None
            continue
        if not in_hunk or current is None:
            continue
        if line.startswith("-"):
            if deletion_start is None:
                deletion_start = old_line
            current.old_lines.add(old_line)
            current.removed.append(line[1:])
            old_line += 1
        elif line.startswith("+"):
            current.anchors.add(deletion_start if deletion_start is not None else old_line)
            current.added.append(line[1:])
            new_line += 1
        elif line.startswith(" "):
            deletion_start = None
            old_line += 1
            new_line += 1
        elif line.startswith("\\"):
            continue
        else:
            in_hunk = False
            deletion_start = None
    return changes
