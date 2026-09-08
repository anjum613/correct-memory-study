# Procedural Memory Across Trust Boundaries

The complete shared manuscript is in this new Fedora project directory. Both workshop drafts contain eight content pages, one references/LLM-declaration page, and seven appendix pages. Their scientific text and results are identical; only the workshop wrapper differs.

## Deliverables

| File | Purpose |
|---|---|
| `iab.pdf` | Anonymous IAB long-paper draft |
| `aiwild.pdf` | Anonymous Agents in the Wild Regular Paper draft |
| `iab.tex`, `aiwild.tex`, `manuscript.tex`, `sections/` | Separate wrappers and shared LaTeX manuscript |
| `neurips_2026.sty`, `references.bib` | Unchanged official style and nine verified references |
| `data/`, `generated/`, `figures/`, `scripts/analyze.py`, `scripts/render_assets.py` | Saved anonymous data and reproducible analysis |
| `dist/anonymous-paper-source.zip` | Both PDFs, complete anonymous source, data and analysis; 51 files plus manifest |
| `dist/anonymous-analysis.zip` | Anonymous saved-data supplement; 31 files plus manifest |
| `VENUE_REQUIREMENTS.md`, `SUBMISSION_CHECKLIST.md`, `SUBMISSION_METADATA.md` | Verified rules and exact remaining manual submission steps |
| `ASSET_ASSESSMENT.md`, `CLAIM_EVIDENCE.md`, `UNRESOLVED_ITEMS.md` | Internal evidence assessment, exact private provenance and factual gaps |
| `BUILD_REPORT.md`, `build/qa.json`, `build/package-reproduction.json` | Build, visual QA and fresh-package reproduction results |

The reported experiment comprises thirteen synthetic families, four conditions, two repetitions and six completed configurations: 624 recorded runs, 595 technically valid. The primary harmful-memory hypothesis is retained, with its heterogeneous observed outcome. The draft includes corrected within-configuration contrasts, all joint outcomes, both harmful-transfer and successful-adaptation cases, and proportionate witness/missingness qualifications.

The workstation search found July engineering smoke checks and tool-format qualification records. They do not add final study runs, a later audit or completed independent behavioral coding. Exact inspected roots and versions are recorded in the asset assessment. Earlier repository-candidate work is assessed internally and contributes no unsupported corpus-to-task selection claim.

## Build

The Python analysis dependencies are pinned in `requirements.txt`. A standard LaTeX installation with latexmk, pdfLaTeX and BibTeX is required; QA also uses Poppler.

```sh
make analyze
make all
make qa
make package
```

`make analyze` processes saved numerical data only. It does not run candidate code, security evaluators, evaluated agents or paid APIs. Private ingestion/provenance scripts are not needed to reproduce the anonymous package.

## Before submission

Use `SUBMISSION_CHECKLIST.md`. Author review and consent, live portal access, IAB's unstated checklist rule and supplementary-upload availability remain manual checks. The published ordinary deadline converts to the evening of September 6 in Melbourne; use 21:59 AEST as the conservative common cutoff, subject to the live portal and official CFP.

The `private/` directory and internal assessment/claim files contain identifying evidence mappings. They remain separate from both anonymous ZIPs. No original evidence was modified, and no manuscript or supplement was submitted, uploaded or published.
