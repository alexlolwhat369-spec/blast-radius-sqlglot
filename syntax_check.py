"""Check whether an independent patch makes pinned Python source unimportable."""

from __future__ import annotations

import re


HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def patched_source(patch: str, path: str, original: str) -> str | None:
    source = original.splitlines()
    output = []
    position = 0
    active = False
    in_hunk = False
    saw_hunk = False
    for line in patch.splitlines():
        if line.startswith("diff --git "):
            if active:
                break
            match = re.match(r"diff --git a/(.+?) b/(.+)$", line)
            active = bool(match and match.group(2) == path)
            in_hunk = False
            continue
        if not active:
            continue
        hunk = HUNK.match(line)
        if hunk:
            start = int(hunk.group(1))
            old_count = int(hunk.group(2)) if hunk.group(2) is not None else 1
            hunk_position = start if old_count == 0 else start - 1
            if hunk_position < position or hunk_position > len(source):
                return None
            output.extend(source[position:hunk_position])
            position = hunk_position
            in_hunk = True
            saw_hunk = True
            continue
        if not in_hunk:
            continue
        if line.startswith("\\"):
            continue
        if not line or line[0] not in " +-":
            in_hunk = False
            continue
        content = line[1:]
        if line[0] in " -":
            if position >= len(source) or source[position] != content:
                return None
            position += 1
        if line[0] in " +":
            output.append(content)
    if not active and not saw_hunk:
        return original
    if not saw_hunk:
        return None
    output.extend(source[position:])
    return "\n".join(output) + ("\n" if original.endswith("\n") else "")


def has_compile_error(patch: str, source_index: dict[str, str]) -> bool:
    paths = {
        match.group(1)
        for line in patch.splitlines()
        if (match := re.match(r"diff --git a/.+? b/(sqlglot/.+\.py)$", line))
    }
    for path in paths:
        original = source_index.get(path)
        if original is None:
            continue
        result = patched_source(patch, path, original)
        if result is None:
            return True
        try:
            compile(result, path, "exec", dont_inherit=True)
        except (SyntaxError, ValueError):
            return True
    return False
