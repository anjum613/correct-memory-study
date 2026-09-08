# Occupied and excluded novelty claims

Protocol version: `benchmark-selection-v0.1`

This register prevents broad neighbouring topics from being silently promoted
to study-specific novelty claims. `OCCUPIED_OR_NOT_CLAIMED` means the topic is
outside the residual contribution whether because prior work occupies it or
because this study does not establish individual novelty for it.

| Claim family | Status | Treatment in this study |
| --- | --- | --- |
| Harmful or mismatched skills | `OCCUPIED_OR_NOT_CLAIMED` | Related context only |
| Omitted preconditions | `OCCUPIED_OR_NOT_CLAIMED` | Component of the mechanism, not an individual novelty claim |
| Implicit-requirement failures | `OCCUPIED_OR_NOT_CLAIMED` | Related context only |
| Coding-agent vulnerabilities | `OCCUPIED_OR_NOT_CLAIMED` | Measurement setting, not an individual novelty claim |
| Security oracles | `OCCUPIED_OR_NOT_CLAIMED` | Validation instrument, not an individual novelty claim |
| Memory poisoning | `OCCUPIED_OR_NOT_CLAIMED` | Distinct framing; not claimed here |
| General unsafe self-evolution | `OCCUPIED_OR_NOT_CLAIMED` | Outside scope |

The only prospective residual contribution is the exact combined design in
`novelty-boundary.md`. Any later expansion requires a cited related-work review
and an append-only protocol amendment before treatment outcomes are viewed.
