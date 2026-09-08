#!/usr/bin/env python3
"""Run the predetermined calculator fixture against the ready Devstral server."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cmpilot.devstral_profile import (  # noqa: E402
    AGENT_PYTHON,
    MODEL_ID,
    MODEL_SNAPSHOT,
    PROFILE_ID,
)
from cmpilot.devstral_mini_swe_adapter import (  # noqa: E402
    write_devstral_adapter,
)
from cmpilot.devstral_technical_smoke import load_json  # noqa: E402
from cmpilot.mini_swe_adapter import write_adapter as write_qwen_adapter  # noqa: E402
from cmpilot.smoke_runner import DEFAULT_AGENT_CONFIG, SmokeConfig, run_smoke  # noqa: E402
import cmpilot.smoke_runner as smoke_runner  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--runs-root", type=Path, required=True)
    parser.add_argument("--runtime-integrity", type=Path, required=True)
    parser.add_argument("--agent-config-source", type=Path, required=True)
    parser.add_argument("--agent-timeout", type=int, default=600)
    arguments = parser.parse_args()
    runtime = load_json(arguments.runtime_integrity)
    if not (
        runtime.get("pass") is True
        and runtime.get("production_ready") is True
        and runtime.get("status") == "READY"
        and runtime.get("profile_id") == PROFILE_ID
    ):
        raise RuntimeError("Devstral runtime integrity is not READY")
    if arguments.agent_config_source.resolve(strict=True) != DEFAULT_AGENT_CONFIG.resolve(
        strict=True
    ):
        raise RuntimeError("Devstral technical smoke agent config changed")
    if smoke_runner.write_adapter is not write_qwen_adapter:
        raise RuntimeError("shared smoke adapter writer changed before Devstral selection")
    smoke_runner.write_adapter = write_devstral_adapter
    return run_smoke(
        SmokeConfig(
            base_url=arguments.base_url,
            model=MODEL_ID,
            mini_python=str(AGENT_PYTHON),
            runs_root=arguments.runs_root,
            agent_timeout=arguments.agent_timeout,
            tokenizer_path=str(MODEL_SNAPSHOT),
            agent_config_source=arguments.agent_config_source,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
