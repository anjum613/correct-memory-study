# Build and verification report

Both anonymous review drafts passed the checks below on 6 September 2026.

| Wrapper | Content pages | Total pages | PDF bytes |
|---|---:|---:|---:|
| iab | 8 | 16 | 328,515 |
| aiwild | 8 | 16 | 328,512 |

Each PDF has pages 1–8 of scientific content, page 9 of references and the LLM declaration, and pages 10–16 of technical appendix. There are nine verified bibliography entries, two data-generated figures and twelve tables. Main-paper tables comprise the configuration table, corrected treatment contrasts and three matched behavioral panels.

## Build and statistical checks

- `make analyze` regenerated all contrasts, numerical macros, figures and tables from the saved anonymous records.
- A separate QA calculation reconstructed all 144 original/revised, scope, configuration and contrast rows, including their exact family eligibility.
- The outcome matrix has 624 unique recorded runs, 595 technically valid runs and 29 invalids. Invalid F/S/U values remain empty in both score versions.
- Exactly four Devstral security scores change. No functionality or technical-validity score changes.
- All six case records agree with their corrected outcomes; exact quotes were separately bound to native transcript lines and patch hashes in the private ledger.
- Both wrappers use `dblblindworkshop`; the official style hash matches the downloaded archive. Fonts and margins are unmodified. Only the workshop title and first-page notice differ.
- PDF text is identical between wrappers after removal of the workshop notice. All nine bibliography entries are cited; there are no undefined citations, unresolved cross-references, overfull boxes or missing-character warnings.
- PDF author metadata is empty. Reviewer-facing source and extracted PDF text passed checks for home-directory paths, private network addresses and original native run identifiers. The anonymous ZIPs use an explicit file whitelist.

The build used Python 3.14.7, NumPy 2.3.5, pandas 2.3.3, Matplotlib 3.10.9, pdfTeX 1.40.25, latexmk and BibTeX. `requirements.txt` pins the Python analysis dependencies. The statistical bootstrap seed is fixed; PDF creation timestamps can differ between builds without changing scientific content.

## Rendered-page inspection

All sixteen IAB pages were rendered with Poppler and inspected as page contact sheets. The title/abstract, both figures, matched case table, family definitions, correction/missingness page and estimator equation were additionally inspected at larger size. The AIWILD first page was inspected separately; the remaining scientific text and layout are shared. Figure legends, half-cell repetition encoding and condition order are readable. Tables remain within page bounds. No clipping, overlapping labels or incomplete references were found.

The retained images are `build/render/checked-iab-*.png`, `build/render/checked-aiwild-01.png`, `build/render/checked-content.jpg` and `build/render/checked-backmatter.jpg`. These are author-workspace QA artifacts, excluded from the anonymous ZIPs. This inspection was performed by the writing agent; no completed human review of this new manuscript is claimed.

## Fresh-package reproduction

The anonymous source ZIP was extracted into a new `build/package-check/` directory. Running `make analyze` and `make qa` there succeeded without access to private evidence mappings. All nineteen generated text/CSV/JSON files matched the originals byte-for-byte. Both freshly rebuilt PDFs had the same extracted text as the delivered drafts and the same eight-content/sixteen-total page counts. See `build/package-reproduction.json` and the corresponding logs.

`build/qa.json` records the delivered PDF hashes and automated checks. `dist/package-report.json` records anonymous archive hashes and sizes. The source package contains 51 files plus its manifest; the analysis package contains 31 plus its manifest. No evaluated agent, candidate implementation or security evaluator was executed during writing or reproduction.

## Remaining submission checks

Scientific draft verification is complete within the saved-evidence scope. Author approval, authorship/conflicts, consent declarations, live portal eligibility, the unstated IAB checklist rule and any supplementary-upload route remain manual items in `SUBMISSION_CHECKLIST.md`. No file was submitted, uploaded or published.
