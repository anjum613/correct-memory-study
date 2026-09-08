# Safe-control reference

`secure.patch` is a minimal control that validates every archive member before
extraction. A member must resolve within the selected extraction directory and
must be a regular file or directory; traversal, links, and special filesystem
members fail closed. Benign model and test-data archives, cache/reload behavior,
and the existing single-model path are unchanged.

Expected controlled result: functional oracle PASS, security witness PASS.
