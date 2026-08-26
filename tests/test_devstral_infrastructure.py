from __future__ import annotations

import subprocess
from pathlib import Path


REPOSITORY = Path(__file__).parents[1]


def test_environment_lock_pins_required_runtime_versions() -> None:
    requirements = (
        REPOSITORY / "environments" / "devstral-small-2507" / "requirements-cu128.txt"
    ).read_text()

    for requirement in (
        "packaging==25.0",
        "torch==2.7.1",
        "transformers==4.53.2",
        "vllm==0.10.0",
        "tokenizers==0.21.2",
        "huggingface-hub[hf_xet]==0.33.4",
        "mistral-common[audio,hf-hub,image]==1.8.4",
        "xgrammar==0.1.21",
        "outlines-core==0.2.10",
    ):
        assert requirement in requirements
    assert "https://download.pytorch.org/whl/cu128" in requirements


def test_new_shell_and_slurm_scripts_have_valid_bash_syntax() -> None:
    scripts = [
        REPOSITORY / "scripts" / "create_devstral_environment.sh",
        REPOSITORY / "scripts" / "start_devstral_vllm.sh",
        REPOSITORY / "slurm" / "devstral_smoke_2gpu.sbatch",
    ]

    subprocess.run(["bash", "-n", *(str(path) for path in scripts)], check=True)


def test_smoke_job_is_bounded_two_gpu_and_non_confirmatory() -> None:
    script = (REPOSITORY / "slurm" / "devstral_smoke_2gpu.sbatch").read_text()

    assert "#SBATCH --nodes=1" in script
    assert "#SBATCH --gpus=2" in script
    assert "#SBATCH --constraint=a100" in script
    assert "#SBATCH --time=00:45:00" in script
    assert "export CMPILOT_TENSOR_PARALLEL_SIZE=2" in script
    assert "--profile devstral-small-2507" in script
    assert "non-confirmatory" in script
    assert "--array" not in script
    assert "CMPILOT_TENSOR_PARALLEL_SIZE=4" not in script


def test_action_protocol_diagnostic_never_executes_commands() -> None:
    source = (REPOSITORY / "scripts" / "diagnose_action_protocol.py").read_text()

    assert '"commands_executed_by_diagnostic": 0' in source
    assert "subprocess" not in source
    assert "os.system" not in source
    assert "literal_placeholder_rejected" in source
    assert "multiple_actions_rejected" in source
