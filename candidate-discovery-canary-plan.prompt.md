You are performing a READ-ONLY production-canary planning audit.

DO NOT modify any file.
DO NOT run candidate discovery.
DO NOT access GitHub or any network service.
DO NOT submit or execute Slurm jobs.
DO NOT use sbatch, srun, salloc, SSH, SSHFS, curl, wget, gh, or GPUs.
DO NOT install packages.
DO NOT commit, stage, reset, restore, clean, checkout, merge, rebase, or stash.

You may inspect only:

1. Current fixed worktree:
   /home/anjum/candidate-discovery-casing-20260816

2. Preserved audit/stopped-run repository:
   /home/anjum/candidate-discovery-audit-20260814T123116Z

Do not recursively search /home/anjum or use `find ..`.
Do not inspect unrelated repositories.

CURRENT FIXED COMMIT

The production candidate-discovery code to test must be exactly:

a7b400f37

Its parent fixes are:

7649b145e
    dependency-order fix:
    ClosingPullRequests GraphQL capture occurs before repository metadata can
    return 404 and short-circuit.

a7b400f37
    linked-PR casing fix:
    materialization can recover evidence captured under GraphQL/request casing
    when REST repository casing differs only by case.

The current worktree must be clean. Verify these facts from Git before planning.

BACKGROUND

The previous long candidate-discovery run lasted about 15 hours and failed
because repository metadata could return 404 before required
ClosingPullRequests GraphQL evidence had been captured/finalized.

The repaired expected unavailable-repository path is:

ClosingPullRequests GraphQL evidence = AVAILABLE
repository evidence = UNAVAILABLE
capture status = CAPTURE_COMPLETE
materialization completes
rejection = GITHUB_REPOSITORY_UNAVAILABLE
candidate from that unavailable object = absent
RAW_CAPTURE_INCOMPLETE = absent

A second latent casing mismatch has also been fixed and regression tested.
Do not invent a live casing-divergent GitHub object merely to exercise it.
If the preserved run evidence already identifies a naturally casing-divergent
object, report that fact; otherwise rely on the local regression for that part.

OBJECTIVE

Derive, entirely from existing local source, scripts, manifests, logs,
AGENTS.md files, CLI parsers, and stopped-run evidence, the exact safest
CPU-only live canary for candidate discovery.

The canary is NOT the real discovery run.

It exists only to establish that the repaired production capture and
materialization path works in a real network/HPC execution before any broader
candidate acquisition is attempted.

MANDATORY CANARY LIMITS

The proposed live canary must have all of the following:

- CPU only
- no GPU allocation
- no Qwen or other model serving
- no Codex inside the Slurm job
- exactly one query/source path, if the implementation supports this
- at most one search page
- at most five discovered/materialized source objects
- at most 100 combined GitHub REST + GraphQL requests
- Slurm wall time <= 45 minutes
- inner candidate-discovery process timeout <= 35 minutes
- new timestamped output directory
- original stopped-run directory must remain read-only historical evidence
- preserve partial logs/evidence if the canary fails
- non-zero exit on structural capture/materialization failure
- record exact tested Git commit
- record exact source/query identity
- record configured caps
- no silent resume into a larger discovery run

IMPORTANT

Every limit must be backed by an existing production-supported mechanism.

Do not invent CLI flags.

Do not claim that a shell-level grep, `head`, post-hoc truncation, or output
filter constrains requests if it does not actually prevent the requests from
being issued.

If production code does NOT currently provide enforceable controls for one or
more of:

- page count
- source/query count
- object count
- total GitHub request count

then do NOT propose an unsafe live run.

Instead return:

NO_GO_NEEDS_BOUNDED_CANARY_CAP

and identify:

- exactly which limits are missing;
- the smallest production location where a guard can be implemented;
- the smallest regression tests needed;
- whether adding the guard can be done without altering scientific
  selection/ranking semantics.

INVESTIGATION

Inspect, locally only:

- AGENTS.md
- candidate-discovery CLI/parser definitions
- candidate-discovery entry points
- capture_searches and associated capture orchestration
- existing Slurm/submission scripts
- previous candidate-discovery run scripts
- preserved stopped-run manifests
- stopped-run logs
- source/query specifications
- rate-limit handling
- manifest/index verification tooling
- any request-count/page-count/object-count controls
- previous HPC account/partition/module/environment information

Use the actual preserved evidence to recover commands and HPC configuration.
Do not invent account names, partitions, Python environments, modules,
filesystem paths, query IDs, or CLI options.

PREFLIGHT REQUIREMENTS

The proposed preflight must prove before sbatch that:

1. current Git commit is exactly a7b400f37;
2. worktree is clean;
3. intended Python environment exists;
4. every proposed candidate-discovery CLI argument is supported;
5. output directory does not already exist;
6. Slurm script passes `bash -n`;
7. no GPU directive exists;
8. no Codex/model-server command exists;
9. wall-time <= 45 minutes;
10. inner timeout <= 35 minutes;
11. all page/object/request/query caps are genuinely enforceable;
12. original stopped-run artifacts are never output targets.

POST-RUN VALIDATION

Derive exact commands using existing project validators where available.

The canary should be considered PASS only if all applicable checks establish:

- Slurm state COMPLETED
- exit code 0:0
- CAPTURE_COMPLETE
- manifest verification passes
- evidence/artifact hash verification passes
- no RAW_CAPTURE_INCOMPLETE
- request/page/object limits were not exceeded
- ClosingPullRequests evidence required by the failure-shaped path is AVAILABLE
- repository evidence for the unavailable object is UNAVAILABLE
- final classification is GITHUB_REPOSITORY_UNAVAILABLE
- no candidate is materialized from that unavailable object

Do not replace structured validation with vague log greps when an existing
validator or structured JSON field exists.

OUTPUT

Return exactly these sections:

1. CURRENT STATE
   - current branch
   - current commit
   - worktree cleanliness
   - relevant fix commits

2. EVIDENCE INSPECTED
   - exact local files consulted
   - explain why each matters

3. PRODUCTION ENTRY POINT
   - exact executable/module/script
   - exact CLI parser/location defining it

4. EXISTING BOUNDING CONTROLS
   For each:
   - query/source cap
   - page cap
   - object cap
   - total GitHub request cap
   - wall-time cap
   - process timeout

   State PRESENT or ABSENT and cite the exact local implementation.

5. STOPPED-RUN EXECUTION
   - exact prior entry point
   - relevant HPC account/partition/environment
   - relevant failure-shaped source/object
   - do not expose secrets/tokens

6. LOCAL PREFLIGHT COMMANDS
   Copyable commands only using verified existing options.

7. CANARY SLURM SCRIPT
   Provide a complete script ONLY if all required hard bounds already exist.

8. SUBMISSION COMMAND
   Provide an exact `sbatch --parsable ...` command ONLY if ready.

9. POST-RUN VALIDATION
   Exact commands and expected structured outcomes.

10. ABORT CONDITIONS
    Explicit conditions that invalidate the canary.

11. DECISION

End with exactly one of:

READY_FOR_BOUNDED_CANARY

NO_GO_NEEDS_BOUNDED_CANARY_CAP

INSUFFICIENT_LOCAL_EVIDENCE

Do not execute anything described in the proposed plan.
