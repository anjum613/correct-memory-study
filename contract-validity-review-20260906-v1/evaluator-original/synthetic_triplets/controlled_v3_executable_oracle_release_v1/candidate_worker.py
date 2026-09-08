#!/usr/bin/env python3
"""One fail-closed candidate-state worker invoked only by the trusted validator."""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import sys


WRITE = os.write
PREFIX = b"V3_WORKER_RESULT="


def _load_python(path):
    specification = importlib.util.spec_from_file_location("v3_candidate_service", path)
    if specification is None or specification.loader is None:
        raise ImportError("candidate service loader unavailable")
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    function = getattr(module, "run")
    if not callable(function):
        raise TypeError("candidate must export callable run")
    return function


def _load_x02(path):
    from .x02_lowering import lower
    from .x02_machine import Execution, run
    from .x02_oracle import InvalidInput, cells, validate_request
    compiled = lower(path.read_text())

    def application(pattern, records, flags="NONE"):
        try:
            validate_request(pattern, records, flags)
        except InvalidInput:
            return Execution("INVALID_INPUT")
        return run(compiled, cells(pattern, records, flags), tuple(records))
    return application


def evaluate(family_id, state, service_path):
    from .candidate_test_registry import checks
    from .harness import functional, invariant
    existing, feature, focal = checks(family_id)
    application = (_load_x02(service_path) if family_id == "X02"
                   else _load_python(service_path))
    return {
        "family_id": family_id,
        "state": state,
        "existing": functional(existing, application),
        "feature": functional(feature, application),
        "invariant": invariant(focal, application),
    }


def main(argv=None):
    arguments = sys.argv[1:] if argv is None else argv
    try:
        if len(arguments) != 3 or arguments[0] not in {f"X{n:02d}" for n in range(1, 29)} or arguments[1] not in {"B", "U", "R"}:
            raise ValueError("invalid worker arguments")
        result = evaluate(arguments[0], arguments[1], Path(arguments[2]).resolve())
        result["worker_status"] = "COMPLETE"
        code = 0
    except BaseException as error:
        result = {"worker_status": "HARNESS_ERROR", "error": type(error).__name__}
        code = 2
    WRITE(1, PREFIX + json.dumps(result, sort_keys=True, default=repr).encode("utf-8") + b"\n")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
