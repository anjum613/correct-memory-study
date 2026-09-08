# Isolated Devstral runtime

This environment is only for the Devstral server. It must not be created over,
or activated in place of, the existing Qwen2.5-Coder environment.

From the repository root, create it with:

```bash
DEVSTRAL_BOOTSTRAP_PYTHON=/path/to/python3.11 \
DEVSTRAL_ENV_DIR="$PWD/.runtime/devstral-small-2507" \
scripts/create_devstral_environment.sh
```

The bootstrap interpreter must be exactly Python 3.11.11. Activate the new
environment with:

```bash
source "$PWD/.runtime/devstral-small-2507/bin/activate"
```

Then run the offline checks after the exact model snapshot has been populated
in the shared Hugging Face cache:

```bash
python -m pip check
python scripts/verify_devstral_environment.py --require-cuda --expected-gpus 2
```

The lock pins vLLM 0.10.0 and `mistral-common` 1.8.4. That combination includes
support for the model's v13 Tekken tokenizer. PyTorch 2.7.1 uses the CUDA 12.8
wheel index. The verifier records the actual CUDA runtime, A100 names, tokenizer
revision, and rendered-template digest rather than assuming installation implies
runtime compatibility.
