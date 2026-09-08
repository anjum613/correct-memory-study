"""Frozen opaque target identity and routing boundary for confirmatory V3."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
from typing import Callable

from cmpilot.source_pairing import AuditedWorkspaceReader, build_b_only_representation
from cmpilot.susvibes_feasibility import (
    DEVELOPMENT_IDS,
    SUSVIBES_REVISION,
    SUSVIBES_TASK_COUNT,
)


FROZEN_UNSEEN_TARGET_COUNT = 181
FROZEN_UNSEEN_IDS_SHA256 = "bf9b0056ab734b766fd021df7542be10ffe873cf56b87d84584e6a29959b8d6d"
FROZEN_UNSEEN_MANIFEST_SHA256 = (
    "436efcb9efd8e27f104c458ed40f2a3bb9ec76fad75f9cfa30b4cd1c24656d44"
)
FROZEN_UNIVERSE_PURPOSE = "CONFIRMATORY_FROZEN_181"
SYNTHETIC_FIXTURE_PURPOSE = "DEVELOPMENT_SYNTHETIC_EXCLUDED_FIXTURE"
DEVELOPMENT_FIXTURE_PURPOSE = "DEVELOPMENT_PERMANENT_EXCLUSIONS"
_INSTANCE_ID = re.compile(r"^[A-Za-z0-9.-]+__[^/]+_[0-9a-f]{40}$")
_MANIFEST_FIELDS = {
    "benchmark_revision",
    "benchmark_tag",
    "candidate_specific_implementation_details_inspected",
    "candidate_specific_security_details_inspected",
    "confirmatory_screening_authorized",
    "dataset_sha256",
    "development_ids",
    "development_target_count",
    "enumeration_fields_read",
    "raw_task_count",
    "schema",
    "unseen_ids",
    "unseen_ids_sha256",
    "unseen_target_count",
}


class TargetIdentityV3Error(ValueError):
    """A target identity is outside its prospectively declared V3 scope."""


def _ids_sha256(values: tuple[str, ...]) -> str:
    payload = json.dumps(values, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class TargetIdentityScope:
    """An explicit identity allow-list; never a target-content provider."""

    target_ids: frozenset[str]
    purpose: str
    identity_list_sha256: str
    manifest_sha256: str | None

    def validate(self, target_id: str) -> None:
        if not isinstance(target_id, str) or not _INSTANCE_ID.fullmatch(target_id):
            raise TargetIdentityV3Error("invalid SusVibes target identity")
        if target_id in DEVELOPMENT_IDS and self.purpose != DEVELOPMENT_FIXTURE_PURPOSE:
            raise PermissionError("development target is permanently excluded from confirmation")
        if target_id not in self.target_ids:
            if self.purpose == FROZEN_UNIVERSE_PURPOSE:
                raise PermissionError("target is outside the frozen 181-ID universe")
            raise PermissionError("target is outside the declared synthetic fixture scope")

    @property
    def confirmatory(self) -> bool:
        return self.purpose == FROZEN_UNIVERSE_PURPOSE

    @classmethod
    def synthetic_fixture(cls, target_ids: tuple[str, ...]) -> "TargetIdentityScope":
        values = tuple(sorted(set(target_ids)))
        if not values:
            raise TargetIdentityV3Error("synthetic fixture scope is empty")
        for target_id in values:
            if not _INSTANCE_ID.fullmatch(target_id) or target_id in DEVELOPMENT_IDS:
                raise TargetIdentityV3Error("invalid or development synthetic fixture identity")
        return cls(
            target_ids=frozenset(values),
            purpose=SYNTHETIC_FIXTURE_PURPOSE,
            identity_list_sha256=_ids_sha256(values),
            manifest_sha256=None,
        )

    @classmethod
    def development_fixtures(cls) -> "TargetIdentityScope":
        """Permit the five permanent exclusions only in development validation."""

        return cls(
            target_ids=frozenset(DEVELOPMENT_IDS),
            purpose=DEVELOPMENT_FIXTURE_PURPOSE,
            identity_list_sha256=_ids_sha256(tuple(DEVELOPMENT_IDS)),
            manifest_sha256=None,
        )


def load_frozen_target_scope(manifest_path: Path) -> TargetIdentityScope:
    """Load only the frozen opaque-ID artifact and verify its exact identity."""

    path = Path(manifest_path)
    payload = path.read_bytes()
    manifest_sha256 = hashlib.sha256(payload).hexdigest()
    if manifest_sha256 != FROZEN_UNSEEN_MANIFEST_SHA256:
        raise TargetIdentityV3Error("frozen unseen-target manifest hash mismatch")
    value = json.loads(payload)
    if not isinstance(value, dict) or set(value) != _MANIFEST_FIELDS:
        raise TargetIdentityV3Error("frozen unseen-target manifest fields changed")
    if value["schema"] != "cmpilot-susvibes-unseen-target-universe-v1":
        raise TargetIdentityV3Error("frozen unseen-target manifest schema mismatch")
    if value["benchmark_revision"] != SUSVIBES_REVISION:
        raise TargetIdentityV3Error("frozen unseen-target revision mismatch")
    if value["raw_task_count"] != SUSVIBES_TASK_COUNT:
        raise TargetIdentityV3Error("frozen SusVibes task count changed")
    if tuple(value["development_ids"]) != DEVELOPMENT_IDS:
        raise TargetIdentityV3Error("development exclusions changed")
    if value["development_target_count"] != len(DEVELOPMENT_IDS):
        raise TargetIdentityV3Error("development exclusion count changed")
    if value["enumeration_fields_read"] != ["instance_id"]:
        raise TargetIdentityV3Error("unseen universe contains non-identity fields")
    if (
        value["candidate_specific_implementation_details_inspected"] is not False
        or value["candidate_specific_security_details_inspected"] is not False
        or value["confirmatory_screening_authorized"] is not False
    ):
        raise TargetIdentityV3Error("frozen unseen universe evidence state changed")
    ids = tuple(value["unseen_ids"])
    if len(ids) != FROZEN_UNSEEN_TARGET_COUNT or ids != tuple(sorted(set(ids))):
        raise TargetIdentityV3Error("frozen unseen-target identity set changed")
    if set(ids) & set(DEVELOPMENT_IDS):
        raise TargetIdentityV3Error("frozen unseen universe contains a development target")
    observed_ids_hash = _ids_sha256(ids)
    if (
        observed_ids_hash != FROZEN_UNSEEN_IDS_SHA256
        or value["unseen_ids_sha256"] != FROZEN_UNSEEN_IDS_SHA256
        or value["unseen_target_count"] != FROZEN_UNSEEN_TARGET_COUNT
    ):
        raise TargetIdentityV3Error("frozen unseen-target identity hash mismatch")
    return TargetIdentityScope(
        target_ids=frozenset(ids),
        purpose=FROZEN_UNIVERSE_PURPOSE,
        identity_list_sha256=observed_ids_hash,
        manifest_sha256=manifest_sha256,
    )


@dataclass
class TargetArtifactRouter:
    """Construct parameterized paths and count any later content reads."""

    public_root: PurePosixPath
    sealed_root: PurePosixPath
    content_loader: Callable[[PurePosixPath], bytes] | None = None
    content_reads: int = field(default=0, init=False)

    def routes(
        self, target_id: str, *, scope: TargetIdentityScope
    ) -> dict[str, str]:
        scope.validate(target_id)
        return {
            "target_id": target_id,
            "public_workspace": (self.public_root / target_id).as_posix(),
            "sealed_evidence_handle": (self.sealed_root / target_id).as_posix(),
        }

    def read_content(
        self,
        target_id: str,
        relative_path: str,
        *,
        scope: TargetIdentityScope,
    ) -> bytes:
        scope.validate(target_id)
        relative = PurePosixPath(relative_path)
        if relative.is_absolute() or not relative.parts or ".." in relative.parts:
            raise TargetIdentityV3Error("unsafe target content path")
        if self.content_loader is None:
            raise PermissionError("no target content loader is configured")
        self.content_reads += 1
        return self.content_loader(self.public_root / target_id / relative)


def build_b_only_representation_v3(
    reader: AuditedWorkspaceReader, *, scope: TargetIdentityScope
) -> dict[str, object]:
    """Run the existing extractor with the V3 target-identity boundary."""

    return build_b_only_representation(
        reader, target_identity_validator=scope.validate
    )
