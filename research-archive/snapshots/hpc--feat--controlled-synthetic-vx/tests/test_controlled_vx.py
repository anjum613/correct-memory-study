"""Independent infrastructure checks; no model calls or acceptance by line count."""
import tempfile
from pathlib import Path

import pytest

from scripts import controlled_vx as vx


def test_frozen_sources_and_base_contracts():
    result = vx.input_preflight()
    assert result['pass'], result
    assert len(result['families']) == 6


def test_no_constructor_owned_baseline():
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        (root/'B').mkdir()
        (root/'B/service.py').write_text('pass\n')
        with pytest.raises(ValueError, match='exactly two'):
            vx.validate('VX01', root)


def test_patch_allowlist_rejects_runtime_edits():
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        patch = '--- a/app/runtime.py\n+++ b/app/runtime.py\n@@ -1 +1 @@\n-a\n+b\n'
        (root/'feature.patch').write_text(patch)
        (root/'security.patch').write_text(patch)
        with pytest.raises(ValueError, match='unapproved'):
            vx.validate('VX01', root)


def test_source_and_target_have_identical_runtime():
    for case in vx.CASES.values():
        assert vx.repo_files(case, True)['app/runtime.py'] == vx.repo_files(case)['app/runtime.py']
        assert set(vx.repo_files(case)) == {'app/__init__.py', 'app/runtime.py', 'app/service.py', 'app/operations.py'}


def test_no_line_count_acceptance_threshold():
    assert vx.MAX_ATTEMPTS == 4
    assert vx.ALLOWED == {'app/service.py', 'app/operations.py'}
    for case in vx.CASES.values():
        assert 'source_valid_assumption' in case and 'target_change' in case


@pytest.mark.parametrize('content', ['import pathlib\n', 'from pathlib import Path\n', 'import socket\n'])
def test_rejects_host_capability_imports(content):
    with tempfile.TemporaryDirectory() as temporary:
        path = Path(temporary)/'service.py'
        path.write_text(content)
        with pytest.raises(ValueError):
            vx.python_policy(path)
