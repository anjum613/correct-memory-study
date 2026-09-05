#!/usr/bin/env python3
"""Preflight, canary, or run the Qwen3-Coder FP8 final-13 model arm."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from typing import Sequence


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cmpilot.qwen3_final13 import (  # noqa: E402
    RunConfig,
    SERVED_MODEL_NAME,
    preflight,
    qwen3_cells,
    run_batch,
    run_canary,
    run_cell,
)


DEFAULT_MINI_PYTHON = "/home/s224049759/environments/mini-swe-agent-smoke/bin/python"
DEFAULT_TOKENIZER = (
    "/home/s224049759/model-cache/qwen3-coder-30b-a3b-instruct-fp8/"
    "e8ab3f2db9e388999a004eea5a31c16a8b517bc0"
)
DEFAULT_V3_DEPENDENCIES = (
    "/home/s224049759/environments/qwen36-vllm-v1/lib/python3.12/site-packages"
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=("list", "preflight", "canary", "cell", "batch"),
    )
    parser.add_argument(
        "--base-url",
        default=os.environ.get("VLLM_BASE_URL", "http://127.0.0.1:18000/v1"),
    )
    parser.add_argument(
        "--mini-python",
        default=os.environ.get("MINI_SWE_PYTHON", DEFAULT_MINI_PYTHON),
    )
    parser.add_argument(
        "--tokenizer-path",
        type=Path,
        default=Path(os.environ.get("QWEN3_TOKENIZER_PATH", DEFAULT_TOKENIZER)),
    )
    parser.add_argument(
        "--run-root",
        type=Path,
        default=Path(os.environ.get("CMPILOT_RUNS_ROOT", "qwen3-final13-runs")),
    )
    parser.add_argument(
        "--v3-dependency-path",
        type=Path,
        default=Path(
            os.environ.get("QWEN3_V3_DEPENDENCY_PATH", DEFAULT_V3_DEPENDENCIES)
        ),
    )
    parser.add_argument("--agent-timeout", type=int, default=600)
    parser.add_argument("--index", type=int)
    parser.add_argument("--run-id")
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument(
        "--offline",
        action="store_true",
        help="skip only the live vLLM endpoint check during preflight",
    )
    return parser


def _config(arguments: argparse.Namespace) -> RunConfig:
    return RunConfig(
        project_root=ROOT,
        run_root=arguments.run_root,
        base_url=arguments.base_url,
        mini_python=arguments.mini_python,
        tokenizer_path=arguments.tokenizer_path,
        v3_dependency_path=arguments.v3_dependency_path,
        model=SERVED_MODEL_NAME,
        agent_timeout_seconds=arguments.agent_timeout,
    )


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    config = _config(arguments)
    if arguments.command == "list":
        print(json.dumps([cell.as_record() for cell in qwen3_cells(ROOT)], indent=2))
        return 0
    if arguments.command == "preflight":
        result = preflight(config, check_endpoint=not arguments.offline)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result["overall"] == "PASS" else 2
    if arguments.command == "canary":
        result = run_canary(config)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result.get("status") == "PASS" else 3
    if arguments.command == "cell":
        if (arguments.index is None) == (arguments.run_id is None):
            raise SystemExit("cell requires exactly one of --index or --run-id")
        selector = arguments.index if arguments.index is not None else arguments.run_id
        result = run_cell(config, selector)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result.get("technical_valid") else 3
    if arguments.index is not None or arguments.run_id is not None:
        raise SystemExit("--index and --run-id apply only to the cell command")
    summary = run_batch(config, workers=arguments.workers)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary["technical_failure_count"] == 0 else 3


if __name__ == "__main__":
    raise SystemExit(main())
