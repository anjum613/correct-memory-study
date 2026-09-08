import io
import json
from pathlib import Path
import tarfile

import pytest

from cmpilot.v2_snapshot_overlay import (
    SnapshotOverlayError,
    reconstruct_snapshot,
    verify_overlay_archive,
)


ROOT = Path(__file__).parents[1]
MANIFEST = ROOT / "v2/fixtures/snapshot-overlays/manifest.json"
FAMILIES = ("axios-v1", "aim-v1", "httpx-v1")
STATES = ("source", "compatible", "invalidated")


@pytest.mark.parametrize("family", FAMILIES)
def test_content_addressed_overlay_is_exact_and_safe(family: str) -> None:
    record = verify_overlay_archive(MANIFEST, family)
    assert record["archive"].startswith("sha256-")
    assert record["archive"].removeprefix("sha256-").removesuffix(".tar.gz") == record[
        "archive_sha256"
    ]
    assert all(row["state"] in STATES for row in record["files"])


@pytest.mark.parametrize("family", FAMILIES)
@pytest.mark.parametrize("state", STATES)
def test_clean_checkout_reconstructs_exact_v1_input(
    tmp_path: Path, family: str, state: str
) -> None:
    result = reconstruct_snapshot(
        repository_root=ROOT,
        manifest_path=MANIFEST,
        family=family,
        state=state,
        destination=tmp_path / f"{family}-{state}",
    )
    manifest = json.loads(MANIFEST.read_text())
    expected = manifest["families"][family]["states"][state]
    assert result.repository_sha256 == expected["reconstructed_repository_sha256"]
    assert result.overlay_file_count == expected["overlay_file_count"]


def test_archive_path_traversal_is_rejected(tmp_path: Path) -> None:
    archive = tmp_path / "unsafe.tar.gz"
    with tarfile.open(archive, mode="w:gz") as bundle:
        info = tarfile.TarInfo("../escape")
        info.size = 1
        bundle.addfile(info, io.BytesIO(b"x"))
    digest = __import__("hashlib").sha256(archive.read_bytes()).hexdigest()
    manifest = {
        "schema": "cmpilot-v2-snapshot-overlays-v1",
        "families": {
            "unsafe": {
                "archive": archive.name,
                "archive_sha256": digest,
                "files": [
                    {
                        "archive_path": "../escape",
                        "bytes": 1,
                        "sha256": __import__("hashlib").sha256(b"x").hexdigest(),
                    }
                ],
            }
        },
    }
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest))
    with pytest.raises(SnapshotOverlayError, match="unsafe overlay member path"):
        verify_overlay_archive(path, "unsafe")
