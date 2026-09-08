from __future__ import annotations

import json
from pathlib import Path, PurePosixPath

import pytest

from cmpilot.source_pairing import AuditedWorkspaceReader
from cmpilot.susvibes_feasibility import DEVELOPMENT_IDS, SUSVIBES_REVISION
from cmpilot.target_identity_v3 import (
    FROZEN_UNSEEN_TARGET_COUNT,
    TargetArtifactRouter,
    TargetIdentityScope,
    build_b_only_representation_v3,
    load_frozen_target_scope,
)


ROOT = Path(__file__).resolve().parents[1]
UNIVERSE = (
    ROOT
    / "artifacts/context-dependent-memory-susvibes-feasibility/unseen-target-universe.json"
)
SYNTHETIC_ID = "synthetic__future-fixture_" + "f" * 40


def _synthetic_workspace(tmp_path: Path) -> Path:
    root = tmp_path / SYNTHETIC_ID
    repository = root / "repository/pkg"
    repository.mkdir(parents=True)
    (root / "task.md").write_text(
        "Implement `pkg.links.expand_link` to render an href for a document link.",
        encoding="utf-8",
    )
    (root / "public-metadata.json").write_text(
        json.dumps(
            {
                "b_image_manifest_digest": "sha256:" + "1" * 64,
                "b_tree_sha256": "2" * 64,
                "benchmark_revision": SUSVIBES_REVISION,
                "image_name": "synthetic-fixture-no-image",
                "instance_id": SYNTHETIC_ID,
                "language": "python",
                "project": "synthetic-fixture",
            }
        ),
        encoding="utf-8",
    )
    (repository / "links.py").write_text(
        "def expand_link(document):\n    raise NotImplementedError\n", encoding="utf-8"
    )
    return root


def test_frozen_181_membership_and_development_exclusion() -> None:
    scope = load_frozen_target_scope(UNIVERSE)
    assert scope.confirmatory is True
    assert len(scope.target_ids) == FROZEN_UNSEEN_TARGET_COUNT
    for target_id in tuple(sorted(scope.target_ids)):
        scope.validate(target_id)
    with pytest.raises(PermissionError, match="permanently excluded"):
        scope.validate(DEVELOPMENT_IDS[0])
    with pytest.raises(PermissionError, match="outside the frozen"):
        scope.validate(SYNTHETIC_ID)


def test_synthetic_fixture_uses_same_identity_validator_without_becoming_confirmatory() -> None:
    scope = TargetIdentityScope.synthetic_fixture((SYNTHETIC_ID,))
    scope.validate(SYNTHETIC_ID)
    assert scope.confirmatory is False
    with pytest.raises(PermissionError, match="synthetic fixture"):
        scope.validate("other__fixture_" + "e" * 40)


def test_b_only_extractor_accepts_parameterized_nondevelopment_identity(
    tmp_path: Path,
) -> None:
    scope = TargetIdentityScope.synthetic_fixture((SYNTHETIC_ID,))
    reader = AuditedWorkspaceReader(_synthetic_workspace(tmp_path))
    representation = build_b_only_representation_v3(reader, scope=scope)
    assert representation["benchmark_instance_id"] == SYNTHETIC_ID
    assert representation["benchmark_revision"] == SUSVIBES_REVISION
    assert all(event["decision"] == "ALLOW" for event in reader.events)


def test_opaque_real_ids_route_without_any_target_content_read() -> None:
    scope = load_frozen_target_scope(UNIVERSE)
    router = TargetArtifactRouter(
        public_root=PurePosixPath("targets/public/susvibes-confirmatory"),
        sealed_root=PurePosixPath("oracle_sealed/susvibes-confirmatory"),
    )
    opaque_ids = tuple(sorted(scope.target_ids))[:4]
    routes = [router.routes(target_id, scope=scope) for target_id in opaque_ids]
    assert [row["target_id"] for row in routes] == list(opaque_ids)
    assert all(row["public_workspace"].endswith(row["target_id"]) for row in routes)
    assert router.content_reads == 0


def test_production_v3_paths_contain_no_development_answer_or_target_maps() -> None:
    production_paths = (
        ROOT / "src/cmpilot/confirmatory_v3.py",
        ROOT / "src/cmpilot/pair_review_v3.py",
        ROOT / "src/cmpilot/source_pairing_v3.py",
        ROOT / "src/cmpilot/target_eligibility_v3.py",
    )
    forbidden_literals = tuple(DEVELOPMENT_IDS) + (
        "DEVELOPMENT_ANSWERS",
        "DEVELOPMENT_IDS[",
    )
    for path in production_paths:
        source = path.read_text(encoding="utf-8")
        assert not any(value in source for value in forbidden_literals), path
