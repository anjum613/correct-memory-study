#!/usr/bin/env python3
"""Thin runner for the two frozen public callables; it adds no assertions."""
from __future__ import annotations
import argparse
import importlib
import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = ROOT / "repository"
sys.path.insert(0, str(REPOSITORY))

FAMILY = 'X06'
ENTRYPOINTS = ['x06_existing', 'x06_feature']

def load_python(path):
    spec = importlib.util.spec_from_file_location("constructor_candidate_service", path)
    if spec is None or spec.loader is None:
        raise ImportError("candidate service loader unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    function = getattr(module, "run")
    if not callable(function):
        raise TypeError("candidate must export callable run")
    return function

def load_x02(path):
    from fixture_api.x02_inputs import InvalidInput, cells, validate_request
    from fixture_api.x02_lowering import lower
    from fixture_api.x02_machine import Execution, run
    compiled = lower(path.read_text(encoding="utf-8"))
    def application(pattern, records, flags="NONE"):
        try:
            validate_request(pattern, records, flags)
        except InvalidInput:
            return Execution("INVALID_INPUT")
        return run(compiled, cells(pattern, records, flags), tuple(records))
    return application

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--service", required=True)
    args = parser.parse_args()
    service = (ROOT / args.service).resolve()
    if ROOT not in service.parents:
        raise ValueError("service must be inside workspace")
    application = load_x02(service) if FAMILY == "X02" else load_python(service)
    tests = importlib.import_module("public_tests")
    completed = []
    for name in ENTRYPOINTS:
        getattr(tests, name)(application)
        completed.append(name)
    print(json.dumps({"family_id": FAMILY, "public_entrypoints": completed, "status": "PASS"}, sort_keys=True))

if __name__ == "__main__":
    main()
