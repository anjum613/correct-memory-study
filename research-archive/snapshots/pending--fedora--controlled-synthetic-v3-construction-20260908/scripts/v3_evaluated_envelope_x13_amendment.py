"""X13 wording-only overlay; no admission, construction, or execution API."""
from __future__ import annotations

import copy
import json
from pathlib import Path

from scripts import v3_evaluated_envelope as base

AMENDMENT_ID = "controlled-synthetic-v3-evaluated-envelope-x13-wording-amendment-v1"
DIRECTORY = Path("protocols") / AMENDMENT_ID
BASE_COMMIT = "51ddbc9e02abb0a665c320de7e68e10b8540ad7c"
BASE_MANIFEST_SHA256 = "4bed9d4d6464903312f81cfebd89f094df04a4d7b9b1df4b54fdfac380468e33"
BASE_CONTENT_SHA256 = "a07f20f2d59ecfd49b09d173e8cb7c49c9640656d56bb4cc168b641e4e679c2c"
OLD_X13_SHA256 = "2479af3a578a020e0b034646516ea0232e2fa10d4597e14deda61ff4a598dda9"
OLD_PHRASE = "define rounding and range policy prospectively."
NEW_PHRASE = "follow the declared rounding and range policy."
TASK_PATH = "exports/X13/target_request.txt"
CODE_FILES = (
    "scripts/v3_evaluated_envelope_x13_amendment.py",
    "scripts/freeze_v3_evaluated_envelope_x13_amendment.py",
    "tests/test_v3_evaluated_envelope_x13_amendment.py",
)


def corrected_x13_task(original: bytes) -> bytes:
    """Accept only the exact frozen original, not arbitrary task/spec content."""
    if base.digest(original) != OLD_X13_SHA256 or original.count(OLD_PHRASE.encode()) != 1:
        raise base.EnvelopeError("X13 wording overlay requires exact original task")
    return original.replace(OLD_PHRASE.encode(), NEW_PHRASE.encode(), 1)


def generated_overlay(root: Path) -> dict[str, bytes]:
    """Pure generation. No scientific field, public file or memory is rewritten."""
    base.verify_contract(root, expected_manifest_sha256=BASE_MANIFEST_SHA256)
    original = root / base.DIRECTORY
    task = corrected_x13_task((original / TASK_PATH).read_bytes())
    index = json.loads((original / "export_index.json").read_bytes())
    packets = json.loads((original / "memory_packets.json").read_bytes())
    index["X13"]["target_request_sha256"] = base.digest(task)
    index["X13"]["messages_sha256"] = {
        condition: base.digest(base.canonical(base.render_messages(
            "X13", condition, task.decode(), packets)))
        for condition in base.CONDITIONS
    }
    return {TASK_PATH: task, "effective_export_index.json": base.canonical(index)}


def expected_binding_changes() -> list[str]:
    return ["X13.target_request_sha256"] + [
        "X13.messages_sha256." + condition for condition in base.CONDITIONS
    ]


def verify_amendment(root: Path, *, expected_manifest_sha256: str) -> dict:
    directory = root / DIRECTORY
    manifest_path = directory / "amendment_manifest.json"
    if not base._regular_beneath(manifest_path, root):
        raise base.EnvelopeError("amendment manifest is not a regular in-root file")
    raw = manifest_path.read_bytes()
    if base.digest(raw) != expected_manifest_sha256:
        raise base.EnvelopeError("amendment manifest differs from trusted external binding")
    manifest = json.loads(raw)
    if (manifest["amendment_id"] != AMENDMENT_ID
            or manifest["base_contract_commit"] != BASE_COMMIT
            or manifest["base_manifest_sha256"] != BASE_MANIFEST_SHA256
            or manifest["base_content_sha256"] != BASE_CONTENT_SHA256):
        raise base.EnvelopeError("amendment/base identity mismatch")
    inventory = manifest["inventory"]
    if (manifest["exact_inventoried_file_count"] != len(inventory)
            or manifest["content_sha256"] != base.digest(base.canonical(inventory))):
        raise base.EnvelopeError("amendment inventory mismatch")
    for name, expected in inventory.items():
        path = root / name
        if not base._regular_beneath(path, root) or base.digest(path.read_bytes()) != expected:
            raise base.EnvelopeError("amendment member changed: " + name)
    actual = {p.relative_to(root).as_posix() for p in directory.rglob("*")
              if p.is_file() or p.is_symlink()}
    exempt = {(DIRECTORY / name).as_posix()
              for name in ("amendment_manifest.json", "commit_receipt.json")}
    expected = {name for name in inventory if name.startswith(DIRECTORY.as_posix() + "/")}
    if actual - exempt != expected:
        raise base.EnvelopeError("unexpected/missing amendment artifact")
    for name, data in generated_overlay(root).items():
        if (directory / name).read_bytes() != data:
            raise base.EnvelopeError("overlay changes more than fixed X13 wording: " + name)
    return manifest


def load_bound_context(root: Path, family: str, condition: str, service: bytes,
                       *, expected_b_sha256: str,
                       expected_amendment_sha256: str) -> tuple[list[dict], dict[str, bytes]]:
    """Inspection/assembly only. Admission and final isolated evaluator still required.

    Advisory ratings and amendment documentation are never rendering inputs.
    Their hashes are verified as provenance; their contents are not interpreted.
    """
    verify_amendment(root, expected_manifest_sha256=expected_amendment_sha256)
    messages, files = base.load_bound_context(
        root, family, condition, service, expected_b_sha256=expected_b_sha256,
        expected_contract_sha256=BASE_MANIFEST_SHA256)
    if family == "X13":
        old_task = (root / base.DIRECTORY / TASK_PATH).read_text()
        new_task = (root / DIRECTORY / TASK_PATH).read_text()
        if not messages[1]["content"].startswith(old_task):
            raise base.EnvelopeError("unexpected base message layout")
        messages = copy.deepcopy(messages)
        messages[1]["content"] = new_task + messages[1]["content"][len(old_task):]
    index = json.loads((root / DIRECTORY / "effective_export_index.json").read_bytes())
    if base.digest(base.canonical(messages)) != index[family]["messages_sha256"][condition]:
        raise base.EnvelopeError("amended message binding drift")
    return messages, files
