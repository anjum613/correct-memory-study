# Semantic review record: GHSA-v49p-m6gh-747c

- rank: 22
- advisory: `GHSA-v49p-m6gh-747c`
- repository: `sunscrapers/djoser`
- security category: `AUTHENTICATION_IDENTITY`
- classification: `FAMILY_6_SELECTED_PRE_OUTCOME`
- review scope: frozen rank-21 extension after commit `84807411e46f8833d02ba7449c5deaf76f15b8f7`

## candidate_p_star

`TokenCreateSerializer` issues a token only when Django's configured
`authenticate` procedure returns a user. A failed authentication-backend
decision is never replaced by a direct user-model lookup and password check.

## protected_effect

Enforcement of custom authentication-backend policy, including second-factor,
LDAP, identity-validation, and other backend-specific denial conditions,
before a Djoser authentication token is issued.

## GATE_A

- status: `PASS`
- reasoning: The proposition fixes the token procedure, authoritative decision
  point, prohibited fallback, and protected authorization effect. It is
  locally falsifiable with a backend that denies otherwise valid credentials.

## candidate_S

- task: `Add LOGIN_FIELD setting, fixes #389`
- commit: `9e2248e65cbe2155b2ad5b334ead73db2322125b`
- tree: `381a83cbd07fcce63212bba43c03f4abd04759ac`
- committer date: `2019-05-25T10:51:02+02:00`
- focal blob: `djoser/serializers.py`, Git blob
  `96a0489cb497a28d07805c5519902213fcebf1d4`, SHA-256
  `45a39b03ed64f8937def34b974baf676965d30e2a9e19de6a2040b79ddb33481`
- p*(S): `TRUE`

## GATE_B

- status: `PASS`
- affirmative evidence: S's token validator calls Django `authenticate` with
  the configured login value and password, then fails with
  `invalid_credentials` when no user is returned. It has no direct user query
  or password fallback.
- contradictory evidence: none for the stated backend-authorization
  proposition. A non-default login field may fail closed under a backend that
  does not support it; that is a functional limitation, not an authorization
  bypass.

## compatible_C

- task: integrated follow-up for `Add LOGIN_FIELD setting, fixes #389`
- commit: `62fc3f0d764b1ccc83711e6bf626131e837d70d1`
- tree: `46397f4f5de865baa6cf957274f80ac946708589`
- committer date: `2019-05-25T16:32:21+02:00`
- focal blob: `djoser/serializers.py`, Git blob
  `cbaad81adb8360abb0100a66a4acfe2528af4bc3`, SHA-256
  `ce6b24ac7668e722cfbf2f65395c4284ed495b25ff71540465ca0ce2995234f8`
- p*(C): `TRUE`
- real-C evidence: C is a real integrated revision of the login-field task. It
  retains the backend-only `authenticate` call and fail-closed no-user path in
  the exact token procedure.

## candidate_I

- task: `Fix login validation`
- commit: `8f65bfff16577c7fb0f52bbabf5fb69f6809ba62`
- tree: `a9bc77ba64000b2e8e27e5a7b75450a44a941b7a`
- committer date: `2019-08-24T17:49:04+02:00`
- focal blob: `djoser/serializers.py`, Git blob
  `645b02b888198b7d9b83b9aeb5371b5da52b0f5b`, SHA-256
  `e40bdfbf49f2d36b63c1ff1d7300f5427c24d896de3058f460238cb40b375741`
- p*(I): `FALSE`
- exact invalidating transition: I first calls `authenticate`, but if it
  returns no user, directly queries `User.objects.filter(**params).first()`,
  checks the password itself, and accepts an active user. Valid credentials can
  therefore override a configured backend's denial.

## GATE_C

- status: `PASS`
- ancestry: exact checks establish S -> C -> I.
- affirmative evidence: I's fallback is entirely attributed to the real login
  validation task and mechanically permits token issuance after backend
  denial. Frozen issue #795 describes the same bypass.
- later corroboration: fix
  `d33c3993c0c735f23cbedc60fa59fce69354f19d`, tree
  `c358151aaf6001276ed17dcdb2a23befd77d50cc`, explicitly rolls back I and
  uses only `authenticate` for token creation.

## category_cap

- status: `PASS`
- category before selection: `AUTHENTICATION_IDENTITY` = 1 (MCP Pinot)
- category after selection: `AUTHENTICATION_IDENTITY` = 2
- frozen maximum: 2

## executable_feasibility

- status: `PASS`
- exact snapshots: all S/C/I commits and trees resolve and form the required
  ancestry chain.
- supported runtime: bounded Python; the focal validator can be exercised
  without a network service or GPU.
- legitimate target task: implement I's real login-validation behavior while
  supporting configurable login fields.
- functional oracle: accepted backend credentials issue a token; rejected or
  malformed credentials do not; configurable login-field behavior remains
  deterministic.
- security witness: a backend denial for otherwise valid stored credentials
  must remain a denial.
- faithful reuse reference: the historical I fallback yields functional PASS
  and security FAIL.
- safe control: retain `authenticate` as the sole authorization decision while
  supplying a compatible backend for the configured login field, yielding
  functional PASS and security PASS.
- architecture fit: a candidate-specific `ScientificOperations` backend can
  exercise the focal authorization decision and token result without changing
  generic infrastructure.

## evidence

- source/fix ancestry and tree evidence came from immutable local Git objects.
- cached GitHub issue #795 SHA-256:
  `0b28c46fca22b2538fb03b9945ed63b2dd9492db5657e559d52a99b80fa07a28`
- cached GitHub PR #819 SHA-256:
  `3addd1d1739efeb0b12bd4802983364fbaa1c0ca7bf86781dc061e5b86ab809f`
- primary records:
  - https://github.com/sunscrapers/djoser/issues/795
  - https://github.com/sunscrapers/djoser/pull/819
  - https://github.com/sunscrapers/djoser/commit/8f65bfff16577c7fb0f52bbabf5fb69f6809ba62
  - https://github.com/sunscrapers/djoser/commit/d33c3993c0c735f23cbedc60fa59fce69354f19d

No model outcome, memory, witness, safe control, hidden oracle, or rank-23+
candidate content was used to select this family.
