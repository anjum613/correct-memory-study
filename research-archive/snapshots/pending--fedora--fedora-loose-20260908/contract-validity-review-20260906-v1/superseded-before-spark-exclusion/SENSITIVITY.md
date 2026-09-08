# Post-hoc sensitivity analyses

All estimates average two repetitions within family/condition before taking an equally weighted family mean. Models and harnesses stay separate.
Both repetitions must be technically valid with observed F and S in both conditions. Original/revised eligibility is identical in this review.
Positive ΔF/ΔS means more functionality/security-witness passes; positive ΔU means more functional completions that fail the focal witness.
No invalid, unstarted or unresolved result is imputed. Family omissions below are uniform scope diagnostics specified in the frozen review rule, not replacement primary estimates.

Each cell is original → revised, in percentage points. N is eligible families; two repetitions are not two independent families.

## all_13

| Cohort/model | Contrast | N | ΔF | ΔS | ΔU | Revised sign-flip p (U) |
|---|---|---:|---:|---:|---:|---:|
| MiniSWE / QwenNext | C-N | 13 | -3.85 → -3.85 | +0.00 → +0.00 | +0.00 → +0.00 | 1.0 |
| MiniSWE / QwenNext | B-C | 13 | -3.85 → -3.85 | +0.00 → +0.00 | +0.00 → +0.00 | 1.0 |
| MiniSWE / Qwen30 | C-N | 13 | -15.38 → -15.38 | +3.85 → +3.85 | -11.54 → -11.54 | 0.375 |
| MiniSWE / Qwen30 | B-C | 12 | +12.50 → +12.50 | +4.17 → +4.17 | +4.17 → +4.17 | 1.0 |
| MiniSWE / Devstral | C-N | 12 | +4.17 → +4.17 | +12.50 → +8.33 | -8.33 → -4.17 | 1.0 |
| MiniSWE / Devstral | B-C | 12 | +0.00 → +0.00 | +0.00 → +0.00 | +0.00 → +0.00 | 1.0 |
| Codex / GPT55 | C-N | 11 | +0.00 → +0.00 | -9.09 → -9.09 | +9.09 → +9.09 | 0.8125 |
| Codex / GPT55 | B-C | 10 | +0.00 → +0.00 | +30.00 → +30.00 | -30.00 → -30.00 | 0.125 |
| Codex / Luna | C-N | 11 | -9.09 → -9.09 | -9.09 → -9.09 | +13.64 → +13.64 | 0.5 |
| Codex / Luna | B-C | 11 | +4.55 → +4.55 | +13.64 → +13.64 | -13.64 → -13.64 | 0.5 |
| Codex / Terra | C-N | 12 | -4.17 → -4.17 | -4.17 → -4.17 | +4.17 → +4.17 | 1.0 |
| Codex / Terra | B-C | 11 | +0.00 → +0.00 | +22.73 → +22.73 | -22.73 → -22.73 | 0.25 |
| Codex / Spark | C-N | 4 | +0.00 → +0.00 | -12.50 → -12.50 | +12.50 → +12.50 | 1.0 |
| Codex / Spark | B-C | 1 | +0.00 → +0.00 | +0.00 → +0.00 | +0.00 → +0.00 | 1.0 |

## without_X06

| Cohort/model | Contrast | N | ΔF | ΔS | ΔU | Revised sign-flip p (U) |
|---|---|---:|---:|---:|---:|---:|
| MiniSWE / QwenNext | C-N | 12 | -8.33 → -8.33 | +0.00 → +0.00 | +0.00 → +0.00 | 1.0 |
| MiniSWE / QwenNext | B-C | 12 | +0.00 → +0.00 | +0.00 → +0.00 | +0.00 → +0.00 | 1.0 |
| MiniSWE / Qwen30 | C-N | 12 | -16.67 → -16.67 | +4.17 → +4.17 | -12.50 → -12.50 | 0.375 |
| MiniSWE / Qwen30 | B-C | 11 | +13.64 → +13.64 | +4.55 → +4.55 | +4.55 → +4.55 | 1.0 |
| MiniSWE / Devstral | C-N | 11 | +4.55 → +4.55 | +13.64 → +9.09 | -9.09 → -4.55 | 1.0 |
| MiniSWE / Devstral | B-C | 11 | +0.00 → +0.00 | +0.00 → +0.00 | +0.00 → +0.00 | 1.0 |
| Codex / GPT55 | C-N | 10 | +0.00 → +0.00 | +0.00 → +0.00 | +0.00 → +0.00 | 1.0 |
| Codex / GPT55 | B-C | 9 | +0.00 → +0.00 | +22.22 → +22.22 | -22.22 → -22.22 | 0.25 |
| Codex / Luna | C-N | 10 | +0.00 → +0.00 | -10.00 → -10.00 | +15.00 → +15.00 | 0.5 |
| Codex / Luna | B-C | 10 | -5.00 → -5.00 | +20.00 → +20.00 | -20.00 → -20.00 | 0.25 |
| Codex / Terra | C-N | 11 | -4.55 → -4.55 | -9.09 → -9.09 | +9.09 → +9.09 | 0.75 |
| Codex / Terra | B-C | 10 | +0.00 → +0.00 | +25.00 → +25.00 | -25.00 → -25.00 | 0.25 |
| Codex / Spark | C-N | 4 | +0.00 → +0.00 | -12.50 → -12.50 | +12.50 → +12.50 | 1.0 |
| Codex / Spark | B-C | 1 | +0.00 → +0.00 | +0.00 → +0.00 | +0.00 → +0.00 | 1.0 |

## without_reviewed_families

| Cohort/model | Contrast | N | ΔF | ΔS | ΔU | Revised sign-flip p (U) |
|---|---|---:|---:|---:|---:|---:|
| MiniSWE / QwenNext | C-N | 10 | -5.00 → -5.00 | -5.00 → -5.00 | +5.00 → +5.00 | 1.0 |
| MiniSWE / QwenNext | B-C | 10 | -5.00 → -5.00 | +5.00 → +5.00 | -5.00 → -5.00 | 1.0 |
| MiniSWE / Qwen30 | C-N | 10 | -15.00 → -15.00 | +5.00 → +5.00 | -10.00 → -10.00 | 0.625 |
| MiniSWE / Qwen30 | B-C | 9 | +11.11 → +11.11 | +5.56 → +5.56 | +0.00 → +0.00 | 1.0 |
| MiniSWE / Devstral | C-N | 9 | +5.56 → +5.56 | +11.11 → +11.11 | -5.56 → -5.56 | 1.0 |
| MiniSWE / Devstral | B-C | 9 | +0.00 → +0.00 | +0.00 → +0.00 | +0.00 → +0.00 | 1.0 |
| Codex / GPT55 | C-N | 9 | +0.00 → +0.00 | +0.00 → +0.00 | +0.00 → +0.00 | 1.0 |
| Codex / GPT55 | B-C | 8 | +0.00 → +0.00 | +25.00 → +25.00 | -25.00 → -25.00 | 0.25 |
| Codex / Luna | C-N | 9 | +5.56 → +5.56 | -11.11 → -11.11 | +16.67 → +16.67 | 0.5 |
| Codex / Luna | B-C | 9 | -11.11 → -11.11 | +22.22 → +22.22 | -22.22 → -22.22 | 0.25 |
| Codex / Terra | C-N | 10 | -5.00 → -5.00 | -10.00 → -10.00 | +10.00 → +10.00 | 0.75 |
| Codex / Terra | B-C | 9 | +0.00 → +0.00 | +27.78 → +27.78 | -27.78 → -27.78 | 0.25 |
| Codex / Spark | C-N | 4 | +0.00 → +0.00 | -12.50 → -12.50 | +12.50 → +12.50 | 1.0 |
| Codex / Spark | B-C | 1 | +0.00 → +0.00 | +0.00 → +0.00 | +0.00 → +0.00 | 1.0 |

The exact two-sided sign-flip diagnostic enumerates family difference signs and requires exchangeability/symmetry under the null. It is exploratory, unadjusted for multiple comparisons and does not imply random sampling of software tasks.

Exact family membership, per-family differences, both contributing run IDs per condition, and leave-one-family-out ranges are in [family units](sensitivity_family_units.csv) and [contrasts](sensitivity_contrasts.csv). Spark has incomplete cells and is not pooled with completed cohorts.
