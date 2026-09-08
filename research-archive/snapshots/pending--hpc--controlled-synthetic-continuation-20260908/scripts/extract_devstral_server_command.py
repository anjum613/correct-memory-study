#!/usr/bin/env python3
"""Emit a validated Devstral server argv as NUL-delimited UTF-8."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import BinaryIO, Sequence


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cmpilot.devstral_profile import validate_devstral_server_argv  # noqa: E402
from cmpilot.server_command import encode_nul_delimited, load_command_argv  # noqa: E402


SCHEMA = "devstral-server-command-extraction-v1"
PASS = "DEVSTRAL_SERVER_COMMAND_EXTRACTION_PASS"
FAILURE = "DEVSTRAL_SERVER_COMMAND_EXTRACTION_FAILURE"


def _write_new_json(path: Path, value: object) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, sort_keys=True)
        stream.write("\n")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--command-json", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    arguments = parser.parse_args(argv)
    try:
        command = validate_devstral_server_argv(
            load_command_argv(arguments.command_json)
        )
        payload = encode_nul_delimited(command)
        result = {
            "argument_count": len(command),
            "command_input_sha256": hashlib.sha256(
                arguments.command_json.read_bytes()
            ).hexdigest(),
            "label": PASS,
            "schema": SCHEMA,
        }
        status = 0
    except Exception as error:
        payload = b""
        result = {
            "error": f"{type(error).__name__}: {error}",
            "label": FAILURE,
            "schema": SCHEMA,
        }
        print(f"{FAILURE}: {result['error']}", file=sys.stderr)
        status = 79
    try:
        _write_new_json(arguments.result, result)
    except OSError as error:
        print(f"{FAILURE}: cannot write result: {error}", file=sys.stderr)
        return 79
    if status == 0:
        output: BinaryIO = sys.stdout.buffer
        output.write(payload)
        output.flush()
    return status


if __name__ == "__main__":
    raise SystemExit(main())
