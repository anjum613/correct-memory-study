#!/usr/bin/env python3
"""Run corrected Devstral Small 2507 over its frozen final-13 arm."""

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
    preflight,
    qwen3_cells,
    run_batch,
    run_canary,
    run_cell,
)


SOURCE_MODEL_KEY = "devstral-small-2507"
MODEL_ID = "mistralai/Devstral-Small-2507"
MODEL_REVISION = "bd165ab26cebbcc2eea2c4ecbfc07f3ac42b3c39"
SERVED_MODEL_NAME = "devstral-small-2507"
TEKKEN_SHA256 = "839c48629ff570bd664586800aa3ee17ee628f56efc7fd8e145cc01467a1c188"
AGENT_CONFIG_PATH = Path("configs/agent/mini_swe_agent_devstral_recommended.yaml")
MODEL_PROFILE_PATH = Path("configs/models/devstral-small-2507-recommended-runpod.json")
DEFAULT_MINI_PYTHON = (
    "/home/s224049759/environments/devstral-small-2507-agent-v1/bin/python"
)
DEFAULT_TOKENIZER = (
    "/home/s224049759/model-cache/devstral-small-2507/" + MODEL_REVISION
)
DEFAULT_V3_DEPENDENCIES = (
    "/home/s224049759/environments/qwen36-vllm-v1/lib/python3.12/site-packages"
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command", choices=("list", "preflight", "canary", "cell", "batch")
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
        default=Path(os.environ.get("DEVSTRAL_TOKENIZER_PATH", DEFAULT_TOKENIZER)),
    )
    parser.add_argument(
        "--run-root",
        type=Path,
        default=Path(os.environ.get("CMPILOT_RUNS_ROOT", "devstral-final13-runs")),
    )
    parser.add_argument(
        "--v3-dependency-path",
        type=Path,
        default=Path(
            os.environ.get("DEVSTRAL_V3_DEPENDENCY_PATH", DEFAULT_V3_DEPENDENCIES)
        ),
    )
    parser.add_argument("--agent-timeout", type=int, default=1200)
    parser.add_argument("--index", type=int)
    parser.add_argument("--run-id")
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--offline", action="store_true")
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
        source_model_key=SOURCE_MODEL_KEY,
        model_id=MODEL_ID,
        model_revision=MODEL_REVISION,
        agent_config_path=AGENT_CONFIG_PATH,
        model_profile_path=MODEL_PROFILE_PATH,
        tokenizer_json_sha256=TEKKEN_SHA256,
        tokenizer_config_sha256=TEKKEN_SHA256,
        context_limit=32768,
        completion_limit=512,
        temperature=0.15,
        native_tool_calls=True,
        tokenizer_kind="mistral",
        tokenizer_tekken_sha256=TEKKEN_SHA256,
        adapter_kind="devstral_native",
        quantization=None,
        dtype="bfloat16",
        tool_call_parser="mistral",
    )


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    config = _config(arguments)
    if arguments.command == "list":
        cells = qwen3_cells(
            ROOT,
            source_model_key=SOURCE_MODEL_KEY,
            model_id=MODEL_ID,
            model_revision=MODEL_REVISION,
        )
        print(json.dumps([cell.as_record() for cell in cells], indent=2))
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
