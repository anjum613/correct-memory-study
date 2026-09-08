# Synthetic Qwen3.6 GPU smoke execution layer

This namespace binds the frozen synthetic fixture in
`synthetic/memory-smoke-v1` to the already-qualified Qwen3.6 scientific
adapter. It does not change the source fixture and is not scientific evidence.

One Slurm allocation loads the model once. The four frozen conditions then run
in their frozen assignment order with independent repositories, agent
processes, homes, temporary directories, conversations, resolved configs, and
artifact directories. Only the vLLM weights/server are shared.

Condition outcomes are descriptive engineering evidence. Model behavior never
controls condition selection, reruns, or the pipeline-integrity decision.
