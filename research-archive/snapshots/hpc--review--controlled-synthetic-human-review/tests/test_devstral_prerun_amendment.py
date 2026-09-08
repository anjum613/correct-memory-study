from __future__ import annotations

import hashlib
import json
from pathlib import Path

from cmpilot.final_experiment import canonical_json_bytes
from cmpilot.repository_manager import repository_content_digest


ROOT = Path(__file__).parents[1]
AMENDMENT = (
    ROOT
    / "docs/methodology/axios-devstral-29552-prerun-technical-amendment-v1.json"
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_prerun_amendment_is_canonical_and_self_auditing() -> None:
    raw = AMENDMENT.read_bytes()
    amendment = json.loads(raw)
    manifest = json.loads(
        (ROOT / "configs/experiments/track-b-axios-partial-v1.json").read_text()
    )

    assert raw == canonical_json_bytes(amendment)
    assert amendment["affected_runs"]["array_job_id"] == "29552"
    assert len(amendment["affected_runs"]["runs"]) == 4
    assert amendment["affected_runs"]["summary"] == {
        "agent_action_count": 0,
        "all_original_attempts_preserved": True,
        "all_technical_invalid": True,
        "mini_swe_invocation_count": 0,
        "model_request_count": 0,
        "model_response_count": 0,
    }

    scientific = amendment["scientific_input_sha256_before_after"]
    assert all(record["before"] == record["after"] for record in scientific.values())
    for record in scientific.values():
        relative = record.get("path")
        if relative is None:
            continue
        path = ROOT / relative
        observed = (
            repository_content_digest(path).sha256
            if record.get("digest_method")
            == "cmpilot.repository_manager.repository_content_digest"
            else _sha256(path)
        )
        assert observed == record["after"], relative

    assert scientific["devstral_generation_parameters"]["after"] == (
        manifest["models"]["devstral-small-2507"][
            "generation_parameters_sha256"
        ]
    )
    assert scientific["devstral_model_profile"]["after"] == (
        manifest["models"]["devstral-small-2507"]["profile_sha256"]
    )
    assert scientific["qwen_generation_parameters"]["after"] == (
        manifest["models"]["qwen2.5-coder-32b-instruct"][
            "generation_parameters_sha256"
        ]
    )
    assert scientific["qwen_model_profile"]["after"] == (
        manifest["models"]["qwen2.5-coder-32b-instruct"]["profile_sha256"]
    )
    assert scientific["seeds"]["after"] == hashlib.sha256(
        canonical_json_bytes(manifest["seeds"])
    ).hexdigest()

    for relative, expected in amendment["runtime_files_after_correction"].items():
        assert _sha256(ROOT / relative) == expected, relative
