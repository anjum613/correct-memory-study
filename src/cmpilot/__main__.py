"""Command-line entry point for cmpilot."""

from __future__ import annotations

import argparse

from .doctor import collect_report, render_report


def main() -> int:
    parser = argparse.ArgumentParser(prog="cmpilot")
    parser.add_argument("command", choices=["doctor"])
    arguments = parser.parse_args()

    if arguments.command == "doctor":
        print(render_report(collect_report()))
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
