# vLLM smoke environment diagnosis

This diagnosis was performed on the login node against the existing isolated
environment:

    /home/s224049759/environments/vllm-smoke

No package was installed, removed, patched, or shimmed.

## Versions and imports

| Item | Result |
| --- | --- |
| Python | 3.12.8 |
| vLLM metadata | 0.6.1.post2 |
| outlines metadata | 0.0.46 |
| lm-format-enforcer metadata | 0.10.6 |
| pyairports metadata | 0.0.1 |
| import vllm | PASS (the login-node CUDA-library warning is expected without a GPU) |
| import lmformatenforcer | PASS |
| import outlines | FAIL: ModuleNotFoundError: No module named 'pyairports' |
| import pyairports | FAIL: ModuleNotFoundError: No module named 'pyairports' |
| python -m pip check | PASS: No broken requirements found. |

The installed pyairports distribution declares version 0.0.1 and has no
dependencies, but its recorded files contain sample/ and
pyairports-0.0.1.dist-info/; they do not contain an importable
pyairports/ module. Its metadata lists the author as John Doe and the author
email as males-folds0a@icloud.com.

The project tree has no file or directory whose name contains pyairport.
The environment contains only pyairports-0.0.1.dist-info, not a local
pyairports shim. No package files were manually changed.

## Package evidence

The complete frozen package set is preserved in the immutable job-24579
artifact:

    /home/s224049759/run-artifacts/vllm-smoke-2/24579/pip-freeze.txt

The current environment's sorted pip freeze is compared against that file
during the preflight for this change. Relevant entries are:

    vllm==0.6.1.post2
    torch==2.4.0
    triton==3.0.0
    outlines==0.0.46
    lm-format-enforcer==0.10.6
    pyairports==0.0.1

## Resolution used for the next approved retry

vLLM serve --help for vLLM 0.6.1.post2 explicitly accepts:

    --guided-decoding-backend {outlines,lm-format-enforcer}

The Slurm launch script therefore explicitly selects
--guided-decoding-backend lm-format-enforcer. This avoids importing outlines
for the ordinary chat-completions smoke request; it does not create or modify
a pyairports package.
