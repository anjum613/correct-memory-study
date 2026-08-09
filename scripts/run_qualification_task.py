#!/usr/bin/env python3
"""Run exactly one frozen qualification task against an already-ready vLLM server."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cmpilot.qualification_runner import (  # noqa: E402
    QualificationRunConfig,
    run_qualification_task,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--suite-manifest", type=Path, required=True)
    parser.add_argument("--task-manifest", type=Path, required=True)
    parser.add_argument("--freeze-manifest", type=Path, required=True)
    parser.add_argument("--artifact-directory", type=Path, required=True)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--mini-python", required=True)
    parser.add_argument("--tokenizer-path")
    parser.add_argument("--seed", type=int)
    parser.add_argument("--suite-reference", type=Path)
    parser.add_argument("--agent-timeout", type=int, default=600)
    parser.add_argument("--server-pid", type=int)
    parser.add_argument("--runtime-integrity", type=Path)
    arguments = parser.parse_args()
    return run_qualification_task(
        QualificationRunConfig(
            project_root=arguments.project_root,
            suite_manifest=arguments.suite_manifest,
            task_manifest=arguments.task_manifest,
            freeze_manifest=arguments.freeze_manifest,
            artifact_directory=arguments.artifact_directory,
            base_url=arguments.base_url,
            model=arguments.model,
            mini_python=arguments.mini_python,
            tokenizer_path=arguments.tokenizer_path,
            seed=arguments.seed,
            suite_reference=arguments.suite_reference,
            agent_timeout=arguments.agent_timeout,
            server_pid=arguments.server_pid,
            runtime_integrity=arguments.runtime_integrity,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
