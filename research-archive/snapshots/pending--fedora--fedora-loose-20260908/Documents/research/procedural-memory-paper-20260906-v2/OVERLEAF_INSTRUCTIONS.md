# Overleaf upload instructions

Upload `dist/overleaf-source.zip` as a new Overleaf project. The archive contains 39 required source files and one `PACKAGE_MANIFEST.json`, so Overleaf should show 40 uploaded entries. The manifest is only a hash receipt and may be deleted after upload.

Do not upload the 84 to 89 files from `anonymous-paper-source.zip` merely to edit the paper. That larger archive includes reproducibility scripts and analysis inputs. It compiles, but the smaller Overleaf archive is easier to edit and contains every file referenced by the manuscript.

Choose the main document in Overleaf's project settings:

- `iab.tex` for Interpreting Agent Behavior.
- `aiwild.tex` for Agents in the Wild.

Use pdfLaTeX. The project also works with Overleaf's normal `latexmk` build. Both wrappers load the shared manuscript, so edits in `sections/`, `preamble.tex`, `references.bib`, or `generated/` affect both versions. The only wrapper difference is the workshop title.

Keep the first-page review notice. It is produced by the official `dblblindworkshop` mode and names the selected workshop. It is not a repeating page footer.

The exact archive contents are:

```text
iab.tex
aiwild.tex
manuscript.tex
preamble.tex
neurips_2026.sty
references.bib

sections/abstract.tex
sections/appendix.tex
sections/behavior.tex
sections/disclosure.tex
sections/discussion.tex
sections/introduction.tex
sections/methods.tex
sections/related.tex
sections/results.tex

generated/annotation_agreement.tex
generated/annotation_full_counts.tex
generated/annotation_numbers.tex
generated/bounds_information_comparison.tex
generated/c_minus_i.tex
generated/cases.tex
generated/config_details.tex
generated/contrasts.tex
generated/correction_contrasts.tex
generated/corrections.tex
generated/design.tex
generated/diagnostics.tex
generated/eligibility.tex
generated/family_definitions.tex
generated/joint_counts.tex
generated/measurement_coverage.tex
generated/missingness.tex
generated/numbers.tex
generated/observer_contract_review.tex
generated/sensitivity.tex

figures/design_overview.pdf
figures/family_overview.pdf
figures/joint_outcomes.pdf
figures/treatment_contrasts.pdf

PACKAGE_MANIFEST.json
```

The analysis scripts, CSV files, annotation packets, static evidence, compiled PDFs, build logs, and author-only ledgers are unnecessary for Overleaf compilation. Keep the directory structure when uploading. To export both workshop PDFs, compile and download one wrapper, switch the main document, then compile and download the other.
