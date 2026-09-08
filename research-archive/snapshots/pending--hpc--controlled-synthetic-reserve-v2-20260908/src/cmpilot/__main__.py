"""Command-line entry point for cmpilot."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from dataclasses import asdict
from pathlib import Path

from .adapter_preflight import AdapterPreflightConfig, run_adapter_preflight
from .artifact_logger import write_json
from .artifact_preserver import atomic_preserve_directory
from .doctor import collect_report, render_report
from .multiturn_preflight import MultiturnPreflightConfig, run_multiturn_preflight
from .smoke_runner import dry_run, resolve_config, run_smoke


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="cmpilot")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("doctor", help="report local prerequisites and probe /v1/models when configured")
    smoke = commands.add_parser("smoke", help="run the isolated calculator engineering smoke test")
    smoke.add_argument("--base-url", help="OpenAI-compatible vLLM base URL")
    smoke.add_argument("--model", help="expected model ID")
    smoke.add_argument("--mini-python", help="mini-SWE-agent 2.4.6 interpreter")
    smoke.add_argument("--runs-root", help="directory where immutable run artifacts are created")
    smoke.add_argument("--agent-timeout", type=int, default=600, help="wall-clock timeout in seconds (default: 600)")
    smoke.add_argument("--dry-run", action="store_true", help="perform preflight and print the planned run without launching an agent")
    smoke.add_argument("--live", action="store_true", help="explicitly authorize one live mini-SWE-agent launch")
    adapter_preflight = commands.add_parser(
        "adapter-preflight", help="validate the adapter against the unavailable 127.0.0.1:9 endpoint"
    )
    adapter_preflight.add_argument("--mini-python", required=True, help="absolute mini-SWE-agent 2.4.6 interpreter")
    adapter_preflight.add_argument("--artifact-dir", required=True, help="directory for preflight artifacts")
    adapter_preflight.add_argument("--timeout", type=float, default=45, help="adapter timeout in seconds")
    multiturn = commands.add_parser(
        "multiturn-preflight", help="run the deterministic direct-adapter CPU integration"
    )
    multiturn.add_argument("--mini-python", required=True, help="absolute mini-SWE-agent 2.4.6 interpreter")
    multiturn.add_argument("--artifact-dir", required=True, help="directory for immutable preflight artifacts")
    multiturn.add_argument("--timeout", type=int, default=90, help="agent timeout in seconds")
    preserve = commands.add_parser(
        "preserve-artifacts", help="atomically preserve one run directory once"
    )
    preserve.add_argument("--source", required=True)
    preserve.add_argument("--destination", required=True)
    preserve.add_argument("--status-file")
    arguments = parser.parse_args(argv)

    if arguments.command == "doctor":
        print(render_report(collect_report()))
        return 0
    if arguments.command == "smoke":
        config = resolve_config(arguments)
        if arguments.dry_run:
            return dry_run(config)
        if not arguments.live:
            parser.error("live smoke execution requires --live; use --dry-run to inspect first")
        return run_smoke(config)
    if arguments.command == "adapter-preflight":
        return run_adapter_preflight(
            AdapterPreflightConfig(
                mini_python=arguments.mini_python,
                artifact_dir=Path(arguments.artifact_dir),
                timeout_seconds=arguments.timeout,
            )
        )
    if arguments.command == "multiturn-preflight":
        return run_multiturn_preflight(
            MultiturnPreflightConfig(
                mini_python=arguments.mini_python,
                artifact_dir=Path(arguments.artifact_dir),
                timeout_seconds=arguments.timeout,
            )
        )
    if arguments.command == "preserve-artifacts":
        result = atomic_preserve_directory(
            Path(arguments.source), Path(arguments.destination)
        )
        record = asdict(result)
        if arguments.status_file:
            write_json(Path(arguments.status_file), record)
        print(record["status"])
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
