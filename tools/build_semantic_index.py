"""Derive conservative identity-equality facts from the pinned source tree."""

from __future__ import annotations

import ast
import json
import sys
from collections import defaultdict
from pathlib import Path


def names(node: ast.AST) -> set[str]:
    return {part.id for part in ast.walk(node) if isinstance(part, ast.Name)}


def annotation_class(node: ast.AST) -> str | None:
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        parts = [node.left, node.right]
        non_none = [part.id for part in parts if isinstance(part, ast.Name) and part.id != "None"]
        if len(non_none) == 1 and any(isinstance(part, ast.Constant) and part.value is None or isinstance(part, ast.Name) and part.id == "None" for part in parts):
            return non_none[0]
    return None


def main() -> None:
    source_root, output_file = map(Path, sys.argv[1:3])
    parsed = {}
    classes = []
    for source in (source_root / "sqlglot").rglob("*.py"):
        relative = source.relative_to(source_root).as_posix()
        tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        imports = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                for alias in node.names:
                    imports[alias.asname or alias.name] = f"{node.module.replace('.', '/')}.py::{alias.name}"
        parsed[relative] = (tree, imports)
        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                classes.append((relative, node))

    enum_names = {"Enum", "IntEnum", "StrEnum"}
    while True:
        new = {
            node.name for _, node in classes
            if any(names(base) & enum_names for base in node.bases)
        }
        if new <= enum_names:
            break
        enum_names.update(new)

    simple_classes = {
        f"{path}::{node.name}"
        for path, node in classes
        if not node.bases and not any(isinstance(part, ast.FunctionDef) and part.name == "__eq__" for part in node.body)
    }

    constant_types = defaultdict(set)
    for _, node in classes:
        for part in node.body:
            if isinstance(part, ast.Assign) and isinstance(part.value, ast.Attribute) and isinstance(part.value.value, ast.Name):
                enum_type = part.value.value.id
                if enum_type in enum_names:
                    for target in part.targets:
                        if isinstance(target, ast.Name):
                            constant_types[target.id].add(enum_type)
    unambiguous_constants = {
        name: next(iter(types)) for name, types in constant_types.items() if len(types) == 1
    }

    fresh_factories = set()
    copy_passthrough = set()
    for path, (tree, _) in parsed.items():
        if not path.startswith("sqlglot/expressions/"):
            continue
        for function in (node for node in tree.body if isinstance(node, ast.FunctionDef)):
            returns = [node for node in ast.walk(function) if isinstance(node, ast.Return)]
            if len(returns) == 1 and isinstance(returns[0].value, ast.Call) and isinstance(returns[0].value.func, ast.Name) and returns[0].value.func.id[:1].isupper():
                fresh_factories.add(function.name)
            if "copy" in [arg.arg for arg in function.args.args + function.args.kwonlyargs]:
                uses = [node for node in ast.walk(function) if isinstance(node, ast.Name) and node.id == "copy" and isinstance(node.ctx, ast.Load)]
                forwarding = [
                    keyword for call in ast.walk(function) if isinstance(call, ast.Call) and isinstance(call.func, ast.Name) and call.func.id == "maybe_parse"
                    for keyword in call.keywords if keyword.arg == "copy" and isinstance(keyword.value, ast.Name) and keyword.value.id == "copy"
                ]
                if len(uses) == len(forwarding) == 1:
                    copy_passthrough.add(function.name)

    result = {}
    fixed_tuple_lengths = {}
    for path, klass in classes:
        _, imports = parsed[path]
        enum_values = defaultdict(list)
        none_safe = set()
        for part in ast.walk(klass):
            if isinstance(part, ast.FunctionDef):
                padded_names = set()
                for call in (node for node in ast.walk(part) if isinstance(node, ast.Call)):
                    if not isinstance(call.func, ast.Attribute) or call.func.attr != "extend" or not isinstance(call.func.value, ast.Name) or not call.args:
                        continue
                    factor = call.args[0]
                    if isinstance(factor, ast.BinOp) and isinstance(factor.op, ast.Mult) and isinstance(factor.right, ast.BinOp) and isinstance(factor.right.op, ast.Sub) and isinstance(factor.right.left, ast.Constant) and isinstance(factor.right.right, ast.Call) and isinstance(factor.right.right.func, ast.Name) and factor.right.right.func.id == "len" and factor.right.right.args and isinstance(factor.right.right.args[0], ast.Name) and factor.right.right.args[0].id == call.func.value.id:
                        padded_names.add((call.func.value.id, factor.right.left.value))
                for assignment in (node for node in ast.walk(part) if isinstance(node, ast.Assign)):
                    if len(assignment.targets) != 1 or not isinstance(assignment.targets[0], ast.Attribute) or not isinstance(assignment.targets[0].value, ast.Name) or assignment.targets[0].value.id != "self":
                        continue
                    value = assignment.value
                    if not isinstance(value, ast.Call) or not isinstance(value.func, ast.Name) or value.func.id != "tuple" or len(value.args) != 1 or not isinstance(value.args[0], ast.GeneratorExp):
                        continue
                    generator = value.args[0].generators[0]
                    sequence = generator.iter
                    if isinstance(sequence, ast.Subscript) and isinstance(sequence.value, ast.Name) and isinstance(sequence.slice, ast.Slice) and isinstance(sequence.slice.upper, ast.Constant):
                        length = sequence.slice.upper.value
                        if (sequence.value.id, length) in padded_names:
                            fixed_tuple_lengths[assignment.targets[0].attr] = length
            if isinstance(part, ast.AnnAssign) and isinstance(part.target, ast.Attribute) and isinstance(part.target.value, ast.Name) and part.target.value.id == "self":
                class_name = annotation_class(part.annotation)
                if class_name:
                    resolved = imports.get(class_name, f"{path}::{class_name}")
                    if resolved in simple_classes:
                        none_safe.add(part.target.attr)
            if not isinstance(part, (ast.Assign, ast.AnnAssign)):
                continue
            targets = part.targets if isinstance(part, ast.Assign) else [part.target]
            value = part.value
            for target in targets:
                if not isinstance(target, ast.Attribute) or not isinstance(target.value, ast.Name) or target.value.id != "self":
                    continue
                inferred = None
                if isinstance(value, ast.Call) and isinstance(value.func, ast.Name) and value.func.id in enum_names:
                    inferred = value.func.id
                elif isinstance(value, ast.Attribute) and isinstance(value.value, ast.Name):
                    if value.value.id in enum_names:
                        inferred = value.value.id
                    elif value.value.id == "self":
                        inferred = unambiguous_constants.get(value.attr)
                elif isinstance(value, ast.Constant) and value.value is None:
                    inferred = "None"
                enum_values[target.attr].append(inferred)
        enum_attrs = {
            name: next(iter(types - {"None"}))
            for name, values in enum_values.items()
            if (types := set(values)) and None not in types and len(types - {"None"}) == 1
        }
        if enum_attrs or none_safe:
            result.setdefault(path, []).append({
                "class": klass.name,
                "start": klass.lineno,
                "end": klass.end_lineno,
                "enum_attrs": enum_attrs,
                "none_safe_attrs": sorted(none_safe),
            })
    result["fixed_tuple_lengths"] = fixed_tuple_lengths
    result["fresh_factories"] = sorted(fresh_factories)
    result["copy_passthrough"] = sorted(copy_passthrough)
    output_file.write_text(json.dumps(result, separators=(",", ":"), sort_keys=True), encoding="utf-8")
    print(f"semantic classes={sum(map(len, result.values()))} bytes={output_file.stat().st_size}")


if __name__ == "__main__":
    main()
