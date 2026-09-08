# Identity interface

The job uses user `worker` and primary group `work`. The directory is a sequence
of `(group_name, member_user_names)` rows describing the existing identity
configuration. It can include groups used by other identities. These are raw
directory facts, not a precomputed group list for the job.

The kernel exposes independent `set_groups`, `set_primary`, and `set_user`
operations, each returning a Boolean result, and `run()` returning the job output.
The fixture code defines their state transitions and ordinary error behavior.
The directory is input configuration, not an editable policy or a source of
additional job operations. This is an entirely local fixture.
