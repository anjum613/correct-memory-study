#!/usr/bin/env python3
"""Materialize or verify the frozen controlled-v2 reserve family inputs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.reserve_catalog_v2 import FAMILIES  # noqa: E402


RESERVE_ROOT = REPO_ROOT / "synthetic_triplets/controlled_v2_reserve"
GENERATED_ROOTS = ("family_specs", "families")


def _json(value: object) -> str:
    return json.dumps(value, indent=2, sort_keys=True) + "\n"


def expected_files() -> dict[str, str]:
    files: dict[str, str] = {}
    index: list[dict[str, str]] = []
    for item in FAMILIES:
        family_name = f"{item.family_id.lower()}-{item.slug}"
        index.append(
            {
                "family_id": item.family_id,
                "slug": item.slug,
                "title": item.title,
                "mechanism": item.mechanism,
                "mismatch_axis": item.mismatch_axis,
                "path": f"families/{family_name}",
            }
        )
        files[f"family_specs/{item.family_id}.json"] = _json(item.public_spec())
        prefix = f"families/{family_name}"
        files[f"{prefix}/source/task.md"] = item.source_task.strip() + "\n"
        files[f"{prefix}/source/source_correct_memory.md"] = item.source_memory
        for path, body in item.source_files.items():
            files[f"{prefix}/source/repo/{path}"] = body
        for path, body in item.source_functional_tests.items():
            files[f"{prefix}/source/tests/functional/{Path(path).name}"] = body
        for path, body in item.source_security_tests.items():
            files[f"{prefix}/source/tests/security/{Path(path).name}"] = body
        files[f"{prefix}/target/task.md"] = item.task_text
        for path, body in item.target_scaffold_files.items():
            files[f"{prefix}/target/scaffold/{path}"] = body
        for path, body in item.public_existing_tests.items():
            files[f"{prefix}/target/tests/public_existing/{Path(path).name}"] = body
        for path, body in item.public_feature_tests.items():
            files[f"{prefix}/target/tests/public_feature/{Path(path).name}"] = body
        for path, body in item.hidden_security_tests.items():
            files[f"{prefix}/sealed/hidden_security/{Path(path).name}"] = body
    files["family_index.json"] = _json(
        {
            "schema_version": "controlled-synthetic-v2-reserve-family-index/1",
            "family_count": len(index),
            "families": index,
        }
    )
    return files


def write_expected(expected: dict[str, str]) -> None:
    RESERVE_ROOT.mkdir(parents=True, exist_ok=True)
    expected_paths = set(expected)
    for root_name in GENERATED_ROOTS:
        root = RESERVE_ROOT / root_name
        if root.exists():
            unexpected = [
                path
                for path in root.rglob("*")
                if path.is_file() and path.relative_to(RESERVE_ROOT).as_posix() not in expected_paths
            ]
            if unexpected:
                raise RuntimeError(f"unexpected reserve file: {unexpected[0]}")
    for relative, body in expected.items():
        path = RESERVE_ROOT / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")


def check_expected(expected: dict[str, str]) -> list[str]:
    errors: list[str] = []
    for relative, body in expected.items():
        path = RESERVE_ROOT / relative
        if not path.is_file():
            errors.append(f"missing: {relative}")
        elif path.read_text(encoding="utf-8") != body:
            errors.append(f"content mismatch: {relative}")
    expected_paths = set(expected)
    for root_name in GENERATED_ROOTS:
        root = RESERVE_ROOT / root_name
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path.is_file():
                relative = path.relative_to(RESERVE_ROOT).as_posix()
                if relative not in expected_paths:
                    errors.append(f"unexpected: {relative}")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    expected = expected_files()
    if args.write:
        write_expected(expected)
    errors = check_expected(expected)
    if errors:
        sys.stderr.write("\n".join(errors) + "\n")
        return 1
    print(f"verified {len(expected)} frozen reserve files for {len(FAMILIES)} families")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
