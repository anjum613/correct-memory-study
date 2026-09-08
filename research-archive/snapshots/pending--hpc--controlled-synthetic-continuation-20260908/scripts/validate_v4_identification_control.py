#!/usr/bin/env python3
from __future__ import annotations

import argparse

import yaml

from cmpilot.identification_control_v4 import (
    CONTROL_NAMES,
    validate_all_controls,
    validate_identification_control,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run model-free V4 identification non-vacuity controls."
    )
    parser.add_argument("control", choices=(*sorted(CONTROL_NAMES), "all"))
    arguments = parser.parse_args()
    if arguments.control == "all":
        result = validate_all_controls()
    else:
        result = validate_identification_control(arguments.control).result
    print(yaml.safe_dump(result, sort_keys=True), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
