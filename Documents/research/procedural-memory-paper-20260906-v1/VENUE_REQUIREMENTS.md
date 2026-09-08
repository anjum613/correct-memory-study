# Venue requirements — checked 6 September 2026

These are review drafts. No submission, upload, publication, or organizer contact was performed. Site snapshots and the public OpenReview invitation schemas are retained in `private/`.

| Requirement | IAB | Agents in the Wild |
|---|---|---|
| Paper category | Long paper, up to 9 content pages | Regular Paper, up to 9 content pages |
| Excluded from page limit | References, unlimited appendix; LLM declaration explicitly excluded | References and supplementary material |
| Ordinary submission deadline | 5 September 2026, 23:59 AoE | Extended to 5 September 2026 AoE |
| Melbourne conversion | 6 September, 21:59 AEST | End of 6 September, approximately 22:00 AEST |
| Notification | 29 September 2026 | 29 September 2026 AoE |
| Camera ready | 20 November 2026 | 4 December 2026 AoE |
| Workshop | 11–12 December 2026 | 11 or 12 December 2026, tentative |
| Review | Double blind for ordinary submissions | Double blind, including supplements and linked code |
| Format | NeurIPS style | NeurIPS/ICLR/ICML and other major-venue styles accepted |
| Checklist | Workshop requirement not stated; **unverified** | NeurIPS checklist explicitly not required |
| LLM rules | Main-track author LLM policy applies; declaration included in draft | Main-track author LLM policy applies; declaration included in draft |
| Archival status | Non-archival | Non-archival; other venues' policies must still permit concurrent submission |

Sources: [IAB official site](https://iab-agents.github.io/) (its current client bundle supplies the dynamically rendered CFP), [AIWILD official CFP](https://agentwild-workshop.github.io/neurips2026/). IAB additionally permits a September 25 route **only for work reviewed at NeurIPS 2026**, with reviews and response; this is not an ordinary extension for this new draft.

## Public OpenReview form verification

Read-only API inspection verified the schemas for [IAB](https://api2.openreview.net/invitations?id=NeurIPS.cc/2026/Workshop/IAB/-/Submission) and [AIWILD](https://api2.openreview.net/invitations?id=NeurIPS.cc/2026/Workshop/AIWILD/-/Submission). Both require title (1–250 characters), authors with OpenReview profiles, keywords, abstract (maximum 5,000 characters), PDF (maximum 50 MB), author-email-sharing consent, and consent to public release if accepted. TL;DR is optional, maximum 250 characters. AIWILD additionally requires `Regular Paper` or `Short Paper`; choose Regular Paper. IAB's retrieved ordinary form has no separate paper-track selector.

Neither retrieved submission schema has a supplementary upload field. A later or authenticated attachment workflow is **unverified**; do not assume main-track ZIP rules apply. Technical appendices are included in each draft PDF. An anonymous analysis ZIP is prepared locally for use only if a permitted supplementary route is available.

The IAB schema has `duedate` 2026-09-06 11:59 UTC, matching the published date. AIWILD has `duedate` 2026-09-06 13:00 UTC, one hour later than the website's AoE interpretation. Use the earlier published deadline; do not rely on schema expiration/grace timestamps. Authenticated access, live submit-button availability, and any additional account-specific requirements have not been tested. Portals: [IAB](https://openreview.net/group?id=NeurIPS.cc/2026/Workshop/IAB), [AIWILD](https://openreview.net/group?id=NeurIPS.cc/2026/Workshop/AIWILD).

## Official template and main-track distinctions

The style file was extracted unchanged from the [official 2026 template archive](https://media.neurips.cc/Conferences/NeurIPS2026/Formatting_Instructions_For_NeurIPS_2026.zip), linked by the [2026 Call for Papers](https://neurips.cc/Conferences/2026/CallForPapers). Both wrappers use `dblblindworkshop`, with `workshoptitle{Interpreting Agent Behavior}` or `workshoptitle{Agents in the Wild}`. No final/preprint mode, margin changes, or body-font changes are used. The official style omits the workshop name in its default review footer; the shared preamble changes only that notice text to display the configured workshop title. The downloaded style file remains byte-for-byte unchanged.

The [main-track handbook, V2026.3](https://neurips.cc/Conferences/2026/MainTrackHandbook) requires nine content pages, a mandatory checklist, a single PDF up to 50 MB, and an optional anonymous code/data ZIP up to 100 MB. Those main-track submission mechanics are **not automatically workshop rules**. Its author policy asks for methodological disclosure where LLM use is an important component; ordinary editing assistance need not be documented. Authors remain responsible for correctness. Both workshops explicitly adopt this LLM policy. Main-track May 4/6 abstract/paper deadlines and reciprocal-reviewing mechanics do not govern these workshop drafts.

## Exact manual submission steps

1. Confirm the deadline and the chosen workshop's live portal before proceeding; resolve any IAB checklist question and any supplementary-field uncertainty.
2. All authors review the paper, author order, conflicts, originality, cited work, and LLM disclosure. Confirm that concurrent workshop submission is permitted by every applicable venue policy.
3. Use the ordinary IAB submission route or AIWILD Regular Paper. Enter the prepared title, abstract, keywords, and optional TL;DR from `SUBMISSION_METADATA.md`; enter real authors in the form only.
4. Select the corresponding anonymous PDF. Check its first-page workshop footer, content-page count, figure readability, and absence of identifying metadata. Never upload the private project archive or evidence mappings.
5. If the portal permits a supplementary attachment, use only the anonymous analysis package, within the portal's verified limit. The initially retrieved forms have no such field.
6. The submitting author reviews the two consent fields, any live declarations, and the rendered entry, then submits and saves the receipt. These consent and submission steps have not been performed by the writing agent.
