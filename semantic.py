"""Prove a small set of source edits equivalent for values in the pinned tree."""

from __future__ import annotations

import ast
import copy
import re


def _if_test(line: str) -> ast.AST | None:
    stripped = line.strip()
    if not stripped.startswith("if "):
        return None
    try:
        if stripped.endswith(":"):
            node = ast.parse(stripped + "\n    pass").body[0]
            return node.test if isinstance(node, ast.If) else None
        expression = ast.parse("0 " + stripped + " else 1", mode="eval").body
        return expression.test if isinstance(expression, ast.IfExp) else None
    except SyntaxError:
        return None


def _subject_attr(node: ast.AST) -> str | None:
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "self":
        return node.attr
    return None


def _matching_fact(path: str, line: int, index: dict) -> dict | None:
    facts = [fact for fact in index.get(path, []) if fact["start"] <= line <= fact["end"]]
    return min(facts, key=lambda fact: fact["end"] - fact["start"], default=None)


def _call_name(function: ast.AST) -> str | None:
    if isinstance(function, ast.Name):
        return function.id
    if isinstance(function, ast.Attribute):
        return function.attr
    return None


def _copy_of_fresh_expression(old_line: str, new_line: str, semantic_index: dict) -> bool:
    try:
        old = ast.parse(old_line.strip()).body[0]
        new = ast.parse(new_line.strip()).body[0]
    except SyntaxError:
        return False
    old_call = old.value if isinstance(old, (ast.Assign, ast.AnnAssign, ast.Expr)) else None
    new_call = new.value if isinstance(new, (ast.Assign, ast.AnnAssign, ast.Expr)) else None
    if not isinstance(old_call, ast.Call) or not isinstance(new_call, ast.Call) or not old_call.args:
        return False
    if _call_name(old_call.func) not in semantic_index.get("copy_passthrough", []):
        return False
    if not isinstance(old_call.args[0], ast.Call) or _call_name(old_call.args[0].func) not in semantic_index.get("fresh_factories", []):
        return False
    old_copy = next((kw for kw in old_call.keywords if kw.arg == "copy"), None)
    new_copy = next((kw for kw in new_call.keywords if kw.arg == "copy"), None)
    if not old_copy or not new_copy or not isinstance(old_copy.value, ast.Constant) or not isinstance(new_copy.value, ast.Constant):
        return False
    if not isinstance(old_copy.value.value, bool) or not isinstance(new_copy.value.value, bool) or old_copy.value.value == new_copy.value.value:
        return False
    normalized = copy.deepcopy(old)
    normalized_call = normalized.value
    next(kw for kw in normalized_call.keywords if kw.arg == "copy").value = copy.deepcopy(new_copy.value)
    return ast.dump(normalized, include_attributes=False) == ast.dump(new, include_attributes=False)


def changed_mapping_values(old_line: str, new_line: str) -> set[str] | None:
    """Return keys whose values changed when a nonempty literal mapping keeps its keys."""
    try:
        old = ast.parse(old_line.strip()).body[0]
        new = ast.parse(new_line.strip()).body[0]
    except SyntaxError:
        return None
    if not isinstance(old, ast.Assign) or not isinstance(new, ast.Assign) or not isinstance(old.value, ast.Dict) or not isinstance(new.value, ast.Dict):
        return None
    if ast.dump(old.targets[0]) != ast.dump(new.targets[0]):
        return None
    def entries(node: ast.Dict) -> dict[str, str] | None:
        result = {}
        for key, value in zip(node.keys, node.values):
            if not isinstance(key, ast.Constant) or not isinstance(key.value, str):
                return None
            result[key.value] = ast.dump(value, include_attributes=False)
        return result
    old_entries, new_entries = entries(old.value), entries(new.value)
    if not old_entries or not new_entries or old_entries.keys() != new_entries.keys():
        return None
    return {key for key in old_entries if old_entries[key] != new_entries[key]}


def mapping_key_stable(old_line: str, new_line: str) -> bool:
    """Reject precision based on a pinned key when the patch changes that key."""
    old_match = re.match(r"\s*(['\"])(.*?)\1\s*:", old_line)
    new_match = re.match(r"\s*(['\"])(.*?)\1\s*:", new_line)
    if old_match or new_match:
        return bool(old_match and new_match and old_match.group(2) == new_match.group(2))
    try:
        old = ast.parse(old_line.strip()).body[0]
        new = ast.parse(new_line.strip()).body[0]
    except SyntaxError:
        return True
    if isinstance(old, ast.Assign) and isinstance(old.value, ast.Dict):
        return changed_mapping_values(old_line, new_line) is not None
    return True


def proven_equivalent(change, semantic_index: dict) -> bool:
    if len(change.removed) != 1 or len(change.added) != 1 or len(change.old_lines) != 1:
        return False
    if _copy_of_fresh_expression(change.removed[0], change.added[0], semantic_index):
        return True
    old = _if_test(change.removed[0])
    new = _if_test(change.added[0])
    if old is None or new is None:
        return False
    old_compares = [node for node in ast.walk(old) if isinstance(node, ast.Compare)]
    new_compares = [node for node in ast.walk(new) if isinstance(node, ast.Compare)]
    if len(old_compares) != 1 or len(new_compares) != 1:
        return False
    old_cmp, new_cmp = old_compares[0], new_compares[0]
    if len(old_cmp.ops) != 1 or len(new_cmp.ops) != 1:
        return False
    operator_pair = (type(old_cmp.ops[0]), type(new_cmp.ops[0]))
    identity_pairs = {(ast.Is, ast.Eq), (ast.Eq, ast.Is), (ast.IsNot, ast.NotEq), (ast.NotEq, ast.IsNot)}
    if operator_pair not in identity_pairs:
        return False
    normalized = copy.deepcopy(old)
    normalized_compare = next(node for node in ast.walk(normalized) if isinstance(node, ast.Compare))
    normalized_compare.ops[0] = type(new_cmp.ops[0])()
    if ast.dump(normalized, include_attributes=False) != ast.dump(new, include_attributes=False):
        return False
    left, right = old_cmp.left, old_cmp.comparators[0]
    fact = _matching_fact(change.path, next(iter(change.old_lines)), semantic_index)
    if fact is None:
        return False
    attr = _subject_attr(left)
    if attr is None:
        attr = _subject_attr(right)
        left, right = right, left
    if attr is None:
        return False
    if isinstance(right, ast.Constant) and right.value is None:
        return attr in fact["none_safe_attrs"]
    if isinstance(right, ast.Attribute) and isinstance(right.value, ast.Name):
        return fact["enum_attrs"].get(attr) == right.value.id
    return False
