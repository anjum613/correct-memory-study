from __future__ import annotations

from unittest.mock import patch

import pytest

from cmpilot.__main__ import main


def test_smoke_requires_explicit_live_authorization() -> None:
    with patch("cmpilot.__main__.run_smoke") as run:
        with pytest.raises(SystemExit) as error:
            main(["smoke"])

    assert error.value.code == 2
    run.assert_not_called()


def test_smoke_dry_run_never_calls_live_runner() -> None:
    with patch("cmpilot.__main__.dry_run", return_value=0) as dry, patch("cmpilot.__main__.run_smoke") as run:
        assert main(["smoke", "--dry-run"]) == 0

    dry.assert_called_once()
    run.assert_not_called()
