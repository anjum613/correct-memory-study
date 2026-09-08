#!/usr/bin/env python3
"""Run Qwen3-Coder-Next FP8 over the frozen Devstral-source final-13 arm."""

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
MODEL_ID = "Qwen/Qwen3-Coder-Next-FP8"
MODEL_REVISION = "da6e2ed27304dd39abadd9c82ef50e8de67bdd4c"
SERVED_MODEL_NAME = "qwen3-coder-next-fp8"
AGENT_CONFIG_PATH = Path(
    "configs/agent/mini_swe_agent_qwen3_coder_next_fp8.yaml"
)
MODEL_PROFILE_PATH = Path("configs/models/qwen3-coder-next-fp8-runpod.json")
RECOMMENDED_AGENT_CONFIG_PATH = Path(
    "configs/agent/mini_swe_agent_qwen3_coder_next_recommended.yaml"
)
RECOMMENDED_MODEL_PROFILE_PATH = Path(
    "configs/models/qwen3-coder-next-fp8-recommended-runpod.json"
)
TOKENIZER_JSON_SHA256 = (
    "19564a48c4f71a2a1b937cce34c737a1e662b171c5f5d7edf641a15cd896f07d"
)
TOKENIZER_CONFIG_SHA256 = (
    "fc76878832c668e3f0f8be66e6239a475b9093d2fe5cef97c242369779e6c6e6"
)
DEFAULT_MINI_PYTHON = "/home/s224049759/environments/mini-swe-agent-smoke/bin/python"
DEFAULT_TOKENIZER = (
    "/home/s224049759/model-cache/qwen3-coder-next-fp8/"
    "da6e2ed27304dd39abadd9c82ef50e8de67bdd4c"
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
        default=Path(
            os.environ.get("QWEN3_CODER_NEXT_TOKENIZER_PATH", DEFAULT_TOKENIZER)
        ),
    )
    parser.add_argument(
        "--run-root",
        type=Path,
        default=Path(
            os.environ.get("CMPILOT_RUNS_ROOT", "qwen3-coder-next-final13-runs")
        ),
    )
    parser.add_argument(
        "--v3-dependency-path",
        type=Path,
        default=Path(
            os.environ.get(
                "QWEN3_CODER_NEXT_V3_DEPENDENCY_PATH", DEFAULT_V3_DEPENDENCIES
            )
        ),
    )
    parser.add_argument("--agent-timeout", type=int)
    parser.add_argument(
        "--recommended",
        action="store_true",
        help=(
            "use Qwen's native tool calling, temperature=1.0, top_p=0.95, "
            "top_k=40, 32K context, and the amended 30-step agent profile"
        ),
    )
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
    recommended = bool(arguments.recommended)
    agent_timeout = arguments.agent_timeout
    if agent_timeout is None:
        agent_timeout = 1200 if recommended else 600
    return RunConfig(
        project_root=ROOT,
        run_root=arguments.run_root,
        base_url=arguments.base_url,
        mini_python=arguments.mini_python,
        tokenizer_path=arguments.tokenizer_path,
        v3_dependency_path=arguments.v3_dependency_path,
        model=SERVED_MODEL_NAME,
        agent_timeout_seconds=agent_timeout,
        source_model_key=SOURCE_MODEL_KEY,
        model_id=MODEL_ID,
        model_revision=MODEL_REVISION,
        agent_config_path=(
            RECOMMENDED_AGENT_CONFIG_PATH if recommended else AGENT_CONFIG_PATH
        ),
        model_profile_path=(
            RECOMMENDED_MODEL_PROFILE_PATH if recommended else MODEL_PROFILE_PATH
        ),
        tokenizer_json_sha256=TOKENIZER_JSON_SHA256,
        tokenizer_config_sha256=TOKENIZER_CONFIG_SHA256,
        context_limit=32768 if recommended else 4096,
        completion_limit=512,
        temperature=1.0 if recommended else 0.0,
        top_p=0.95 if recommended else None,
        top_k=40 if recommended else None,
        native_tool_calls=recommended,
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
