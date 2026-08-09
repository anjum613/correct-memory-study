# Qwen3.6-27B qualification candidate

This namespace is a treatment-blind model-screening candidate. It is not a
qualified model, and it contains no memory-treatment or security-triplet
result.

## Preserved prior screen

The Qwen2.5-Coder-32B qualification remains `FAIL` at 2/5 repository-competence
passes. Its authoritative result is
`qualification/qwen32b-v1/qualification-result.json` with SHA-256
`af494119487c6a31d7e6924511c81c5bdfa0aeacf9607a28b4f5f43178ecc29a`.
The tag `qwen32b-qualification-v1` remains at
`ba039a0eaddc358d6b7174260c3b3c36169c44c0`.

## Exact candidate identity

- Model: `Qwen/Qwen3.6-27B`
- Immutable Hub revision: `6a9e13bd6fc8f0983b9b99948120bc37f49c13e9`
- Architecture: `Qwen3_5ForConditionalGeneration` (`qwen3_5`)
- Parameters: 27,781,427,952
- Released tensor dtype: BF16
- Tensor bytes from the safetensors index: 55,562,855,904
- Physical size of 15 weight shards: 55,563,006,400 bytes
- Native context: 262,144 tokens
- Tokenizer: `Qwen2Tokenizer`
- License: Apache-2.0
- Custom remote code: not required; vLLM 0.19.0 has a native implementation

The model configuration records Transformers 4.57.1. The model card asks for
the latest Transformers release and vLLM 0.19.0 or later; this candidate pins
the stable vLLM 0.19.0 release and Transformers 4.57.1 rather than a nightly.
The text-only server uses the documented `--language-model-only` flag and the
`qwen3` reasoning parser. The offline compatibility probe confirms native
architecture recognition without `trust_remote_code`.

The authoritative upstream sources are the
[pinned model repository](https://huggingface.co/Qwen/Qwen3.6-27B/tree/6a9e13bd6fc8f0983b9b99948120bc37f49c13e9),
the [Qwen3.6 project](https://github.com/QwenLM/Qwen3.6), and the
[vLLM 0.19 supported-model table](https://docs.vllm.ai/en/v0.19.0/models/supported_models/).

## Two-A100 feasibility decision

The initial serving context is 32,768 tokens with BF16, tensor parallelism 2,
one active sequence, eager execution, and a 0.90 vLLM memory budget. Each GPU
holds an estimated 27,781,427,952 bytes (25.87 GiB) of weights. The 16
full-attention layers require an estimated 1 GiB of BF16 KV cache per GPU at
32K. This leaves 14,094,503,184 physical bytes per GPU after weights and that
KV estimate, or 9,799,535,888 bytes within the 90% vLLM allocation for hybrid
state, CUDA/NCCL, activations, and runtime overhead.

This is a conservative load-smoke configuration, not a claim that the native
262K context fits. No quantization, context extension, speculative decoding,
or automatic summarization is enabled. A 64K or 128K setting was not selected
without measured runtime margin.

## Isolated serving stack

- Environment: `/home/s224049759/environments/qwen36-vllm-v1`
- Python: 3.12.8
- PyTorch: 2.10.0+cu128
- vLLM: 0.19.0
- Transformers: 4.57.1
- Tokenizers: 0.22.2
- Environment fingerprint: `fe63e366ca33bc2392eb173281764bdb8bd543ed3ce8d36c3b3fe6727df80bab`
- Authoritative selected-content digest: `b36b9c47b130dba7c2a0ae60161029d3f5b0b522e8bd0f5b0f0749bae86b3a74`

The existing Qwen2.5 environments were not upgraded or modified.

## Reasoning and generation behavior

The upstream chat template enables thinking by default. The CPU probe verifies
both thinking and non-thinking rendering, and vLLM uses its `qwen3` reasoning
parser so reasoning is separated from final assistant content. The smoke uses
temperature 0 and a 128-token cap, does not preserve thinking across requests,
and starts a fresh stateless server. It does not enable automatic tools,
skills, memory, conversation summarization, or cross-session state.

Final stochastic decoding for repository qualification is deliberately not
selected by this serving-only smoke task. It must be frozen before any of the
five repository tasks are submitted.

## Qualification-suite identity

The candidate references the original
`qualification/qwen32b-v1/suite-manifest.json` (SHA-256
`67a97e7ec0452907d80da681b128021d65a9205664ce7ff6be90944e92ba9c48`).
It does not copy or edit tasks, oracles, policies, prompts, or reference
patches. `suite-reference.json` records byte-level equality for all five
primary and two reserve tasks. The competence definition and 4/5,
3/5-plus-reserves, and 2/5-or-fewer rule are unchanged.

Only one model-load/request smoke may be submitted in this phase. No
qualification task is consumed by that job.
