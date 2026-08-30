# HTTPX Track B family

This package constructs the exact rank-15 HTTPX family selected by immutable
commit `9fe5c350aee4efed5288a075168262df32162c76`.

The source-only procedural memory was frozen at commit `3237c04d` before the
compatible or invalidated target snapshots were materialized. The exact
historical contrast is:

- S `e6da325e8be4a7194571adea67053446c75d9aa3`: p*=TRUE;
- C `2b92a78c41544da0891d2c42c7e2a28174783c57`: p*=TRUE; and
- I `7e6e35160f5c68150f2a9fba7e0dc889efc06510`: p*=FALSE.

The faithful no-change reference must pass the functional oracle and fail the
security witness. The safe control copies the URL object and replaces its parsed
reference directly; it must pass both checks.
