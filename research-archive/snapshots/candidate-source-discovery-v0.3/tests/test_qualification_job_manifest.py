from __future__ import annotations

import hashlib
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


def test_regenerated_manifest_includes_every_late_finalizer_write(
    tmp_path: Path, monkeypatch
) -> None:
    (tmp_path / "runner.exit").write_text("1\n", encoding="ascii")
    monkeypatch.setattr("sys.argv", ["qualification_job_manifest.py", str(tmp_path)])
    assert main() == 0

    late = {
        "artifact-manifest.exit": b"0\n",
        "batch-exit-code.txt": b"1\n",
        "outer-finalizer-result.json": b'{"batch_exit_code": 1}\n',
    }
    for relative, content in late.items():
        (tmp_path / relative).write_bytes(content)

    assert main() == 0

    rows = {
        relative: digest
        for digest, relative in (
            line.split("  ", 1)
            for line in (tmp_path / "SHA256SUMS").read_text().splitlines()
        )
    }
    assert set(rows) == {"runner.exit", *late}
    for relative in rows:
        assert rows[relative] == hashlib.sha256(
            (tmp_path / relative).read_bytes()
        ).hexdigest()
    result = json.loads((tmp_path / "job-manifest.json").read_text())
    assert result["entry_count"] == len(rows)
    assert result["pass"] is True
