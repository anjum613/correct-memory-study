#!/usr/bin/env python3
"""Build adjudicated external-identification audit records from frozen inputs."""

from __future__ import annotations

from copy import deepcopy
import hashlib
from io import StringIO
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
AUDIT_ROOT = REPOSITORY_ROOT / "audits" / "external-identification-v1"
RAW_ROOT = AUDIT_ROOT / "raw"
PAPER_ROOT = AUDIT_ROOT / "papers"
PROTOCOL_PATH = REPOSITORY_ROOT / "protocols" / "external-identification-audit-v1.yaml"
TABLE_DATA_PATH = AUDIT_ROOT / "table-data.yaml"

RAW_HASHES = {
    "reviewer-a.yaml": "743f26d675c0578adf534229cdf380b708a9f6450dc679411c0a030649d06820",
    "reviewer-b.yaml": "94ac0e3f027af0bab8c659971248266fdf3e62f6aae35a2b9078c6982566cdaf",
}

PAPER_FILENAMES = {
    "BASM_WHEN_NOT_TO_IMITATE": "01-basm-when-not-to-imitate.yaml",
    "AGENT_SKILLS_CAN_BE_HARMFUL": "02-agent-skills-can-be-harmful.yaml",
    "SLBENCH": "03-slbench.yaml",
    "SWE_SKILLS_BENCH": "04-swe-skills-bench.yaml",
    "EXPERIENCE_DRIVEN_SELF_EVOLVING_SAFETY": (
        "05-experience-driven-self-evolving-safety.yaml"
    ),
    "SECUREVIBEBENCH": "06-securevibebench.yaml",
}

SOURCE_URLS = {
    "BASM_WHEN_NOT_TO_IMITATE": [
        {
            "TYPE": "OFFICIAL_ARXIV_ABSTRACT",
            "URL": "https://arxiv.org/abs/2608.22339",
            "VERSION_OR_DATE": "v1, 2026-08-23",
            "ACCESS_STATUS": "ACCESSIBLE",
        },
        {
            "TYPE": "OFFICIAL_ARXIV_HTML",
            "URL": "https://arxiv.org/html/2608.22339v1",
            "VERSION_OR_DATE": "v1",
            "ACCESS_STATUS": "ACCESSIBLE",
        },
    ],
    "AGENT_SKILLS_CAN_BE_HARMFUL": [
        {
            "TYPE": "OFFICIAL_ARXIV_ABSTRACT",
            "URL": "https://arxiv.org/abs/2608.11888",
            "VERSION_OR_DATE": "v1, 2026-08-12",
            "ACCESS_STATUS": "ACCESSIBLE",
        },
        {
            "TYPE": "OFFICIAL_ARXIV_HTML",
            "URL": "https://arxiv.org/html/2608.11888v1",
            "VERSION_OR_DATE": "v1",
            "ACCESS_STATUS": "ACCESSIBLE",
        },
    ],
    "SLBENCH": [
        {
            "TYPE": "OFFICIAL_ARXIV_ABSTRACT",
            "URL": "https://arxiv.org/abs/2607.09016",
            "VERSION_OR_DATE": "v1, 2026-07-10",
            "ACCESS_STATUS": "ACCESSIBLE",
        },
        {
            "TYPE": "OFFICIAL_ARXIV_HTML",
            "URL": "https://arxiv.org/html/2607.09016v1",
            "VERSION_OR_DATE": "v1",
            "ACCESS_STATUS": "ACCESSIBLE",
        },
    ],
    "SWE_SKILLS_BENCH": [
        {
            "TYPE": "OFFICIAL_ARXIV_ABSTRACT",
            "URL": "https://arxiv.org/abs/2603.15401",
            "VERSION_OR_DATE": "v1, 2026-03-16",
            "ACCESS_STATUS": "ACCESSIBLE",
        },
        {
            "TYPE": "OFFICIAL_ARXIV_HTML",
            "URL": "https://arxiv.org/html/2603.15401v1",
            "VERSION_OR_DATE": "v1",
            "ACCESS_STATUS": "ACCESSIBLE",
        },
        {
            "TYPE": "OFFICIAL_AUTHOR_REPOSITORY_LINK_AS_PRINTED",
            "URL": "https://github.com/GeniusHTX/SWE-Skills-Bench",
            "VERSION_OR_DATE": "accessed 2026-09-03",
            "ACCESS_STATUS": "DIRECT_PAGE_HTTP_404",
        },
        {
            "TYPE": "OFFICIAL_DATASET",
            "URL": "https://huggingface.co/datasets/GeniusHTX/SWE-Skills-Bench",
            "VERSION_OR_DATE": "accessed 2026-09-03",
            "ACCESS_STATUS": "ACCESSIBLE",
        },
    ],
    "EXPERIENCE_DRIVEN_SELF_EVOLVING_SAFETY": [
        {
            "TYPE": "OFFICIAL_ACL_ANTHOLOGY_PAGE",
            "URL": "https://aclanthology.org/2026.findings-acl.2091/",
            "VERSION_OR_DATE": "proceedings version, July 2026",
            "ACCESS_STATUS": "ACCESSIBLE",
        },
        {
            "TYPE": "OFFICIAL_ACL_ANTHOLOGY_PDF",
            "URL": "https://aclanthology.org/2026.findings-acl.2091.pdf",
            "VERSION_OR_DATE": "proceedings version, July 2026",
            "ACCESS_STATUS": "ACCESSIBLE",
        },
        {
            "TYPE": "OFFICIAL_DOI",
            "URL": "https://doi.org/10.18653/v1/2026.findings-acl.2091",
            "VERSION_OR_DATE": "2026",
            "ACCESS_STATUS": "ACCESSIBLE",
        },
        {
            "TYPE": "OFFICIAL_ARXIV_ABSTRACT",
            "URL": "https://arxiv.org/abs/2604.16968",
            "VERSION_OR_DATE": "v1, 2026-04-18",
            "ACCESS_STATUS": "ACCESSIBLE",
        },
        {
            "TYPE": "OFFICIAL_ARXIV_HTML",
            "URL": "https://arxiv.org/html/2604.16968v1",
            "VERSION_OR_DATE": "v1",
            "ACCESS_STATUS": "ACCESSIBLE",
        },
    ],
    "SECUREVIBEBENCH": [
        {
            "TYPE": "OFFICIAL_ACL_ANTHOLOGY_PAGE",
            "URL": "https://aclanthology.org/2026.acl-long.1107/",
            "VERSION_OR_DATE": "proceedings version, July 2026",
            "ACCESS_STATUS": "ACCESSIBLE",
        },
        {
            "TYPE": "OFFICIAL_ACL_ANTHOLOGY_PDF",
            "URL": "https://aclanthology.org/2026.acl-long.1107.pdf",
            "VERSION_OR_DATE": "proceedings version, July 2026",
            "ACCESS_STATUS": "ACCESSIBLE",
        },
        {
            "TYPE": "OFFICIAL_DOI",
            "URL": "https://doi.org/10.18653/v1/2026.acl-long.1107",
            "VERSION_OR_DATE": "2026",
            "ACCESS_STATUS": "ACCESSIBLE",
        },
        {
            "TYPE": "OFFICIAL_ARXIV_ABSTRACT",
            "URL": "https://arxiv.org/abs/2509.22097",
            "VERSION_OR_DATE": "v5, 2026-06-06",
            "ACCESS_STATUS": "ACCESSIBLE",
        },
        {
            "TYPE": "OFFICIAL_ARXIV_HTML",
            "URL": "https://arxiv.org/html/2509.22097v5",
            "VERSION_OR_DATE": "v5",
            "ACCESS_STATUS": "ACCESSIBLE",
        },
        {
            "TYPE": "OFFICIAL_AUTHOR_REPOSITORY",
            "URL": "https://github.com/iCSawyer/SecureVibeBench",
            "VERSION_OR_DATE": (
                "main HEAD 47c452becd3011ad948876e7cf0f3cca5846802d, "
                "resolved 2026-09-03"
            ),
            "ACCESS_STATUS": "ACCESSIBLE",
        },
        {
            "TYPE": "OFFICIAL_DATASET",
            "URL": "https://huggingface.co/datasets/iCSawyer/SecureVibeBench",
            "VERSION_OR_DATE": "accessed 2026-09-03",
            "ACCESS_STATUS": "ACCESSIBLE",
        },
    ],
}

REPOSITORIES = {
    "SWE_SKILLS_BENCH": {
        "URL": "https://github.com/GeniusHTX/SWE-Skills-Bench",
        "COMMIT_OR_VERSION": "4ac6441a446063066f103bb71faee3b0e89dbc22",
        "COMMIT_RESOLUTION_SOURCE": (
            "Official GitHub commits/master metadata exposed the SHA on "
            "2026-09-03, but direct repository and commit pages returned HTTP "
            "404; repository contents were not used as criterion evidence."
        ),
        "ACCESS_STATUS": "PARTIAL_METADATA_ONLY_DIRECT_PAGE_HTTP_404",
    },
    "SECUREVIBEBENCH": {
        "URL": "https://github.com/iCSawyer/SecureVibeBench",
        "COMMIT_OR_VERSION": "47c452becd3011ad948876e7cf0f3cca5846802d",
        "COMMIT_RESOLUTION_SOURCE": (
            "Official GitHub main history and commit page, resolved "
            "2026-09-03."
        ),
        "ACCESS_STATUS": "ACCESSIBLE",
    },
}

FINAL_SYNTHESIS = {
    "BASM_WHEN_NOT_TO_IMITATE": {
        "SUPPORTED_INTERPRETATION": (
            "Within the reported tool-use benchmarks and model settings, "
            "explicit boundary content changes wrong-tool preferences and "
            "several benchmark outcomes beyond procedural-only and equal-length "
            "controls. The evidence supports a boundary-aware memory effect for "
            "these configurations."
        ),
        "INTERPRETATIONS_NOT_ESTABLISHED": [
            "That every evaluated task rejects an initial no-op.",
            "That source procedures are independently safe under the same "
            "focal security witness used at target.",
            "That AgentDojo marginals identify task-complete insecurity for one "
            "requested feature.",
            "That runtime and all other delivery resources are balanced, source "
            "selection is outcome-blind, or applicability is the sole major "
            "source-target mismatch.",
        ],
        "ADDITIONAL_EVIDENCE_REQUIRED_FOR_OUR_ESTIMAND": [
            "Per-target initial-state and no-op validation.",
            "Same-request insecure and secure task-completing states with feature "
            "retention and one focal witness.",
            "Source-context execution showing the transferred procedure is both "
            "functionally correct and focal-safe.",
            "Pair-level evidence that a named security predicate is true at "
            "source and false at target without a second major mismatch.",
            "Outcome-blind source locking, complete resource treatment, and a "
            "joint task-complete-security outcome.",
        ],
    },
    "AGENT_SKILLS_CAN_BE_HARMFUL": {
        "SUPPORTED_INTERPRETATION": (
            "For the retained contrastive cases, trace and verifier or cost "
            "evidence associates particular loaded skills with functional "
            "regressions or large cost regressions relative to a same-task "
            "reference. The taxonomy describes recurring mechanisms in this "
            "deliberately outcome-selected diagnostic corpus."
        ),
        "INTERPRETATIONS_NOT_ESTABLISHED": [
            "A population prevalence or average causal effect for harmful skills.",
            "A focal security effect or a source-safe applicability-predicate shift.",
            "Robustness of each single-execution contrast to independent reruns.",
            "Prospective outcome-blind reuse of a retained case for the stronger "
            "transfer estimand; corpus inclusion is intentionally outcome-defined.",
        ],
        "ADDITIONAL_EVIDENCE_REQUIRED_FOR_OUR_ESTIMAND": [
            "A prospectively locked source procedure demonstrated correct and "
            "focal-safe in its source context.",
            "A named security applicability predicate verified true at source and "
            "false at a matched target without a second major mismatch.",
            "Target no-op validation, insecure and secure task-completing states, "
            "feature retention, and an executable focal security witness.",
            "A resource-matched memory-content comparison, focal uptake evidence, "
            "joint task/security scoring, and repeated executions where needed.",
        ],
    },
    "SLBENCH": {
        "SUPPORTED_INTERPRETATION": (
            "For the curated source-grounded cases, the evaluated agents often "
            "produce artifact-level violations of explicit skill relations. "
            "Deterministic graders, inconclusive outcomes, safe-control cases, "
            "and targeted SLGuard comparisons support the paper's relation-"
            "following claim."
        ),
        "INTERPRETATIONS_NOT_ESTABLISHED": [
            "A source procedure independently demonstrated correct and focal-safe.",
            "A source-to-target security-precondition shift isolated from other "
            "mismatches.",
            "A task-complete-insecurity effect with same-request secure and "
            "insecure functional controls.",
            "A checklist semantic effect separated from generic extra context, or "
            "outcome-blind choice of the targeted mitigation subset.",
        ],
        "ADDITIONAL_EVIDENCE_REQUIRED_FOR_OUR_ESTIMAND": [
            "A genuinely incomplete target and joint functional/security controls "
            "with feature retention.",
            "A source execution proving procedural correctness and focal safety.",
            "A named predicate verified true at source and false at target, with "
            "procedural relevance and no second major mismatch.",
            "Outcome-blind source locking, a resource-matched semantic control, "
            "focal uptake evidence, and joint task/security outcomes.",
        ],
    },
    "SWE_SKILLS_BENCH": {
        "SUPPORTED_INTERPRETATION": (
            "For the generated task suite and single Claude Code/Haiku 4.5 "
            "configuration, making the selected skill available changes average "
            "functional success little and increases average token use. The "
            "Linkerd trace supports one concrete context-interference mechanism."
        ),
        "INTERPRETATIONS_NOT_ESTABLISHED": [
            "That every generated task is initially unsatisfied by the untouched "
            "repository.",
            "A focal security or source-safe precondition-shift effect.",
            "A semantic content effect separated from all generic context and "
            "resource burdens.",
            "Run-level stochastic stability or generalization beyond the single "
            "agent/backbone and authored task distribution.",
        ],
        "ADDITIONAL_EVIDENCE_REQUIRED_FOR_OUR_ESTIMAND": [
            "Per-task initial-state and no-op validation.",
            "A source execution demonstrated correct and focal-safe under the same "
            "security witness.",
            "A named security predicate and a matched source-target pair differing "
            "on that predicate without a second major mismatch.",
            "Same-request insecure and secure task-completing states with feature "
            "retention and an executable security witness.",
            "Resource-matched content controls, outcome-blind source assignment, "
            "systematic focal uptake, joint outcomes, and appropriate reruns.",
        ],
    },
    "EXPERIENCE_DRIVEN_SELF_EVOLVING_SAFETY": {
        "SUPPORTED_INTERPRETATION": (
            "Across the reported frameworks, backbones, and safety benchmarks, "
            "retrieved experience increases unsafe compliance relative to the "
            "pre-evolution or no-experience state. Length-matched controls, dose "
            "patterns, behavioral cases, and attribution analyses support an "
            "execution-oriented content mechanism; refusal experience exposes a "
            "safety-utility trade-off."
        ),
        "INTERPRETATIONS_NOT_ESTABLISHED": [
            "That each source procedure is functionally correct and focal-safe "
            "under the target witness.",
            "A prospectively named procedure-level applicability predicate or a "
            "pair isolated to that predicate.",
            "A change in task-complete insecurity for a legitimate requested "
            "feature with matched secure and insecure controls.",
            "Seed-level robustness of stochastic and longitudinal comparisons.",
        ],
        "ADDITIONAL_EVIDENCE_REQUIRED_FOR_OUR_ESTIMAND": [
            "One concrete source procedure shown correct and focal-safe under the "
            "same witness.",
            "A predeclared procedure-level predicate shown true at source and false "
            "at a closely matched target, with other major mismatches excluded.",
            "A genuinely incomplete legitimate target with task-completing insecure "
            "and secure controls and feature retention.",
            "A joint task-completion/security endpoint, outcome-blind source "
            "assignment, focal uptake evidence, and independent repetitions.",
        ],
    },
    "SECUREVIBEBENCH": {
        "SUPPORTED_INTERPRETATION": (
            "On 105 reconstructed C/C++ scenarios, generated patches are jointly "
            "classified by differential functionality, a dynamic focal "
            "vulnerability witness, and static new-risk findings. The benchmark "
            "contains task-completing vulnerable and secure states and keeps "
            "security interpretable alongside functionality."
        ),
        "INTERPRETATIONS_NOT_ESTABLISHED": [
            "That every untouched parent repository fails the reconstructed "
            "functional request.",
            "That static suspicious findings are confirmed vulnerabilities; the "
            "paper explicitly avoids that interpretation.",
            "Stability across repeated stochastic agent executions.",
            "Any causal effect of procedural memory or of a source-to-target "
            "applicability-condition shift.",
        ],
        "ADDITIONAL_EVIDENCE_REQUIRED_FOR_OUR_ESTIMAND": [
            "A systematic untouched-repository no-op check.",
            "A source procedural memory demonstrated functionally correct and safe "
            "under the same focal witness.",
            "Evidence of shared procedure, a named predicate true at source and "
            "false at target, and no second major mismatch.",
            "Faithful and outcome-blind memory assignment, resource-matched content "
            "controls, direct uptake measurement, and repeated comparisons.",
            "The existing joint outcome categories, dynamic witness, and observed "
            "secure and vulnerable functional states can support the target-outcome "
            "component after the no-op gap is addressed.",
        ],
    },
}


def _yaml_load(path: Path) -> dict[str, Any]:
    parser = YAML(typ="safe")
    parser.allow_duplicate_keys = False
    data = parser.load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a YAML mapping")
    return data


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _yaml_text(data: dict[str, Any]) -> str:
    emitter = YAML()
    emitter.default_flow_style = False
    emitter.allow_unicode = True
    emitter.width = 88
    emitter.indent(mapping=2, sequence=4, offset=2)
    stream = StringIO()
    emitter.dump(data, stream)
    return stream.getvalue()


def _paper_index(review: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {paper["PAPER_ID"]: paper for paper in review["PAPERS"]}


def _adjudication_index(
    reconciliation: dict[str, Any],
) -> dict[tuple[str, str], dict[str, Any]]:
    return {
        (item["PAPER_ID"], item["CRITERION"]): item
        for item in reconciliation["ADJUDICATIONS"]
    }


def _final_rating(
    paper_id: str,
    criterion: str,
    rating_a: dict[str, Any],
    rating_b: dict[str, Any],
    adjudications: dict[tuple[str, str], dict[str, Any]],
) -> dict[str, Any]:
    if rating_a["STATUS"] == rating_b["STATUS"]:
        return deepcopy(rating_a)

    item = adjudications[(paper_id, criterion)]
    final_status = item["FINAL_ADJUDICATED"]
    matching = [
        rating
        for rating in (rating_a, rating_b)
        if rating["STATUS"] == final_status
    ]
    applicability = (
        matching[0]["APPLICABILITY_RATIONALE"]
        if matching
        else item["RATIONALE"]
    )
    return {
        "STATUS": final_status,
        "APPLICABILITY_RATIONALE": applicability,
        "EVIDENCE_LOCATION": item["EVIDENCE"],
        "EVIDENCE_SUMMARY": item["RATIONALE"],
    }


def _official_repository(
    paper_id: str, source_paper: dict[str, Any]
) -> dict[str, Any]:
    if paper_id in REPOSITORIES:
        return deepcopy(REPOSITORIES[paper_id])
    return deepcopy(source_paper["OFFICIAL_REPOSITORY"])


def build_paper_records() -> list[Path]:
    for filename, expected_hash in RAW_HASHES.items():
        observed = _sha256(RAW_ROOT / filename)
        if observed != expected_hash:
            raise ValueError(
                f"frozen raw review changed: {filename}: {observed} != {expected_hash}"
            )

    review_a = _yaml_load(RAW_ROOT / "reviewer-a.yaml")
    review_b = _yaml_load(RAW_ROOT / "reviewer-b.yaml")
    reconciliation = _yaml_load(AUDIT_ROOT / "reconciliation.yaml")
    papers_a = _paper_index(review_a)
    papers_b = _paper_index(review_b)
    adjudications = _adjudication_index(reconciliation)

    if set(papers_a) != set(PAPER_FILENAMES) or set(papers_b) != set(PAPER_FILENAMES):
        raise ValueError("raw reviews do not contain the six frozen paper identifiers")

    PAPER_ROOT.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for paper_id, filename in PAPER_FILENAMES.items():
        paper_a = papers_a[paper_id]
        paper_b = papers_b[paper_id]
        final_ratings = {
            criterion: _final_rating(
                paper_id,
                criterion,
                rating_a,
                paper_b["RATINGS"][criterion],
                adjudications,
            )
            for criterion, rating_a in paper_a["RATINGS"].items()
        }

        record = {
            "PAPER_ID": paper_id,
            "TITLE": paper_a["TITLE"],
            "AUTHORS": deepcopy(paper_a["AUTHORS"]),
            "VERSION": paper_a["VERSION"],
            "VENUE_OR_STATUS": paper_a["VENUE_OR_STATUS"],
            "SOURCE_URLS": deepcopy(SOURCE_URLS[paper_id]),
            "OFFICIAL_REPOSITORY": _official_repository(paper_id, paper_a),
            "STATED_PRIMARY_CLAIM": paper_a["STATED_PRIMARY_CLAIM"],
            "STATED_UNIT_OF_ANALYSIS": paper_a["STATED_UNIT_OF_ANALYSIS"],
            "MEMORY_OR_SKILL_TREATMENT": deepcopy(
                paper_a["MEMORY_OR_SKILL_TREATMENT"]
            ),
            "CONTROL_CONDITIONS": deepcopy(paper_a["CONTROL_CONDITIONS"]),
            "TARGET_TYPE": paper_a["TARGET_TYPE"],
            "FUNCTIONAL_ENDPOINT": paper_a["FUNCTIONAL_ENDPOINT"],
            "SECURITY_ENDPOINT_IF_ANY": paper_a["SECURITY_ENDPOINT_IF_ANY"],
            "REVIEWER_A_RATINGS": deepcopy(paper_a["RATINGS"]),
            "REVIEWER_B_RATINGS": deepcopy(paper_b["RATINGS"]),
            "ADJUDICATED_RATINGS": final_ratings,
            **deepcopy(FINAL_SYNTHESIS[paper_id]),
        }
        destination = PAPER_ROOT / filename
        destination.write_text(_yaml_text(record), encoding="utf-8")
        written.append(destination)
    return written


def build_table_data(paper_paths: list[Path]) -> Path:
    protocol = _yaml_load(PROTOCOL_PATH)
    papers = [_yaml_load(path) for path in paper_paths]
    criteria = [
        (criterion, definition)
        for group in protocol["IDENTIFICATION_REQUIREMENTS"].values()
        for criterion, definition in group.items()
    ]
    expected_papers = [
        item["PAPER_ID"] for item in protocol["PRIMARY_AUDIT_TARGETS"]
    ]
    if [paper["PAPER_ID"] for paper in papers] != expected_papers:
        raise ValueError("paper records do not follow the frozen slot order")

    table_data = {
        "TABLE_DATA_ID": "EXTERNAL_IDENTIFICATION_AUDIT_V1_PAPER_TABLES",
        "PROTOCOL_PATH": str(PROTOCOL_PATH.relative_to(REPOSITORY_ROOT)),
        "NOT_A_PREVALENCE_STUDY": True,
        "PAPER_COLUMNS": [
            {"PAPER_ID": paper["PAPER_ID"], "TITLE": paper["TITLE"]}
            for paper in papers
        ],
        "REQUIREMENTS_BY_PAPER": {
            "ROW_COUNT": len(criteria),
            "COLUMN_COUNT": len(papers),
            "CELL_STATUS_VOCABULARY": deepcopy(protocol["ALLOWED_STATUSES"]),
            "ROWS": [
                {
                    "CRITERION": criterion,
                    "DEFINITION": definition,
                    "CELLS": {
                        paper["PAPER_ID"]: paper["ADJUDICATED_RATINGS"][
                            criterion
                        ]["STATUS"]
                        for paper in papers
                    },
                }
                for criterion, definition in criteria
            ],
        },
        "CLAIM_DESIGN_GAP_BY_PAPER": {
            "ROW_COUNT": len(papers),
            "ROWS": [
                {
                    "PAPER_ID": paper["PAPER_ID"],
                    "STATED_CLAIM": paper["STATED_PRIMARY_CLAIM"],
                    "DESIGN_ESTABLISHES": paper["SUPPORTED_INTERPRETATION"],
                    "ADDITIONAL_EVIDENCE_FOR_STRONGER_SECURITY_TRANSFER_CLAIM": (
                        deepcopy(
                            paper[
                                "ADDITIONAL_EVIDENCE_REQUIRED_FOR_OUR_ESTIMAND"
                            ]
                        )
                    ),
                }
                for paper in papers
            ],
        },
        "INTERPRETATION_BOUNDARY": (
            "Cells are claim-relative ratings, not paper grades. NOT_APPLICABLE "
            "means the criterion is not required for that paper's stated "
            "estimand. Counts over this deliberately selected set are not "
            "literature prevalence estimates."
        ),
    }
    TABLE_DATA_PATH.write_text(_yaml_text(table_data), encoding="utf-8")
    return TABLE_DATA_PATH


def main() -> int:
    paper_paths = build_paper_records()
    written = [*paper_paths, build_table_data(paper_paths)]
    for path in written:
        print(path.relative_to(REPOSITORY_ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
