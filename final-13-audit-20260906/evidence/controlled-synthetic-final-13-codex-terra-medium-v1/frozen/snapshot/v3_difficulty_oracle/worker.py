"""State worker: the unchanged scientific oracle through lossless interface views."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys

from synthetic_triplets.controlled_v3_executable_oracle_release_v1.candidate_worker import _load_python, _load_x02
from synthetic_triplets.controlled_v3_executable_oracle_release_v1.candidate_test_registry import checks
from synthetic_triplets.controlled_v3_executable_oracle_release_v1.harness import functional, invariant
from .interface_adapter import adapt_application

WRITE = os.write
PREFIX = b"V3_WORKER_RESULT="


def evaluate(family, state, service):
    existing, feature, focal = checks(family)
    application = _load_x02(service) if family == "X02" else _load_python(service)
    application = adapt_application(family, application)
    return {"family_id": family, "state": state,
            "existing": functional(existing, application),
            "feature": functional(feature, application),
            "invariant": invariant(focal, application)}


def main():
    try:
        family, state, path = sys.argv[1:]
        if family in {"X19", "X25"} or family not in {f"X{n:02d}" for n in range(1, 29)} or state not in {"B", "U", "R"}:
            raise ValueError("invalid worker identity")
        result = evaluate(family, state, Path(path).resolve())
        result["worker_status"] = "COMPLETE"
        code = 0
    except BaseException as error:
        result = {"worker_status": "HARNESS_ERROR", "error": type(error).__name__}
        code = 2
    WRITE(1, PREFIX + json.dumps(result, sort_keys=True, default=repr).encode() + b"\n")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
