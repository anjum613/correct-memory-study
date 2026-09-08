# Qwen32B server-command extraction

The authoritative server command uses the `qwen32b-vllm-argv-v2` schema. Its
JSON file is a top-level array whose members are UTF-8 strings in execution
order. The adjacent run manifest records the schema identifier and SHA-256.
Keeping one argument per JSON item avoids shell quoting and word-splitting.

The batch shell invokes the frozen vLLM Python interpreter to parse and
validate the array with Python's standard `json` module. Python emits a NUL
byte after every argument, and Bash reads the output with
`mapfile -d '' -t SERVER_CMD`. The extractor rejects malformed JSON, empty
arrays, non-string values, NUL bytes, an empty or unexpected executable,
duplicate or missing frozen options, and prohibited serving options. It does
not use `jq`, `eval`, command substitution, or shell word splitting.

Before indexing the array, the shell preserves the Python exit status and
stderr, verifies that `SERVER_CMD` is declared and non-empty, and checks that
its first element names an executable file. Invalid input is classified as
`SERVER_COMMAND_EXTRACTION_FAILURE`; the historical job-25335 missing-`jq`
path is classified separately as
`SERVER_COMMAND_EXTRACTION_DEPENDENCY_FAILURE`.

External executable assumptions are recorded in three groups:

- `cluster-core`: absolute commands required from the cluster operating
  system, such as Bash, `cp`, `mkdir`, `printf`, and GPU-only diagnostics such
  as `nvidia-smi`;
- `project-environment`: absolute interpreters and launchers supplied by the
  frozen project environments;
- `optional-diagnostic`: commands such as `numactl` whose absence may omit a
  report but cannot fail the load gate.

Mandatory commands are checked before submission when they are expected on
the login node and checked again inside the batch job. `jq` is not a declared
or mandatory dependency.
