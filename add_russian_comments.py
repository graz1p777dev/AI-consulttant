"""Utility script to annotate Python files with Russian comments.

This script walks the project directory, finds all .py files (excluding __pycache__)
and inserts a Russian comment above every function and class definition if such a comment
is missing. The comment is generic and should be improved manually, but it provides
Russian context for each definition.

Запустить:
    python add_russian_comments.py

"""

import ast
from pathlib import Path

PREFIX = "# "


def annotate_file(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    tree = ast.parse(text)
    lines = text.splitlines()

    # collect insertion points
    inserts = []  # (lineno, comment text)

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            lineno = node.lineno - 1  # 0-index
            # check if previous non-empty line already contains a Russian comment
            if lineno > 0 and lines[lineno - 1].strip().startswith("#"):
                continue
            name = node.name
            kind = "класс" if isinstance(node, ast.ClassDef) else "функция"
            comment = f"# {kind} {name}: описание на русском"
            inserts.append((lineno, comment))

    # apply inserts in reverse order so line numbers stay valid
    for lineno, comment in reversed(inserts):
        lines.insert(lineno, comment)

    new_text = "\n".join(lines)
    if new_text != text:
        path.write_text(new_text, encoding="utf-8")
        print(f"Обновлен файл: {path}")


if __name__ == "__main__":
    root = Path(__file__).parent
    for p in root.rglob("*.py"):
        if "__pycache__" in p.parts:
            continue
        if p.name in {"add_russian_comments.py"}:
            continue
        annotate_file(p)
