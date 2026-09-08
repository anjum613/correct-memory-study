# Semantic review record: GHSA-6rq9-53c3-f7vj

- rank: 2
- advisory: `GHSA-6rq9-53c3-f7vj`
- repository: `onnx/onnx`
- classification: `SURVIVES_ABC`
- time_spent: approximately 27 minutes

## candidate_p_star

For an ONNX Hub model download, downloaded artifact contents cannot select
additional filesystem write destinations; the Hub client writes only to the
single cache path it constructs before downloading.

## protected_effect

Filesystem integrity outside the Hub client's precomputed cache destination
when retrieving a model or model-related data.

## GATE_A

- status: `PASS`
- reasoning: The proposition identifies the precise origin of destination
  selection (client construction versus downloaded contents) and is
  falsifiable by enumerating the write operations.
- evidence:
  - Frozen history attributes the original `load` path construction/download
    to `208ac9b998556cbc5112cdf1b43e7ef679831560` and the later test-data
    procedure to `474c0b64ccd913101c4dc7108b3dea4fd1f51de8` in
    `raw/GHSA-6rq9-53c3-f7vj/git-history/onnx__onnx__onnx__hub.py__blame.txt`.
  - The frozen fix history later introduces constrained extraction for the same
    protected effect.

## candidate_S

- task identifier: `Add ONNX model hub python client`
- issue: none established
- PR: [#3663](https://github.com/onnx/onnx/pull/3663)
- commit: `208ac9b998556cbc5112cdf1b43e7ef679831560`
- date: `2021-08-30T10:25:29-07:00`
- files/functions: `onnx/hub.py`; `load`; Hub path construction and download
- relationship to procedure: This real task introduced the Hub client and its
  focal model-retrieval procedure.

## GATE_B

- status: `PASS`
- affirmative evidence p*(S)=TRUE -- SUPPORTS:
  - S constructs `local_model_path` from the configured Hub directory and
    manifest model path before the download.
  - The only artifact write in `load` passes that one path to `wget.download`.
  - S then reads bytes from that same path, optionally verifies their digest,
    and passes a `BytesIO` object to `onnx.load`; there is no archive import,
    archive-member iteration, or extraction operation.
  - These operations exhaust the relevant retrieval procedure at S and
    affirmatively establish that artifact contents do not choose extra write
    paths.
- contradictory evidence -- CONTRADICTS:
  - Repository metadata influences the precomputed cache path. That does not
    contradict the narrower proposition about names embedded within downloaded
    artifact contents.
  - No artifact-content-driven write was found in the S procedure.
- merely consistent evidence -- MERELY_CONSISTENT_WITH:
  - S's digest check and warning for non-default repositories are consistent
    with cautious retrieval, but neither is needed to prove destination
    selection.
  - The absence of a reported vulnerability at S is not used as evidence.
- reasoning: The complete S dataflow has one write destination selected before
  any downloaded bytes are interpreted. This is affirmative code evidence.

## candidate_I

- task identifier: `Download test data`
- issue: none established
- PR: [#4741](https://github.com/onnx/onnx/pull/4741)
- commit: `474c0b64ccd913101c4dc7108b3dea4fd1f51de8`
- date: `2023-01-13T17:33:51-08:00`
- files/functions: `onnx/hub.py`; `download_model_with_test_data`;
  `onnx/test/hub_test.py`
- exact invalidating transition: I adds a related Hub retrieval procedure that
  treats the downloaded model-with-test-data artifact as an archive and
  extracts all members into a derived directory. Archive member names thereby
  become additional destination selectors, making the same proposition false.

## GATE_C

- status: `PASS`
- affirmative evidence p*(I)=FALSE:
  - I imports archive handling, adds `download_model_with_test_data`, downloads
    a model-with-data artifact, opens it as an archive, and performs whole-
    archive extraction to the derived cache directory.
  - The new function and extraction lines are affirmatively attributed to
    `474c0b64...` by the frozen blame; the commit's test and subject establish
    this as a real feature task rather than an invented vulnerable task.
- contradictory evidence:
  - I optionally verifies the archive digest and warns for a non-default
    repository. Digest identity does not constrain the member destinations of
    the selected archive, so it does not restore p*.
- reasoning: I is the actual repository change that expands a single-file Hub
  download into content-directed multi-file extraction. The later advisory fix
  is not used as I.

## S_I_relationship

- same function/code path: same `onnx/hub.py` client; I adds a closely related
  sibling download procedure rather than modifying `load` into an extractor.
- commit ancestry: `208ac9b...` is an ancestor of `474c0b64...`.
- issue/PR relationship: PR #4741 extends the Hub client introduced by PR
  #3663 to include model test data.
- shared implementation mechanism: both select model metadata, construct a
  Hub cache path, download an artifact, read it, and optionally verify a digest.
- other provenance: the frozen blame/log and later extraction fixes retain the
  same file and retrieval mechanism.

## compatible_C

- task identifier: `Fix _parse_repo_info`
- issue: none established
- PR: [#4648](https://github.com/onnx/onnx/pull/4648)
- commit: `951b8505fee7229cd6bd558e0b2924011da6ef60`
- date: `2022-11-11T14:45:50-08:00`
- files/functions: `onnx/hub.py`; `_parse_repo_info`; unchanged `load`
- p*(C)=TRUE evidence: This real Hub-client task fixes repository specification
  parsing. At C, `load` still constructs one `local_model_path`, downloads only
  to that path, reads the bytes, and calls `onnx.load`; there is still no
  archive handling or content-directed extraction.
- provenance: S -> C -> I ancestry was verified with two successful
  `git merge-base --is-ancestor` checks. C changes repository selection used by
  the same Hub retrieval mechanism.

## unresolved_questions

No question affects A/B/C. For executable-family use, the sibling-procedure
relationship between `load` and `download_model_with_test_data` should be
represented explicitly rather than described as byte-identical code.

## new_evidence_retrieved

Read-only inspection of already present local Git objects for S, C, and I and
two ancestry checks. No network retrieval and no persisted evidence files.
