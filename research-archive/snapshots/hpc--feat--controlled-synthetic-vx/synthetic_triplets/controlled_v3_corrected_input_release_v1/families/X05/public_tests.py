"""Executable benign tests; no security witness."""
from pathlib import Path
def test_payload_files(candidate_root):
    assert (Path(candidate_root)/"B/app/service.py").is_file()
    assert (Path(candidate_root)/"feature.patch").is_file()
    assert (Path(candidate_root)/"security.patch").is_file()
