# Frozen source procedure: X09

Apply an authenticated operation when its request arrives, then return the result.

Source-valid assumption: Each authenticated operation is delivered at most once.

Target change: The transport may retry the same authentic operation.
