from pathlib import Path

import pytest

from cmpilot.v2_logging import REQUIRED_METADATA_FIELDS, V2RunLog, write_v2_run_log
from cmpilot.v2_preflight import V2_PROTOCOL_VERSION, V2PreflightError


def metadata() -> dict[str, object]:
    value = {field: "unknown" for field in REQUIRED_METADATA_FIELDS}
    value.update(
        {
            "protocol_version": V2_PROTOCOL_VERSION,
            "gpu_count": 0,
            "tensor_parallel_degree": 0,
            "physical_context": 32768,
            "first_request_tokens": 500,
            "trajectory_budget": 16384,
            "safety_reserve": 256,
        }
    )
    return value


def test_all_required_metadata_is_enforced() -> None:
    for field in REQUIRED_METADATA_FIELDS:
        broken = metadata()
        del broken[field]
        with pytest.raises(V2PreflightError, match="missing"):
            V2RunLog(broken)


def test_run_log_is_exclusive_and_canonical(tmp_path: Path) -> None:
    path = tmp_path / "attempt-1" / "run.json"
    write_v2_run_log(path, V2RunLog(metadata()))
    assert path.read_bytes().endswith(b"\n")
    with pytest.raises(V2PreflightError, match="overwrite"):
        write_v2_run_log(path, V2RunLog(metadata()))
