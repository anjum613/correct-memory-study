# Source task: Add LOGIN_FIELD setting, fixes #389

Repository: `sunscrapers/djoser`

Source revision: `9e2248e65cbe2155b2ad5b334ead73db2322125b`

Source tree: `381a83cbd07fcce63212bba43c03f4abd04759ac`

The immutable source commit metadata supplies the task identity exactly as
`Add LOGIN_FIELD setting, fixes #389`. At S, `djoser/conf.py` configures the
`token_create` procedure as `djoser.serializers.TokenCreateSerializer`, and
the source documentation defines `LOGIN_FIELD` with the default
`User.USERNAME_FIELD`.

The focal source procedure is the complete `djoser/serializers.py` artifact,
including `TokenCreateSerializer`. This source-only selection was frozen
before source validation and before any target-side inspection.
