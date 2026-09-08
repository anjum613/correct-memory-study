#!/usr/bin/env python3
"""Run only the frozen public callables against one authored component."""
from __future__ import annotations
import argparse
import importlib
import importlib.util
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = ROOT / "repository"
sys.path.insert(0, str(REPOSITORY))
FAMILY = 'X20'
SERVICE_PATH = 'app/service.py'
ENTRYPOINTS = ['x20_existing', 'x20_feature']

def load_python(path):
    spec = importlib.util.spec_from_file_location("constructor_component_service", path)
    if spec is None or spec.loader is None:
        raise ImportError("component service loader unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    function = getattr(module, "run")
    if not callable(function):
        raise TypeError("component must export callable run")
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
    parser.add_argument("--component", choices=("neutral_target", "functional_target"), required=True)
    parser.add_argument("--scope", choices=("existing", "all"), required=True)
    args = parser.parse_args()
    if args.component == "neutral_target" and args.scope != "existing":
        parser.error("neutral_target supports only the existing-behavior check")
    service = ROOT / "components" / args.component / SERVICE_PATH
    application = load_x02(service) if FAMILY == "X02" else load_python(service)
    tests = importlib.import_module("public_tests")
    selected = ENTRYPOINTS[:1] if args.scope == "existing" else ENTRYPOINTS
    for name in selected:
        getattr(tests, name)(application)
    print("PUBLIC_CHECK_PASS " + args.component + " " + args.scope)

if __name__ == "__main__":
    main()
