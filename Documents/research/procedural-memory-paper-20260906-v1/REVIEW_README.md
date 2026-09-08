# Procedural Memory Across Trust Boundaries

This anonymous package accompanies a controlled study with 13 synthetic task families, four memory conditions, two repetitions, and six model–agent configurations. It contains 624 recorded runs, including 595 technically valid runs. It is an analysis package for saved observations, not an executable task benchmark.

## Contents

- `data/outcomes.csv`: all recorded outcomes, retaining original and revised labels. Stable `record` identifiers are local to this release. Invalid F/S/U values are empty. Termination labels and intermediate raw evaluator flags do not override analytical missingness.
- `data/configurations.json`: a census of the configurations actually executed. A `frozen_source_model_key` is a historical protocol key; use `actual_model_id` for MiniSWE model identity and the requested `model` for Codex. Absent settings are unavailable, not zero.
- `data/cases.json`: six exact visible transcript excerpts, final implementation summaries, and outcome links. These cases were selected after outcome inspection. The original transcript line numbers are provenance anchors; full native transcripts are not included.
- `data/families.json`: source assumptions, target changes, and bounded witness definitions.
- `data/reference_controls.json`: saved target-reference checks. Each tuple is `[existing-test pass, feature-test pass, focal-witness pass]`. Here B/U/R name baseline, unadapted, and repaired **reference states**; they are not the memory-condition B or the endpoint U.
- `data/construction_summary.json`: synthetic construction counts, separate from any repository discovery effort.
- `generated/`: estimates, family eligibility, counts, uncertainty diagnostics, and LaTeX tables.
- `figures/`: figures generated from the row data.
- `scripts/analyze.py` and `scripts/render_assets.py`: saved-data analysis and table generation.

The full paper-source ZIP additionally includes two workshop wrappers, a shared manuscript, the unchanged official `neurips_2026.sty`, verified bibliography, PDFs, and a Makefile. Only the workshop name differs between the two PDFs.

## Reproduce the analysis

Python 3 with NumPy, pandas, and Matplotlib is required. The supplied `requirements.txt` records the versions used. No model credentials or network access are needed after installing these dependencies.

```sh
python3 scripts/analyze.py
python3 scripts/render_assets.py
```

The analysis averages two repetitions within each family and condition, then averages paired family differences equally. A contrast includes a family only when both repetitions in both arms are technically valid with observed outcomes. The primary contrast is C−N; I−N and B−C are secondary. C−I, family omission, sign-flip, and leave-one-family-out analyses are exploratory. Bootstrap intervals use 20,000 paired-family resamples and fixed seeds. Original labels are retained for the correction comparison; the manuscript uses revised labels.

## Build the paper-source package

Install a standard LaTeX distribution with `latexmk`, `pdflatex`, and BibTeX. The QA command also requires Poppler's `pdfinfo` and `pdftotext`.

```sh
make analyze
make all
make qa
```

The checked drafts have eight content pages, one reference/declaration page, and seven appendix pages. Both use anonymous workshop review mode. The analysis-only ZIP has no manuscript files or Makefile; use the two Python commands above.

## Interpretation and scope

F denotes functionality pass; S denotes focal-security-witness pass; U is F and not S. A witness pass is not general security or full-contract compliance. Four Devstral S labels changed in the documented X05/X28 correction; functionality and technical validity did not change. X06 rejection can satisfy the executed confidentiality witness without establishing redaction or retention. The paper includes original-versus-corrected comparisons and scope sensitivity.

The release omits private evidence mappings, original session identifiers, credentials, local paths, raw native sessions, and repository-corpus material. It contains no candidate implementations, security-test payloads, or evaluator executables. It supports recomputation of the reported statistics and inspection of selected excerpts; it does not independently reproduce the original task evaluations. Third-party material is not covered by an inferred redistribution license.
