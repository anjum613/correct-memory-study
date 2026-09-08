# Qualification runtime IPC correction after job 25908

Job 25908 is a technical-invalid run and is not a model or repository-competence
failure. vLLM did not start, so no model request, agent action, repository edit, or
immutable-oracle execution occurred.

## Root cause

The qualification launcher put `TMPDIR` at the persistent artifact location
`.../jobs/25908/runtime-scratch`. In the frozen vLLM environment,
`vllm.envs.VLLM_RPC_BASE_PATH` defaults to `tempfile.gettempdir()`, and
`vllm.utils.get_open_zmq_ipc_path()` appends a 36-character UUID. The resulting
filesystem path was 158 bytes, exceeding PyZMQ's reported 107-byte Unix-domain
socket limit.

## Narrow correction

Persistent evidence remains under `/home/s224049759/run-artifacts/...`. Runtime-only
temporary files and vLLM IPC use `/tmp/cmq-<SLURM_JOB_ID>` on the allocated compute
node. The API server and its spawned RPC engine execute on that same node. The
launcher explicitly sets both `TMPDIR` and `VLLM_RPC_BASE_PATH`; nothing required
after the compute job is stored only in `/tmp`.

The runtime directory is task-independent, contains only a bounded numeric job ID,
is created with mode `0700`, and carries an exact job-ownership marker. Cleanup will
remove only the exact `/tmp/cmq-<SLURM_JOB_ID>` directory with a matching marker. It
refuses symlinks, mismatched paths, missing markers, and different ownership.

## Path budget

The platform limit is 107 bytes. Qualification uses a conservative maximum of 90
bytes, leaving 17 bytes of margin. With a representative 20-digit Slurm job ID and
vLLM's 36-character UUID, the longest tested socket filesystem path is 66 bytes
(`72` bytes including the `ipc://` prefix). The CPU gate covers every frozen primary
and reserve task and rejects the artifact-nested form used by job 25908.

This change affects only qualification runtime location, preflight validation, and
cleanup. It does not change model serving arguments, model-agent behavior, prompts,
actions, policy, task inputs, scoring, or any frozen scientific component.
