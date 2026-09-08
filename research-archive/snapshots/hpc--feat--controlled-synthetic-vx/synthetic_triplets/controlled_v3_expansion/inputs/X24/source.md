# Frozen source procedure: X24

Read a multi-record safety condition, change the chosen record and commit.

Source-valid assumption: Decisions for the same invariant cannot overlap.

Target change: Independent transactions may make overlapping decisions under the same fixed snapshot rules.
