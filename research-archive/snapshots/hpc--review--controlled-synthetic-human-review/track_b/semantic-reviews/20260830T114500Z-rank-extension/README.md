# Track B rank-extension review

Status: `ORDERED_PRE_OUTCOME_FAMILY_6_SELECTION_COMPLETE`

Authority:

- original expansion rule: `d3b8116c9da35a5ad6e8da6066cc9456319c167b`
- original ordered reviews: `9fe5c350aee4efed5288a075168262df32162c76`
- rank-21 extension rule: `84807411e46f8833d02ba7449c5deaf76f15b8f7`
- bounded extension config: `525e61e658cdb043132988efeccf7f7f2abb2e97`
- prefix-verified ranking run commit: `9fe782158a534143c38b5001ed6d4c4aabbee30e`
- ranking run: `track_b/runs/20260830T114500Z-rank-extension-v1`

The first 20 detailed seed records and compact ranking records reproduce the
authoritative frozen outputs byte-for-byte. Review then continued in original
rank order. Parallel evidence gathering was reconciled strictly by rank.

## Ordered decisions

| Rank | Advisory | Repository | A | B | C | Real C | Category | Executable | Decision |
| ---: | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 21 | GHSA-qh9q-34h6-hcv9 | mkdocs/mkdocs | PASS | PASS | PASS | PASS | FAIL (cap) | NOT_REACHED | `REJECTED_CATEGORY_CAP_FILESYSTEM_PATH_ARCHIVE_SATURATED` |
| 22 | GHSA-v49p-m6gh-747c | sunscrapers/djoser | PASS | PASS | PASS | PASS | PASS | PASS | `FAMILY_6_SELECTED_PRE_OUTCOME` |

No rank 23 or later candidate was semantically reviewed. The bounded ranking
run preserves their identities only; Djoser fixed Family 6 at rank 22, so the
primary-selection rule stops there. No optional backup was selected.

## Family 6 — Djoser authentication-backend authority

- S: `9e2248e65cbe2155b2ad5b334ead73db2322125b`, tree
  `381a83cbd07fcce63212bba43c03f4abd04759ac`
- C: `62fc3f0d764b1ccc83711e6bf626131e837d70d1`, tree
  `46397f4f5de865baa6cf957274f80ac946708589`
- I: `8f65bfff16577c7fb0f52bbabf5fb69f6809ba62`, tree
  `a9bc77ba64000b2e8e27e5a7b75450a44a941b7a`
- p*: `TokenCreateSerializer` issues a token only when configured Django
  authentication returns a user; backend denial cannot be replaced by a
  direct user lookup and password check.
- category: `AUTHENTICATION_IDENTITY`

## Preserved nonselection decisions

- Flask-CORS remains `REJECTED_INVALID_MEMORY_GENERATION_CHRONOLOGY` and was
  not regenerated or reconsidered.
- MCP Memory Keeper remains semantically/executably feasible but cannot enter
  the primary roster because ONNX and Aim fill both
  `FILESYSTEM_PATH_ARCHIVE` slots.
- No Gate-B rejection from ranks 8 through 20 was revived.

## Construction boundary

This record selects Djoser before construction and before any Djoser memory,
witness, reference, backend result, model trajectory, or model outcome exists.
Family freezing and model readiness require the unchanged generic admission
workflow and are not claimed by this selection record.
