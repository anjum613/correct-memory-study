#!/usr/bin/env python3
"""Canonical file-digest, strict verification, and script observation CLI."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cmpilot.batch_script_attestation import (  # noqa: E402
    AttestationError,
    observe_running_script,
    require_digest_match,
)
from cmpilot.file_digest import FileDigestError, sha256_file  # noqa: E402


def _write_error(path: Path | None, value: dict[str, object]) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    digest = commands.add_parser("digest")
    digest.add_argument("--path", type=Path, required=True)
    verify = commands.add_parser("verify")
    verify.add_argument("--path", type=Path, required=True)
    verify.add_argument("--expected", required=True)
    verify.add_argument("--context", required=True)
    verify.add_argument("--record", type=Path, required=True)
    observe = commands.add_parser("observe")
    observe.add_argument("--path", required=True)
    observe.add_argument("--record", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    if arguments.command == "observe":
        observe_running_script(arguments.path, arguments.record)
        return 0
    try:
        observed = sha256_file(arguments.path)
        if arguments.command == "digest":
            print(observed)
            return 0
        require_digest_match(
            arguments.expected,
            observed,
            context=arguments.context,
            record=arguments.record,
        )
        print(observed)
        return 0
    except (AttestationError, FileDigestError) as error:
        if arguments.command == "verify" and not arguments.record.exists():
            _write_error(
                arguments.record,
                {
                    "context": arguments.context,
                    "error": f"{type(error).__name__}: {error}",
                    "label": "RUNTIME_SOURCE_HASH_MISMATCH",
                    "pass": False,
                },
            )
        print(f"{type(error).__name__}: {error}", file=sys.stderr)
        return 42


if __name__ == "__main__":
    raise SystemExit(main())
