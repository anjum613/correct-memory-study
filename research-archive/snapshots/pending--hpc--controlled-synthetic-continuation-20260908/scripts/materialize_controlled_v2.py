#!/usr/bin/env python3
"""Materialize or verify the frozen controlled synthetic v2 research inputs."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.controlled_v2_catalog import FAMILIES


COHORT_ROOT = REPO_ROOT / "synthetic_triplets/controlled_v2"
GENERATED_ROOTS = (
    "family_specs",
    "families",
)


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
            "schema_version": "controlled-synthetic-v2-family-index/1",
            "family_count": len(index),
            "families": index,
        }
    )
    return files


def _write(expected: dict[str, str]) -> None:
    COHORT_ROOT.mkdir(parents=True, exist_ok=True)
    expected_paths = set(expected)
    for root_name in GENERATED_ROOTS:
        root = COHORT_ROOT / root_name
        if root.exists():
            unexpected = [
                path
                for path in root.rglob("*")
                if path.is_file() and path.relative_to(COHORT_ROOT).as_posix() not in expected_paths
            ]
            if unexpected:
                rendered = ", ".join(str(path) for path in unexpected[:5])
                raise RuntimeError(f"refusing to overwrite tree with unexpected files: {rendered}")
    for relative, body in expected.items():
        path = COHORT_ROOT / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")


def _check(expected: dict[str, str]) -> list[str]:
    errors: list[str] = []
    for relative, body in expected.items():
        path = COHORT_ROOT / relative
        if not path.is_file():
            errors.append(f"missing: {relative}")
        elif path.read_text(encoding="utf-8") != body:
            errors.append(f"content mismatch: {relative}")
    expected_paths = set(expected)
    for root_name in GENERATED_ROOTS:
        root = COHORT_ROOT / root_name
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path.is_file():
                relative = path.relative_to(COHORT_ROOT).as_posix()
                if relative not in expected_paths:
                    errors.append(f"unexpected: {relative}")
    return errors


def hash_inventory(paths: list[Path]) -> dict[str, str]:
    inventory: dict[str, str] = {}
    for path in sorted(paths):
        if path.is_file():
            relative = path.relative_to(REPO_ROOT).as_posix()
            inventory[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    return inventory


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    expected = expected_files()
    if args.write:
        _write(expected)
    errors = _check(expected)
    if errors:
        sys.stderr.write("\n".join(errors) + "\n")
        return 1
    print(f"verified {len(expected)} frozen files for {len(FAMILIES)} families")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
