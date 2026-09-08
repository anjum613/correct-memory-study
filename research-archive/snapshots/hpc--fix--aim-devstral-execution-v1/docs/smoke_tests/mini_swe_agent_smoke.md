# mini-SWE-agent smoke test 3

This is a one-trajectory engineering smoke test. It does not use procedural
memory, inject hints or a reference patch, compare treatments, or make a
benchmark claim.

## Verified mini-SWE-agent interface

The agent runs in the dedicated environment:

    /home/s224049759/environments/mini-swe-agent-smoke

It pins `mini-swe-agent==2.4.6`. The installed `mini --help`, package source,
and shipped configuration were inspected before implementation. Version 2.4.6
provides:

- `DefaultAgent` with `step_limit`, `wall_time_limit_seconds`, and native
  trajectory output;
- `LocalEnvironment` with a per-command timeout;
- `LitellmTextbasedModel` for the fenced-text action format used by its shipped
  `default.yaml` prompt;
- LiteLLM `api_base` configuration for an OpenAI-compatible endpoint.

The direct installation pin is recorded in
`configs/environments/mini-swe-agent-smoke-requirements.txt`; each live run
also preserves the complete resolved environment freeze.

The text-action backend is used deliberately because the fixed vLLM command
does not enable an automatic tool-call parser. It is a shipped, supported
mini-SWE-agent 2.4.6 model class, not a custom protocol.

The project override is in
`configs/agent/mini_swe_agent_smoke.yaml`. It sets 15 steps, a 450-second
internal wall limit, a 60-second shell-command timeout, temperature zero, and
the loopback endpoint. The harness also enforces a 480-second outer agent
timeout.

## Exact agent invocation

The Slurm script invokes the repository harness once:

    PYTHONPATH=/home/s224049759/projects/correct-memory-study/src:/home/s224049759/projects/correct-memory-study \
      /home/s224049759/environments/cmpilot-conda/bin/python -m cmpilot smoke \
      --live \
      --base-url http://127.0.0.1:8000/v1 \
      --model Qwen/Qwen2.5-Coder-1.5B-Instruct \
      --mini-python /home/s224049759/environments/mini-swe-agent-smoke/bin/python \
      --runs-root /tmp/$USER/mini-swe-smoke-$SLURM_JOB_ID/agent-runs \
      --agent-timeout 480

The harness generates and invokes one adapter command:

    /home/s224049759/environments/mini-swe-agent-smoke/bin/python \
      <immutable-run-directory>/mini_swe_adapter.py

The generated adapter loads mini-SWE-agent's shipped `default.yaml`, merges
only the reviewed smoke configuration, uses `DefaultAgent`, and records the
resolved configuration and native trajectory. Its audited local environment
records each command, combined command output, return code, exception, and
the Git diff after the command.

## Server configuration

The same validated smoke-test-2 server command is used:

    vllm serve Qwen/Qwen2.5-Coder-1.5B-Instruct \
      --revision 2e1fd397ee46e1388853d2af2c993145b0f1098a \
      --host 127.0.0.1 \
      --port 8000 \
      --dtype bfloat16 \
      --max-model-len 4096 \
      --gpu-memory-utilization 0.70 \
      --guided-decoding-backend lm-format-enforcer

The vLLM environment is activated and checked but never installed into or
upgraded by this smoke test. The agent environment is separate.

## Isolation and artifacts

The calculator template is copied into a fresh Git repository beneath
`/tmp/$USER/mini-swe-smoke-$SLURM_JOB_ID`. Initial tests must fail from the
deliberate `NotImplementedError`. After the single agent trajectory, the
harness independently runs the complete calculator suite, records hashes and
the final patch, and verifies that the source template is unchanged.

Each job writes immutable evidence under:

    /home/s224049759/run-artifacts/mini-swe-smoke-3/<job-id>/

The batch trap always attempts graceful vLLM shutdown, captures a final GPU
snapshot, checks for remaining server and agent processes, and produces
`result.json` even when an earlier stage fails. No automatic retry is made.
