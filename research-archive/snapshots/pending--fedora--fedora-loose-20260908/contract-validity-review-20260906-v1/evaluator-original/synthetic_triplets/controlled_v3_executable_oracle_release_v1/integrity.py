"""Exact release, scientific-input, and constructor-envelope integrity checks."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import stat

from .candidate_control import pristine_ledger, validate_pristine_ledger
from .contracts import (CONSTRUCTOR_ATTEMPT_LIMIT, EXCLUDED, FAMILY_ORDER,
                        IN_SCOPE, RELEASE_ID)


PACKAGE_RELATIVE = Path("synthetic_triplets/controlled_v3_executable_oracle_release_v1")
MANIFEST_RELATIVE = PACKAGE_RELATIVE / "release_manifest.json"
NONINVENTORIED_PACKAGE_FILES = {"release_manifest.json", "commit_receipt.json"}
RELEASE_TESTS = (
    "tests/test_v3_candidate_control.py",
    "tests/test_v3_executable_oracle_release.py",
    "tests/test_v3_executable_release_integrity.py",
    "tests/test_v3_new_reference_matrices.py",
    "tests/test_v3_x02_executable.py",
    "tests/test_v3_x02_full_contract.py",
)

PROTECTED = {
    "synthetic_triplets/controlled_v3_expansion/admission_ledger.json": "3ce5a28ccad74c83460cbb96d888074bb36e79d5adb98f56aab59b656d9dbbaa",
    "synthetic_triplets/controlled_v3_expansion/construction_input_release.json": "5c00240c044eb0d66d4bc7f4cb96336bf9e0cfa6efda1528b2a6eea43ad5b861",
    "synthetic_triplets/controlled_v3_expansion/family_specs.json": "dd1665df9aa51bdf4cc52202f37ebbc98b680f1f97c97787dfd92435454a8df5",
    "synthetic_triplets/controlled_v3_expansion/freeze_manifest.json": "a2b6eaf731012feffeb03e5f2024d7fd7cc875f2d7d0f56846761f65c2dcb2dc",
    "synthetic_triplets/controlled_v3_expansion/preconstruction_attestation.json": "198d53110de52b0136d2709176de809eb6cf6ecf600072b49c18bcd1e9181977",
    "synthetic_triplets/controlled_v3_expansion/protocol.json": "6cc383a3a6ab6bea1decf991c835fcfad47becd508462ef31ed47e34fa8c7994",
    "synthetic_triplets/controlled_v3_expansion/README.md": "73756f72f493921aaefd5824f62ca7cbf5a8b28f239c0b4fa59d53cddc8007c4",
    "synthetic_triplets/controlled_v3_expansion/review_template.json": "78cfb53868f490618421011b25611b8b9306d5552e74baa7717a5e8f80ca2672",
    "protocols/controlled-synthetic-v3-full-pool-amendment.json": "754281f16a0d7e588272ee80464475fc7cf2545fe4aa8ddb6943e35c15d06b7c",
    "synthetic_triplets/controlled_v2_final/human_review_resolution.json": "9b7f4bfc6ac5111a5a9dc227c2d1df8fb2e552b18de91c79209915cc28487235",
    "synthetic_triplets/controlled_v3_corrected_input_release_v1/release_manifest.json": "59cfd1575f5922ff2f2a4aaf4b3b50f84addd4ee605e17f86ab8e1076a511e66",
    "synthetic_triplets/controlled_v3_corrected_input_release_v1/supersession_notice.json": "db3e4271d521e62550bb88fbe3d4a35e5633d32343a05eb5e6f9163dcd37e7fe",
    "synthetic_triplets/controlled-synthetic-v3-validator-complete-release-v1/release_manifest.json": "c52cccc071e1a886ac364e58ba56c7ad05c69be221d9082244c9c44cb935c626",
    "protocols/controlled-synthetic-v3-x02-x22-clarification-v1/manifest.json": "167251744b87c55f23ce06b61a70891c1192b7581c357a7d5458c22e0f94e1bc",
    "protocols/controlled-synthetic-v3-x02-x22-clarification-v1/X02.md": "544f4d8ec8df9c94e5641cd6eb684000ea4e5e71685a34afa185d9d953946955",
    "protocols/controlled-synthetic-v3-x02-x22-clarification-v1/X02-machine.md": "1b5f7a37ce05fb2d929f1d0f9d885ed102cfd48069911e279501b7fafe7d7354",
    "protocols/controlled-synthetic-v3-x02-x22-clarification-v1/X22.md": "98fd92b88de885198f2df032083fffb202d43985f4bba41d6f4d08fcdaea00ac",
    "protocols/controlled-synthetic-v3-x19-exclusion-v1/amendment.json": "cc866d26924b15bf8dd9217774019e38310d25d60ac1cd23265a23e2ba23026e",
    "protocols/controlled-synthetic-v3-x19-exclusion-v1/manifest.json": "0324a7f7d38618fbca32c74d82c5cab1d293bcf2c9ad24a4966f834f6ad544fb",
    "protocols/controlled-synthetic-v3-x25-exclusion-v1/amendment.json": "466375830babbe809ad585097194b0fcf5818e7c517ed6ec65e0bee6433de9ad",
    "protocols/controlled-synthetic-v3-x25-exclusion-v1/manifest.json": "42e72db8040e47277797c6208aba14fdbcc6ad3a8191d9caedaf646e3af759a3",
}


class ReleaseIntegrityError(ValueError):
    pass


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def repository_root():
    return Path(__file__).resolve().parents[2]


def release_inventory_paths(root=None):
    root = repository_root() if root is None else Path(root)
    package = root / PACKAGE_RELATIVE
    paths = []
    for path in package.rglob("*"):
        relative_package = path.relative_to(package)
        if "__pycache__" in relative_package.parts or path.suffix == ".pyc":
            continue
        metadata = path.lstat()
        if stat.S_ISDIR(metadata.st_mode) and not path.is_symlink():
            continue
        if not stat.S_ISREG(metadata.st_mode) or path.is_symlink():
            raise ReleaseIntegrityError(f"non-regular release path: {path.relative_to(root)}")
        if relative_package.as_posix() in NONINVENTORIED_PACKAGE_FILES:
            continue
        paths.append(path.relative_to(root).as_posix())
    for relative in RELEASE_TESTS:
        path = root / relative
        if not path.is_file() or path.is_symlink():
            raise ReleaseIntegrityError(f"missing release test: {relative}")
        paths.append(relative)
    return tuple(sorted(paths))


def hash_inventory(root=None):
    root = repository_root() if root is None else Path(root)
    return {relative: sha256(root / relative) for relative in release_inventory_paths(root)}


def content_digest(inventory):
    encoded = json.dumps(inventory, sort_keys=True, separators=(",", ":")).encode("ascii")
    return hashlib.sha256(encoded).hexdigest()


def _check_hashes(root, inventory, label):
    for relative, expected in inventory.items():
        path = root / relative
        if not path.is_file() or path.is_symlink():
            raise ReleaseIntegrityError(f"{label} path missing or linked: {relative}")
        actual = sha256(path)
        if actual != expected:
            raise ReleaseIntegrityError(f"{label} changed: {relative}")


def _verify_preserved_evidence(root):
    x19 = json.loads((root / "protocols/controlled-synthetic-v3-x19-exclusion-v1/amendment.json").read_text())
    x25 = json.loads((root / "protocols/controlled-synthetic-v3-x25-exclusion-v1/amendment.json").read_text())
    if list(x19["excluded_families"]) != ["X19"]:
        raise ReleaseIntegrityError("X19 exclusion changed")
    if x25["newly_excluded_family"]["family_id"] != "X25":
        raise ReleaseIntegrityError("X25 exclusion changed")
    for document in (x19, x25):
        if document["constructor_attempts"] or document["evaluated_agent_outcomes"] or document["actual_human_reviews"]:
            raise ReleaseIntegrityError("pre-construction exclusion records activity")
    x19_report = root / x19["excluded_families"]["X19"]["evidence_path"]
    if sha256(x19_report) != x19["excluded_families"]["X19"]["evidence_sha256"]:
        raise ReleaseIntegrityError("X19 evidence changed")
    for relative, record in x25["preservation"]["x25_diagnostic_snapshot"].items():
        if sha256(root / relative) != record["sha256"] or (root / relative).stat().st_size != record["bytes"]:
            raise ReleaseIntegrityError(f"X25 evidence changed: {relative}")


def _verify_scientific_contract(root):
    specification_document = json.loads(
        (root / "synthetic_triplets/controlled_v3_expansion/family_specs.json").read_text())
    specifications = specification_document["specifications"]
    if tuple(row["family_id"] for row in specifications) != FAMILY_ORDER:
        raise ReleaseIntegrityError("frozen family order changed")
    if any(row["constructor_attempt_limit"] != CONSTRUCTOR_ATTEMPT_LIMIT for row in specifications):
        raise ReleaseIntegrityError("frozen constructor cap changed")
    by_id = {row["family_id"]: row for row in specifications}
    package = root / PACKAGE_RELATIVE
    actual_agent_families = tuple(sorted(path.name for path in (package / "agent_inputs").iterdir()
                                         if path.is_dir() and path.name.startswith("X")))
    actual_researcher_families = tuple(sorted(path.name for path in (package / "researcher_tests").iterdir()
                                              if path.is_dir() and path.name.startswith("X")))
    if actual_agent_families != IN_SCOPE or actual_researcher_families != IN_SCOPE:
        raise ReleaseIntegrityError("generated family envelope differs from prospective in-scope order")
    for family_id in IN_SCOPE:
        task = json.loads((package / "agent_inputs" / family_id / "task.json").read_text())
        if (task["family_id"] != family_id
                or task["frozen_order"] != by_id[family_id]["frozen_order"]
                or task["constructor_attempt_limit"] != CONSTRUCTOR_ATTEMPT_LIMIT
                or task["scientific_specification"] != by_id[family_id]):
            raise ReleaseIntegrityError(f"generated task changed scientific contract: {family_id}")
    resolution = json.loads(
        (root / "synthetic_triplets/controlled_v2_final/human_review_resolution.json").read_text())
    retained = tuple(row["family_id"] for row in resolution["retained_families"])
    if retained != ("F01", "F02", "F04", "F08", "F17", "F20"):
        raise ReleaseIntegrityError("permanently retained V2 cohort changed")


def _verify_agent_envelope(root):
    package = root / PACKAGE_RELATIVE
    agent = package / "agent_inputs"
    scan = [path for path in (agent / "shared").rglob("*") if path.is_file()]
    scan.extend(path for family in IN_SCOPE for path in (
        agent / family / "source_service.py",
        agent / family / "source_service.csirpy",
        agent / family / "public_tests.py",
    ) if path.exists())
    forbidden = (b"_repair", b"replace_bound", b"reserve_global", b"atomic_commit",
                 b"target_invariant", b"sealed_", b"InvariantViolation", b", observe")
    for path in scan:
        value = path.read_bytes()
        if any(marker in value for marker in forbidden):
            raise ReleaseIntegrityError(f"constructor-facing repair/witness leakage: {path.relative_to(root)}")
    if any("private" in key.lower() for key in _all_keys(
            json.loads((agent / "shared/public_vectors.json").read_text()))):
        raise ReleaseIntegrityError("private key material appears in public vectors")
    # Path was needed only while building the module's fixed public-vector value;
    # it must not remain as a transitive filesystem capability for candidates.
    from .agent_inputs.shared import agent_crypto
    if hasattr(agent_crypto, "Path"):
        raise ReleaseIntegrityError("constructor crypto runtime exposes filesystem Path")


def _all_keys(value):
    if isinstance(value, dict):
        for key, child in value.items():
            yield str(key)
            yield from _all_keys(child)
    elif isinstance(value, list):
        for child in value:
            yield from _all_keys(child)


def verify_release(root=None):
    root = repository_root() if root is None else Path(root)
    manifest_path = root / MANIFEST_RELATIVE
    if not manifest_path.is_file() or manifest_path.is_symlink():
        raise ReleaseIntegrityError("release manifest missing or linked")
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("release_id") != RELEASE_ID or manifest.get("status") != "CONSTRUCTION_READY":
        raise ReleaseIntegrityError("release identity/status differs")
    inventory = manifest.get("inventory")
    if not isinstance(inventory, dict):
        raise ReleaseIntegrityError("release inventory missing")
    actual_paths = release_inventory_paths(root)
    if tuple(sorted(inventory)) != actual_paths:
        raise ReleaseIntegrityError("exact release file inventory differs")
    if manifest.get("exact_inventoried_file_count") != len(inventory):
        raise ReleaseIntegrityError("inventory count differs")
    _check_hashes(root, inventory, "release file")
    if manifest.get("release_content_sha256") != content_digest(inventory):
        raise ReleaseIntegrityError("release content digest differs")
    _check_hashes(root, PROTECTED, "protected scientific/provenance file")
    if manifest.get("protected_scientific_and_provenance_hashes") != PROTECTED:
        raise ReleaseIntegrityError("recorded protected hash map differs")
    _verify_preserved_evidence(root)
    _verify_scientific_contract(root)
    _verify_agent_envelope(root)
    ledger_path = root / PACKAGE_RELATIVE / "admission_ledger.json"
    validate_pristine_ledger(json.loads(ledger_path.read_text()))
    if (manifest.get("constructor_attempts") != 0
            or manifest.get("evaluated_agent_outcomes") != 0
            or manifest.get("actual_v3_human_reviews") != 0
            or manifest.get("actual_v3_human_review_files") != 0):
        raise ReleaseIntegrityError("manifest records forbidden pre-construction activity")
    return {
        "release_id": RELEASE_ID,
        "status": "CONSTRUCTION_READY",
        "manifest_sha256": sha256(manifest_path),
        "release_content_sha256": manifest["release_content_sha256"],
        "exact_inventoried_file_count": len(inventory),
        "protected_file_count": len(PROTECTED),
        "in_scope_family_count": len(IN_SCOPE),
        "excluded": list(EXCLUDED),
        "constructor_attempts": 0,
        "evaluated_agent_outcomes": 0,
        "actual_v3_human_reviews": 0,
    }
