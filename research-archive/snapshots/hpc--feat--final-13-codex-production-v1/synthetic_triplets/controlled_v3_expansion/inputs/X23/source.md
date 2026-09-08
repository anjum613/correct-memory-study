# Frozen source procedure: X23

Set a worker's user and primary group before running the requested operation.

Source-valid assumption: The inherited supplementary group set contains no authority beyond that worker's intended identity.

Target change: The launcher now carries additional supplementary group memberships.
