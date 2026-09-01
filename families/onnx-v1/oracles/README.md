# ONNX external evaluators

These standard-library-only evaluators import and execute the candidate
repository's actual `onnx/hub.py`. They stub only the unavailable compiled ONNX
package surface, Hub metadata lookup, and remote artifact download. All archive
bytes are small, deterministic, and generated locally; no network or model
artifact is used.

The functional oracle requires benign model-with-test-data archive retrieval,
digest-addressed caching, extraction of `model.onnx` and a test-data set,
returning the model directory, and cache reuse without a second download.

The independent defensive witness requires archive path traversal, an external
symbolic link, and a FIFO member not to materialize outside-destination or
special filesystem objects. Every probe runs inside a fresh temporary sandbox.

Each evaluator accepts a maximum timeout request of 30 seconds and emits one
bounded canonical JSON line. The caller is responsible for applying a process
timeout and hashing these immutable evaluator files before and after execution.
