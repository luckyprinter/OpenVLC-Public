"""Verify the Academy repository index against an OpenVLC-Public Git checkout."""

import argparse
import ast
import json
from pathlib import Path
import subprocess


SOURCE_PIN = "411f183a8592d8285118f613bb4909c5bbd9d3cc"
INDEX = Path(__file__).resolve().parents[1] / "src/data/repo-index.json"
PYTHON_DEFINITIONS = (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)


def git(repository, *args):
    return subprocess.check_output(["git", "-C", str(repository), *args])


def verify(repository, update):
    entries = json.loads(INDEX.read_text(encoding="utf-8"))
    entries_by_path = {entry["path"]: entry for entry in entries}
    if len(entries_by_path) != len(entries):
        raise SystemExit("Repository index contains duplicate paths")

    tree = {}
    for record in git(repository, "ls-tree", "-rz", SOURCE_PIN).split(b"\0"):
        if record:
            metadata, path = record.split(b"\t", 1)
            tree[path.decode()] = metadata.split()[2].decode()
    if tree.keys() != entries_by_path.keys():
        unexpected = tree.keys() ^ entries_by_path.keys()
        raise SystemExit(f"Repository index path mismatch: {sorted(unexpected)}")

    for entry in entries:
        path = entry["path"]
        blob = tree[path]
        if entry["blob"] != blob:
            raise SystemExit(f"Repository index blob mismatch: {path}")
        if entry["bytes"] != int(git(repository, "cat-file", "-s", blob)):
            raise SystemExit(f"Repository index size mismatch: {path}")
        if entry["lineCount"] is None:
            continue

        raw = git(repository, "cat-file", "blob", blob)
        line_count = len(raw.splitlines())
        definitions = {}
        if entry["kind"] == "python":
            definitions = {
                (node.lineno, node.name): node.end_lineno
                for node in ast.walk(ast.parse(raw))
                if isinstance(node, PYTHON_DEFINITIONS)
            }

        if update:
            entry["lineCount"] = line_count
        elif entry["lineCount"] != line_count:
            raise SystemExit(f"Repository index line count mismatch: {path}")

        for symbol in entry["symbols"]:
            start = symbol["line"]
            end = definitions.get((start, symbol["name"]), min(symbol["endLine"], line_count))
            if update:
                symbol["endLine"] = end
            elif symbol["endLine"] != end:
                raise SystemExit(f"Index symbol end mismatch: {path}:{start}")
            if not 1 <= start <= end <= line_count:
                raise SystemExit(f"Index symbol range outside file: {path}:{start}")

        for heading in entry["headings"]:
            if not 1 <= heading["line"] <= line_count:
                raise SystemExit(f"Index heading outside file: {path}:{heading['line']}")

    if update:
        INDEX.write_text(json.dumps(entries, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Verified {len(entries)} files against {SOURCE_PIN}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repository", type=Path, help="OpenVLC-Public checkout with the pinned commit")
    parser.add_argument("--write", action="store_true", help="Refresh source line counts and Python symbol ranges")
    args = parser.parse_args()
    verify(args.repository, args.write)
