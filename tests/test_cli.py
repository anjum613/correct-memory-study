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


def test_adapter_preflight_cli_uses_fixed_dummy_endpoint(tmp_path) -> None:
    artifacts = tmp_path / "artifacts"
    with patch("cmpilot.__main__.run_adapter_preflight", return_value=0) as preflight:
        result = main(
            [
                "adapter-preflight",
                "--mini-python",
                "/mini/python",
                "--artifact-dir",
                str(artifacts),
            ]
        )

    assert result == 0
    config = preflight.call_args.args[0]
    assert config.base_url == "http://127.0.0.1:9/v1"
    assert config.mini_python == "/mini/python"
