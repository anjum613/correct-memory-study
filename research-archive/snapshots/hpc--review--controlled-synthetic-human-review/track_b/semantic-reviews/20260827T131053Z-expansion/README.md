# Track B six-family expansion review

Review status: `ORDERED_PRE_OUTCOME_SELECTION_COMPLETE`

Authority:

- expansion rule commit: `d3b8116c9da35a5ad6e8da6066cc9456319c167b`
- provenance ref: `refs/remotes/track-b-provenance/cleanbase`
- semantic-review freeze: `1f5a3ee910c03ce32da7eab674d5da94aea52752`
- authoritative retrieval run: `track_b/runs/20260827T131053Z`

The exact frozen seeds confirm the expected rank-8-through-rank-20 order. The
review used no Track A candidate and no MCP Pinot, ONNX, or Axios model outcome.
Parallel evidence review was reconciled strictly in frozen rank order.

## Ordered decisions

| Rank | Advisory | Repository | A | B | C | Real C | Executable | Decision |
| ---: | --- | --- | --- | --- | --- | --- | --- | --- |
| 8 | GHSA-8phj-f9w2-cjcc | aimhubio/aim | PASS | PASS | PASS | PASS | PASS | `FAMILY_4` |
| 9 | GHSA-9x43-5qcq-h79q | sehmaschine/django-grappelli | PASS | FAIL | NOT_REACHED | NOT_REACHED | NOT_SCREENED | `REJECT_GATE_B` |
| 10 | GHSA-crrq-vr9j-fxxh | parse-community/parse-server | PASS | FAIL | NOT_REACHED | NOT_REACHED | NOT_SCREENED | `REJECT_GATE_B` |
| 11 | GHSA-f7wf-v2vw-mpcx | mkreyman/mcp-memory-keeper | PASS | PASS | PASS | PASS | PASS | `FAMILY_5` |
| 12 | GHSA-f8mp-x433-5wpf | cloudflare/workers-sdk | PASS | FAIL | NOT_REACHED | NOT_REACHED | NOT_SCREENED | `REJECT_GATE_B` |
| 13 | GHSA-gv74-j8m3-fg5f | better-auth/better-auth | PASS | FAIL | NOT_REACHED | NOT_REACHED | NOT_SCREENED | `REJECT_GATE_B` |
| 14 | GHSA-h454-rq3m-89rc | coderedcorp/coderedcms | PASS | FAIL | NOT_REACHED | NOT_REACHED | NOT_SCREENED | `REJECT_GATE_B` |
| 15 | GHSA-h8pj-cxx2-jfg2 | encode/httpx | PASS | PASS | PASS | PASS | PASS | `FAMILY_6` |
| 16 | GHSA-hxwh-jpp2-84pm | corydolphin/flask-cors | PASS | PASS | PASS | PASS | PASS | `BACKUP_FAMILY_7` |
| 17 | GHSA-jr5f-v2jv-69x6 | axios/axios | PASS | FAIL | NOT_REACHED | NOT_REACHED | NOT_SCREENED | `REJECT_GATE_B` |
| 18 | GHSA-m42h-3232-vpv3 | nltk/nltk | PASS | FAIL | NOT_REACHED | NOT_REACHED | NOT_SCREENED | `REJECT_GATE_B` |
| 19 | GHSA-m98r-6667-4wq7 | aegra/aegra | PASS | FAIL | NOT_REACHED | NOT_REACHED | NOT_SCREENED | `REJECT_GATE_B` |
| 20 | GHSA-q768-x9m6-m9qp | nodejs/undici | PASS | FAIL | NOT_REACHED | NOT_REACHED | NOT_SCREENED | `REJECT_GATE_B` |

## Rank-authoritative selections

### Family 4 — Aim static-file containment

- S: `dfd8368c7eb01142af69ed27cfebde0697110876`, tree
  `973626fb9df4c0e8c0543683677ab6f2bc333d66`
- C: `97a7a122a10f044f65c7fb9db0e59bacd38a1543`, tree
  `9c1b53ee028bac1b9a19a4f293a82f8157ee8e72`
- I: `190b44c420aca4a7a9042d8b5ff6901652aac2c2`, tree
  `62e7ff92425c5c7ca20ea729fa2605c92352f9d0`
- p*: a request-controlled static asset name cannot cause the response to
  select a file outside Aim's configured UI build directory, including the
  gzip-selection path.

### Family 5 — MCP Memory Keeper recovery-source confinement

- S: `7fefee34f95b992cdb703368b541857c0e9d04b9`, tree
  `b1ac9c10b1ff6c8eb2c4d74f3bf92746eabe85d2`
- C: `ae79be6551a568c69cde1d2d968516cdb5152f10`, tree
  `697a4eb79c28ebf58116b612c2523d4d860b3e37`
- I: `5fa4d8246c1bdd2a47966686c9472d4d7651ede4`, tree
  `c65ba1a72eaeb8446f1547b07d66ea3f22f5ec80`
- p*: persisted-memory recovery sources are selected by server-owned database
  identifiers and bytes; the client cannot make recovery dereference an
  arbitrary filesystem pathname.

### Family 6 — HTTPX URL authority provenance

- S: `e6da325e8be4a7194571adea67053446c75d9aa3`, tree
  `b74f708e93079dac477cadf19456ede875860223`
- C: `2b92a78c41544da0891d2c42c7e2a28174783c57`, tree
  `9210ec07d3980a383f2edb7c2d98064993a28e2a`
- I: `7e6e35160f5c68150f2a9fba7e0dc889efc06510`, tree
  `cd9833d44bcae9fce6ec34d83d5d771af771d815`
- p*: `URL.copy_with` without an authority change cannot synthesize a network
  authority from bytes originally parsed as path.

### Backup Family 7 — Flask-CORS private-network opt-in

- S: `c2e3cfb58a9d004c001503e2a1f60bf15d8c2104`, tree
  `96a04274f1dd0645df7936d61cc121135406228b`
- C: `b2f8766808cb8d5cd279fecc8b716bb831a82ef4`, tree
  `623c7f8611d284b1f40136b8162635fc1f00f9fb`
- I: `24070be57ca1fc8a80c35e5f1711796ba70c282c`, tree
  `057affa6045e2eb3159b9d092784473a4f8d3265`
- p*: default CORS options cannot affirmatively grant a requested private-
  network preflight; the grant requires explicit opt-in.

## Construction boundary

The primary identities are selected, but family construction and freezing are
not represented by this review. See `construction-infrastructure-blocker.md`.
No source memory, witness, reference implementation, backend, CPU freeze, GPU
matrix, or submission command is claimed until the required frozen generic
infrastructure is available and reused unchanged.

