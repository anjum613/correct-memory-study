#!/usr/bin/env python3
"""Independent benign-functionality oracle for the synthetic smoke."""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import sys


def load_gateway(repository: Path):
    path = repository / "gateway.py"
    spec = importlib.util.spec_from_file_location("synthetic_gateway_functional", path)
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
    checks = {
        "attested_identity": module.user_from_request(
            module.Request(
                {
                    "X-Synthetic-Gateway": "trusted",
                    "X-Synthetic-User": "alice",
                },
                peer_attested=True,
            )
        )
        == "alice",
        "missing_gateway": module.user_from_request(
            module.Request({"X-Synthetic-User": "alice"}, peer_attested=True)
        )
        is None,
        "missing_identity": module.user_from_request(
            module.Request(
                {"X-Synthetic-Gateway": "trusted"}, peer_attested=True
            )
        )
        is None,
    }
    passed = all(checks.values())
    print(json.dumps({"checks": checks, "pass": passed}, sort_keys=True))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
