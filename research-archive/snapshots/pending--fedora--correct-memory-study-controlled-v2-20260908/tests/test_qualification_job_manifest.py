from __future__ import annotations

import json
from pathlib import Path

from scripts.qualification_job_manifest import main


def test_job_manifest_is_self_excluding_and_stable(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "nested").mkdir()
    (tmp_path / "a.txt").write_text("a\n")
    (tmp_path / "nested/b.txt").write_text("b\n")
    monkeypatch.setattr("sys.argv", ["qualification_job_manifest.py", str(tmp_path)])

    assert main() == 0

    result = json.loads((tmp_path / "job-manifest.json").read_text())
    manifest = (tmp_path / "SHA256SUMS").read_text()
    assert result["pass"] is True
    assert result["entry_count"] == 2
    assert "SHA256SUMS" not in manifest
    assert "job-manifest.json" not in manifest
