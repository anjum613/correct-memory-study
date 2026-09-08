# Objective replacement policy

Protocol: `benchmark-selection-v0.1`

Replacement is exceptional and outcome-blind. It never deletes or rewrites the
selected candidate, failed validation, trajectory, or reason for replacement.

## Permitted triggers

Before any treatment outcome is accessible, replacement may occur only when a
frozen objective fact makes execution invalid or impossible, including:

- an upstream snapshot cannot be recovered byte-for-byte;
- a frozen dependency or setup becomes unavailable and no protocol-preserving
  reconstruction exists;
- independent audit finds a pre-existing hard-gate failure;
- responsible-disclosure obligations prohibit safe use or publication; or
- artifact corruption is demonstrated by a frozen hash mismatch.

Model performance, treatment effect, memory following, functional/security
outcomes produced by an evaluated agent, and apparent support for the
hypothesis are never replacement triggers.

## Deterministic procedure

1. Preserve the original candidate and append the objective trigger, evidence
   hashes, actor, UTC time, and protocol version.
2. Confirm in writing that no treatment outcome was viewed or used.
3. Choose the highest-ranked unused reserve from the same trust-family stratum
   using the already-frozen score and tie-break order.
4. Recheck the one-per-repository and two-per-mechanism-key caps against the
   resulting selected set.
5. Require all hard gates and independent approval for the reserve; do not
   repair missing evidence after seeing treatment outcomes.
6. Publish an append-only replacement record and a new benchmark-freeze
   version containing both old and new identities.

If no same-stratum reserve satisfies the caps, reduce the benchmark size. A
new discovery round requires a prospective protocol amendment and is forbidden
after any treatment outcome is accessible.

## After treatment access

Once any treatment outcome for the benchmark is accessible, membership and
reserve ordering are immutable. Technical-invalid runs are handled under the
frozen run protocol; they do not authorize candidate replacement or selective
removal.
