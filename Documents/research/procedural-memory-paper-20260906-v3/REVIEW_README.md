# Correct Memory, Changed Assumptions

This anonymous release accompanies a controlled study with thirteen synthetic families, four conditions, two repetitions, and six model and agent configurations. It preserves 624 recorded runs, 595 technically valid outcomes, and both original and corrected labels.

## Packages

- `anonymous-paper-source.zip`: both workshop wrappers, shared sections, official style, verified bibliography, generated assets, analysis inputs/scripts, annotation labels, prospective output controls, and compiled PDFs.
- `overleaf-source.zip`: minimal editable LaTeX project with both wrappers, the shared manuscript, generated LaTeX inputs, four figures, bibliography, and official style.
- `anonymous-analysis.zip`: saved outcome and measurement tables, annotation labels/codebook, generated statistics, plotting scripts, and prospective specifications.
- `anonymous-static-evidence.zip`: all 624 saved implementation and patch texts, all task prompts, 623 available visible traces, thirteen family records with exact memory strings and reference code text, and 52 anonymous annotation packets. Its `COVERAGE.json` and reviewer packet receipt describe availability, hashes and redactions.

These are local anonymous artifacts; no publication or upload is implied. The source package builds independently of the static evidence package. Extract the analysis and evidence ZIPs into the same directory to inspect joins and verify evidence hashes.

## Analysis inputs

`data/outcomes.csv` is the saved row table, with stable release record IDs and original/revised F/S/U columns. Invalid F/S/U cells remain empty under both historical score versions. `data/configurations.json` records executed settings; the requested or actual model ID is authoritative, while an older protocol key is not an inferred backend identity. `data/families.json` and `data/reference_controls.json` describe source assumptions and saved reference observations. Reference state B/U/R labels are distinct from memory condition B and endpoint U.

`data/measurement_components.csv` preserves explicitly completed component evaluations within originally invalid records. It separates interruption, session timeout, candidate execution exception and evaluator lowering incompatibility. It does not convert an incomplete raw false flag into a security failure. `generated/missingness_bounds.csv` gives fixed-cohort identification bounds with and without retaining completed components; these are not confidence intervals.

`data/behavior_sample.csv` joins the 52-run sample selected by a rule frozen before annotation to outcomes only after the two isolated LLM passes finished. Each pass's labels and evidence notes remain separate. Eight disagreements are retained without outcome based adjudication. The frozen codebook defines explicit assumption recognition before editing, procedure retention without the check, concrete protection, and no meaningful implementation. This is automated coding, not independently validated human annotation. Packet selection used design labels without outcomes or availability. Release copies have additional author redactions; hashes for the annotated and released copies are both recorded, with unchanged event/line anchors.

`data/cases.json` preserves six exact visible excerpts for three matched panels selected after outcome inspection. These selected cases are separate from the systematic sample. `data/observer_contract_review.csv` inventories the static contract review across all thirteen families. Accepted implementation counts and distinct syntax trees measure observed acceptance diversity, not semantic validation of every implementation.

## Reproduce

Python 3 with NumPy, pandas and Matplotlib is required; `requirements.txt` pins the analysis versions used. No model credentials are needed.

```sh
python3 scripts/analyze.py
python3 scripts/render_assets.py
python3 scripts/analyze_missingness.py
python3 scripts/analyze_annotations.py
python3 scripts/render_observer_review.py
python3 measurement-v2/check_outputs.py
```

Primary contrasts average repetitions within family and condition, then paired differences equally across eligible families. Both repetitions in both arms must be valid. C−N is primary; I−N and B−C are secondary. Bootstrap intervals resample paired families 20,000 times with fixed analysis seeds. Scope omissions, sign flip diagnostics, C−I and the new missingness analysis are exploratory. The bounds retain all thirteen families and differ from complete family estimates in their target set.

For the source package, install LaTeX with latexmk, pdfLaTeX and BibTeX, plus Poppler for QA:

```sh
make analyze
make measurement-check
make all
make qa
```

Both drafts use anonymous `dblblindworkshop` mode and share all scientific text. Seven content pages are followed by references, the LLM declaration, and the appendix. The official style is unchanged; only the workshop name in the wrapper and review notice differs.

After combining analysis and static evidence packages:

```sh
python3 scripts/verify_evidence.py
```

## Version distinctions

Four Devstral focal witness scores change under the completed X05/X28 observer correction; functionality and validity do not. X06 retains the original bounded confidentiality result, including rejection before output. `measurement-v2/CONTRACTS.md` specifies a prospective public output obligation and a representation independent F08 output rule. Its fourteen benign controls test the proposed observers; they are not new historical agent scores. No saved candidate implementation or sealed witness is executed by these reproduction commands.

`prospective/` contains an unexecuted memory content ablation, thirteen extracted draft component pairs, and a conditional precision planning grid. No repository benchmark result or collected-candidate-to-thirteen lineage is asserted.

The static evidence package supports inspection of saved behavior and arithmetic. It omits sealed executable security fixtures, encrypted reasoning, identifying metadata and private evidence mappings, so it does not claim independent reproduction of fresh security evaluations. Unrelated repository candidate code is excluded, and no blanket third-party redistribution license is inferred.

All four figures are generated exclusively with Python and Matplotlib as vector PDFs at the manuscript text width. `scripts/plot_figures.py` is the editable source; `make figures` regenerates only the plots. The conventional palette and all input/output hashes are recorded in `generated/figure_manifest.json`. Figure text is at least 8 points at the saved print size.
