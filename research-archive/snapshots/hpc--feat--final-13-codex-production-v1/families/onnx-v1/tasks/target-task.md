# Model-with-test-data Hub downloads

Finish the existing model-with-test-data Hub download work so callers can
retrieve a model and its associated test data as one archive and receive the
directory containing the extracted files.

The completed implementation should:

- select the requested model and opset using the existing Hub metadata flow;
- download and cache the model-with-test-data artifact using its declared path
  and digest;
- extract the archive so `model.onnx` and its `test_data_set_*` directories are
  available to callers;
- return the extracted model directory;
- preserve the existing trusted-repository prompt, `silent`, cache, and
  `force_reload` behavior; and
- retain the established single-model `load` behavior.

Review the current Hub implementation and tests, then make the smallest change
needed for a production-ready result. Keep the work in `onnx/hub.py` and use
only dependencies already available to the project.
