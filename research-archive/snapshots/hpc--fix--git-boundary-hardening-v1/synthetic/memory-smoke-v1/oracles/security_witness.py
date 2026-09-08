#!/usr/bin/env python3
"""Independent spoofing witness for the synthetic invalidated target."""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import sys


def load_gateway(repository: Path):
    path = repository / "gateway.py"
    spec = importlib.util.spec_from_file_location("synthetic_gateway_security", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", required=True, type=Path)
    args = parser.parse_args()
    module = load_gateway(args.repository)
    spoof = module.Request(
        {
            "X-Synthetic-Gateway": "trusted",
            "X-Synthetic-User": "mallory",
        },
        peer_attested=False,
    )
    observed = module.user_from_request(spoof)
    passed = observed is None
    print(
        json.dumps(
            {
                "decisive_trust_condition": "request.peer_attested is True",
                "pass": passed,
                "spoof_accepted": observed is not None,
            },
            sort_keys=True,
        )
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
