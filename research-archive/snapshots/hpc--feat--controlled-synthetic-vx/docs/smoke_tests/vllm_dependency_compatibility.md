# vLLM guided-decoding dependency compatibility

## Scope

This document records the narrow environment correction required after
smoke-test-2 job 24617. It does not authorize another Slurm submission.
Jobs 24570, 24578, 24579, and 24617 and their immutable artifacts remain
unchanged.

## Observed failure

Job 24617 proved allocation, GPU access, model caching, BF16 loading, vLLM
startup, the health endpoint, the models endpoint, and clean shutdown. Its
chat-completions request failed before generation when lm-format-enforcer
imported LogitsWarper from transformers.generation.logits_process; the
installed Transformers 4.57.6 no longer exposed that import.

This is a dependency compatibility failure, not a GPU, model, model-cache, or
vLLM-serving failure. The exact traceback is preserved under:

    /home/s224049759/run-artifacts/vllm-smoke-2/24617/server.stderr.log

## Corrected direct requirements

configs/environments/vllm-smoke-requirements.txt pins the smallest supported
combination:

    vllm==0.6.1.post2
    lm-format-enforcer==0.10.6
    transformers==4.45.2

The lm-format-enforcer version stays at vLLM 0.6.1.post2's required version.
No pyairports module, shim, or package-file modification is introduced.
The vLLM server continues to select lm-format-enforcer explicitly, so its
ordinary chat request does not select outlines.

## Re-resolution and regression check

The isolated environment is re-resolved from the direct requirements using
pip's eager strategy and a forced reinstall. This permits pip to select the
tokenizers and other dependency versions compatible with Transformers 4.45.2
rather than retaining packages selected for Transformers 4.57.6.

Run the compatibility regression with the isolated environment:

    /home/s224049759/environments/vllm-smoke/bin/python \
      scripts/check_vllm_guided_decoding_deps.py

The regression asserts the three direct versions and imports both LogitsWarper
and lmformatenforcer.integrations.transformers.
build_transformers_prefix_allowed_tokens_fn. It must pass, along with
python -m pip check, before any future GPU retry.

## Future GPU retry preflight

The Slurm script records the regression output in
guided-decoding-dependency-check.txt before it launches the server. The
server command remains:

    vllm serve Qwen/Qwen2.5-Coder-1.5B-Instruct \
      --revision 2e1fd397ee46e1388853d2af2c993145b0f1098a \
      --host 127.0.0.1 --port 8000 --dtype bfloat16 \
      --max-model-len 4096 --gpu-memory-utilization 0.70 \
      --guided-decoding-backend lm-format-enforcer

No future smoke-test-2 job is submitted by this change; explicit approval is
required after the login-node checks and full CPU suite pass.

## Final resolved state

The original eager-install wording above is superseded. Transformers was
re-resolved to 4.45.2, selecting tokenizers 0.20.3 instead of retaining the
version selected for Transformers 4.57.6. The environment retains NumPy
1.26.4 and fsspec 2026.6.0 as transitive constraints because vLLM, outlines,
datasets, and mistral-common declare bounds that exclude the newer releases.
This does not change the three direct compatibility pins.

configs/environments/vllm-smoke-freeze.txt records the complete resolved
package set and has SHA-256
69720f260db96634ff23641731b7c70f4a37068bf108719346b153de4d84d0a7.
