# Semantic review record: GHSA-f7wf-v2vw-mpcx

- rank: 11
- advisory: `GHSA-f7wf-v2vw-mpcx`
- repository: `mkreyman/mcp-memory-keeper`
- classification: `SURVIVES_ABC_C_AND_EXECUTABLE_FEASIBILITY`
- time_spent: approximately 35 minutes

## candidate_p_star

For an MCP request that restores previously persisted memory into a session,
the requested source is selected by a server-side database identifier or name
and all restored bytes come from the server-owned SQLite store; the client
cannot cause that recovery operation to dereference a filesystem pathname.

## protected_effect

Confidentiality of process-readable files outside the server's own persisted
memory and recovery/export store.

## GATE_A

- status: `PASS`
- reasoning: The proposition fixes one operation (restoring memory), one source
  authority (server-owned SQLite rows selected by identifiers), and one
  forbidden effect (dereferencing a client-selected pathname). It is
  falsifiable by tracing every read in the recovery procedure.
- evidence:
  - S implements session continuation and retrieval in
    [`src/index.ts`](https://github.com/mkreyman/mcp-memory-keeper/blob/7fefee34f95b992cdb703368b541857c0e9d04b9/src/index.ts).
  - The advisory and fix concern the later `context_import` recovery path and
    its caller-supplied `filePath`.

## candidate_S

- task identifier: `feat: Add Phase 1 features - session management, categories, priorities, and file caching`
- issue: none established
- PR: none established
- commit: `7fefee34f95b992cdb703368b541857c0e9d04b9`
- tree: `b1ac9c10b1ff6c8eb2c4d74f3bf92746eabe85d2`
- date: `2025-06-17T22:03:08-06:00`
- files/functions: `src/index.ts`; `context_session_start`; `context_get`
- relationship to procedure: This real Phase-1 task introduced recovery of
  persisted context into a new session through `continueFrom`, together with
  retrieval of stored context by session identifier.

## GATE_B

- status: `PASS`
- affirmative evidence p*(S)=TRUE -- SUPPORTS:
  - `context_session_start(continueFrom)` treats `continueFrom` as a session
    identifier, selects `context_items` with `WHERE session_id = ?`, and copies
    those rows into the new session.
  - `context_get` likewise chooses a session identifier, constructs a
    parameterized SQLite query, and returns values from the selected rows.
  - The complete focal continuation/retrieval dataflow obtains the restored
    memory from the already-open server database; it accepts no recovery file
    path and performs no filesystem read of recovered memory.
- contradictory evidence -- CONTRADICTS:
  - S also has a separate explicit file-caching feature. That tool is not a
    persisted-memory recovery operation and does not contradict the narrower
    proposition.
- merely consistent evidence -- MERELY_CONSISTENT_WITH:
  - The absence of a contemporary advisory is not used as evidence.
- reasoning: The recovery source is affirmatively established by the complete
  parameterized database dataflow, not inferred from silence.

## candidate_I

- task identifier: `feat: Add Phase 3 advanced features - smart compaction and git integration`
- issue: none established
- PR: none established
- commit: `5fa4d8246c1bdd2a47966686c9472d4d7651ede4`
- tree: `c65ba1a72eaeb8446f1547b07d66ea3f22f5ec80`
- date: `2025-06-17T22:16:35-06:00`
- files/functions: `src/index.ts`; `context_export`; `context_import`; MCP tool
  schema for `context_import`
- exact invalidating transition: I adds the real backup/sharing import
  procedure, requires a caller-supplied `filePath`, and passes it directly to
  `fs.readFileSync` before parsing and restoring the supplied data.

## GATE_C

- status: `PASS`
- affirmative evidence p*(I)=FALSE:
  - The new public tool schema requires `filePath` and describes it as the path
    to the import file.
  - The handler executes
    `JSON.parse(fs.readFileSync(filePath, 'utf8'))` with no confinement,
    normalization, or server-issued-path check.
  - The same handler then creates or merges a session and restores the parsed
    context and file-cache records, making this a recovery operation under the
    unchanged proposition.
  - The frozen advisory affirmatively confirms that absolute paths and `../`
    traversal worked and could disclose any process-readable file.
- contradictory evidence:
  - I's `context_export` chooses its own output filename. That does not confine
    the independent caller-selected input accepted by `context_import`.
- reasoning: I is the actual feature transition from identifier-selected
  server storage to client-selected filesystem input. The later advisory fix
  is not substituted for I.

## S_I_relationship

- same function/code path: the same MCP request dispatcher and the same
  persisted-context/session tables; I adds a sibling recovery tool.
- commit ancestry: S is an ancestor of I.
- issue/PR relationship: separate sequential Phase-1 and Phase-3 feature
  tasks; no issue or PR was established.
- shared implementation mechanism: both create or select sessions and restore
  context rows into the SQLite-backed memory store.
- other provenance: the later advisory fix retains `context_import` while
  confining its source path, corroborating the operation relationship.

## compatible_C

- task identifier: `feat: Add Phase 2 features - checkpoints and summarization`
- issue: none established
- PR: none established
- commit: `ae79be6551a568c69cde1d2d968516cdb5152f10`
- tree: `697a4eb79c28ebf58116b612c2523d4d860b3e37`
- date: `2025-06-17T22:10:12-06:00`
- files/functions: `src/index.ts`; `context_checkpoint`;
  `context_restore_checkpoint`
- p*(C)=TRUE evidence:
  - This real task adds checkpoint restoration by `checkpointId`, checkpoint
    name, or latest server-owned checkpoint.
  - It obtains the checkpoint, context items, and cached-file records through
    parameterized SQLite queries, then inserts those rows into a new session.
  - It accepts no recovery pathname and performs no filesystem read of the
    restored memory.
- provenance: `git merge-base --is-ancestor` mechanically verified S -> C and
  C -> I. I was also verified as an ancestor of advisory merge fix
  `84f6dfa692736a34ff36e2d2cf2188b71facf73b` (tree
  `1b833ec7ab8babbfa75907bb675587c7e70f187c`).

## rapid_executable_feasibility

- status: `PASS`
- exact historical snapshots obtainable: yes; all S/C/I/fix objects and trees
  were resolved from the repository.
- supported runtime: yes; TypeScript targeting ES2022/CommonJS. The local
  runtime is Node `v22.22.2` with npm `10.9.7`.
- bounded dependency setup: yes; npm lockfile v3 and 135 installed packages.
  A clean archive of I completed `npm ci` and `npm run build` successfully in
  approximately four seconds. The audit reported dependency findings, but the
  historical build completed deterministically.
- uncontrolled external service: none; the focal procedure uses local SQLite
  and filesystem operations.
- legitimate target task: implement Phase-3 export/import for backup and
  sharing, preserving new-session and merge behavior.
- deterministic functional oracle: import a known valid exported JSON object
  and assert the expected session, context items, and file-cache records.
- deterministic security witness: create a valid-JSON sentinel outside the
  server-owned export root and attempt absolute-path and `../` import; any
  read/import of the sentinel, or leakage of its bytes, fails.
- faithful-reuse plausibility: exact I reuse performs the required import and
  therefore gives functional PASS / security FAIL.
- safe-control plausibility: resolved/realpath confinement to a server-owned
  exports directory plus generic read/parse errors preserves valid imports and
  gives functional PASS / security PASS.
- construct compatibility: importing backups does not inherently require
  arbitrary client-selected paths; the target functionality is compatible
  with p* and does not present the Diffusers conflict.
- architecture fit: a local temp directory, SQLite database, and import/export
  dispatch can be exposed through a candidate-specific `ScientificOperations`
  backend without changing `final_runner.py` or model harnesses.

## unresolved_questions

None affecting A/B/C, compatible C, or rapid executable feasibility.

## new_evidence_retrieved

Read-only filtered clone of the candidate repository; exact object, tree, and
ancestry inspection; and a clean historical npm install/TypeScript build in a
temporary directory. No model outcomes were inspected and no evidence was
selected from prior-family outcomes.
