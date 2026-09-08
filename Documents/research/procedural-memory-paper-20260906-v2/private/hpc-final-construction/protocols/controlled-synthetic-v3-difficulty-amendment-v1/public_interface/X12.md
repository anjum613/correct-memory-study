# Child configuration interface

The fixed child's documented output contains the effective `LOCALE`, `DATA`,
`TUNING` and `REQUIRED` settings, in that order, along with its exit code.
`LOCALE`, `DATA` and `TUNING` are string-valued options; `REQUIRED` is existing
inherited configuration. The call takes a parent environment and an option
overlay. No executable selection is added.

The public child is a local integration-test collector of environment calls and
ordinary results, not an implementation of a process loader or interpreter.
The fixed child and configuration contract are unchanged.
