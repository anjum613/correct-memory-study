"""Command-line entry point for cmpilot."""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from .doctor import collect_report, render_report
from .model_profiles import load_model_profile
from .smoke_runner import dry_run, resolve_config, run_smoke


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="cmpilot")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("doctor", help="report local prerequisites and probe /v1/models when configured")
    profile_arguments = commands.add_parser(
        "model-profile-arguments",
        help="print one validated vLLM server argument per line for a dedicated launcher",
    )
    profile_arguments.add_argument("--profile", required=True)
    smoke = commands.add_parser("smoke", help="run the isolated calculator engineering smoke test")
    smoke.add_argument("--base-url", help="OpenAI-compatible vLLM base URL")
    smoke.add_argument("--model", help="expected model ID")
    smoke.add_argument("--profile", help="exact, repository-owned model profile for an isolated replication smoke")
    smoke.add_argument("--mini-python", help="mini-SWE-agent 2.4.6 interpreter")
    smoke.add_argument("--runs-root", help="directory where immutable run artifacts are created")
    smoke.add_argument("--agent-timeout", type=int, default=600, help="wall-clock timeout in seconds (default: 600)")
    smoke.add_argument("--dry-run", action="store_true", help="perform preflight and print the planned run without launching an agent")
    smoke.add_argument("--live", action="store_true", help="explicitly authorize one live mini-SWE-agent launch")
    arguments = parser.parse_args(argv)

    if arguments.command == "doctor":
        print(render_report(collect_report()))
        return 0
    if arguments.command == "model-profile-arguments":
        try:
            profile = load_model_profile(arguments.profile)
        except (KeyError, ValueError) as error:
            parser.error(str(error))
        if not profile.launchable:
            parser.error(f"model profile is attestation-only and cannot be launched: {profile.name}")
        for argument in profile.server_arguments:
            print(argument)
        return 0
    if arguments.command == "smoke":
        try:
            config = resolve_config(arguments)
        except (KeyError, ValueError) as error:
            parser.error(str(error))
        if arguments.dry_run:
            return dry_run(config)
        if not arguments.live:
            parser.error("live smoke execution requires --live; use --dry-run to inspect first")
        return run_smoke(config)

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
