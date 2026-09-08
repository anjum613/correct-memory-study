#!/usr/bin/env python3
"""Write smoke PASS evidence and the pre-outcome Qwen3.6 qualification freeze."""

from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cmpilot.qwen36_qualification import (  # noqa: E402
    QUALIFICATION_FREEZE,
    SMOKE_ARTIFACT,
    SMOKE_RESULT,
    build_freeze_manifest,
    build_smoke_result,
    validate_freeze_manifest,
    write_canonical_json,
)
from cmpilot.qwen36_candidate import sha256_file  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=ROOT)
    parser.add_argument("--smoke-artifact", type=Path, default=SMOKE_ARTIFACT)
    parser.add_argument("--created-at-utc", required=True)
    parser.add_argument("--infrastructure-commit", required=True)
    arguments = parser.parse_args()
    project = arguments.project_root.resolve(strict=True)
    smoke_path = project / SMOKE_RESULT
    freeze_path = project / QUALIFICATION_FREEZE
    if smoke_path.exists() or freeze_path.exists():
        raise FileExistsError("Qwen3.6 qualification freeze outputs already exist")
    current = subprocess.run(
        ("git", "-C", str(project), "rev-parse", "HEAD"),
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    ).stdout.strip()
    status = subprocess.run(
        ("git", "-C", str(project), "status", "--porcelain"),
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    ).stdout
    if current != arguments.infrastructure_commit:
        raise RuntimeError("infrastructure commit is not current HEAD")
    if status:
        raise RuntimeError("worktree must be clean before emitting the freeze")
    write_canonical_json(smoke_path, build_smoke_result(arguments.smoke_artifact))
    write_canonical_json(
        freeze_path,
        build_freeze_manifest(
            project,
            qualification_infrastructure_commit=arguments.infrastructure_commit,
            created_at_utc=arguments.created_at_utc,
        ),
    )
    validation = validate_freeze_manifest(project, freeze_path)
    print(f"smoke_result={smoke_path} sha256={sha256_file(smoke_path)}")
    print(f"qualification_freeze={freeze_path} sha256={validation['sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
