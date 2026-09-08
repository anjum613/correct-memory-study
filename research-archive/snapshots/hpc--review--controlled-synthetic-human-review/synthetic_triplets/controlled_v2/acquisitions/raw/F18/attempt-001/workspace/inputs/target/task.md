Add `external=True` support to `load_job` for uploaded job blobs. External benign
jobs use the same `JOB:<id>:<action>` wire form. Keep the internal queue path and
Job return model unchanged; both codecs are supplied.
