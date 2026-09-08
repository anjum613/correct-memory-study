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


def test_model_profile_arguments_print_exact_served_identity(capsys) -> None:
    assert main(["model-profile-arguments", "--profile", "devstral-small-2507"]) == 0

    arguments = capsys.readouterr().out.splitlines()
    assert arguments[0] == "mistralai/Devstral-Small-2507"
    assert arguments[arguments.index("--served-model-name") + 1] == "cmpilot-devstral-small-2507-bd165ab26ceb"
    assert arguments[arguments.index("--tensor-parallel-size") + 1] == "2"
