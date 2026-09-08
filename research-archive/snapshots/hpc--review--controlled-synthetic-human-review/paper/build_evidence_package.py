#!/usr/bin/env python3
"""Build publication-only derivatives from the frozen scientific evidence."""

from __future__ import annotations

import csv
from hashlib import sha256
import io
from pathlib import Path
import sys
import types
from typing import Any, Iterable, Mapping, Sequence

from ruamel.yaml import YAML


REPO_ROOT = Path(__file__).resolve().parents[1]
PAPER_ROOT = REPO_ROOT / "paper"
DATA_ROOT = PAPER_ROOT / "data"
HUMAN_ROOT = PAPER_ROOT / "human-review"
TABLE_ROOT = PAPER_ROOT / "tables"

PAPER_IDS = (
    "BASM_WHEN_NOT_TO_IMITATE",
    "AGENT_SKILLS_CAN_BE_HARMFUL",
    "SLBENCH",
    "SWE_SKILLS_BENCH",
    "EXPERIENCE_DRIVEN_SELF_EVOLVING_SAFETY",
    "SECUREVIBEBENCH",
)
PAPER_ABBREVIATIONS = {
    "BASM_WHEN_NOT_TO_IMITATE": "BASM",
    "AGENT_SKILLS_CAN_BE_HARMFUL": "Harmful skills",
    "SLBENCH": "SLBench",
    "SWE_SKILLS_BENCH": "SWE-Skills",
    "EXPERIENCE_DRIVEN_SELF_EVOLVING_SAFETY": "Evolving safety",
    "SECUREVIBEBENCH": "SecureVibeBench",
}
STATUS_VOCABULARY = {
    "ESTABLISHED",
    "NOT_ESTABLISHED",
    "UNDETERMINED",
    "NOT_APPLICABLE",
}
GROUP_LABELS = {
    "GROUP_A_TARGET_OUTCOME_VALIDITY": "A. Target / outcome validity",
    "GROUP_B_SOURCE_TRANSFER_VALIDITY": "B. Source / transfer validity",
    "GROUP_C_TREATMENT_VALIDITY": "C. Treatment validity",
    "GROUP_D_PROCESS_ANALYSIS_VALIDITY": "D. Process / analysis validity",
}
AGREEMENT_SAMPLE_DOMAIN = "cmpilot-paper-human-review-agreement-v1"
HUMAN_VERIFICATION_PROTOCOL = (
    "paper/human-review/human-verification-protocol.yaml"
)
HUMAN_RESPONSE_OPTIONS = ("AGREE", "DISAGREE", "CANNOT_DETERMINE")
HUMAN_RESPONSE_RECORD_FIELDS = (
    "REVIEWER_ID_OR_PSEUDONYM",
    "HUMAN_RESPONSE",
    "HUMAN_PREFERRED_STATUS",
    "HUMAN_RATIONALE",
    "HUMAN_ORIGINAL_SOURCE_EVIDENCE_LOCATION",
    "CORRECTION_BASIS",
)


CONTRACT_DETAILS: Mapping[str, tuple[str, str, str]] = {
    "A1_TARGET_TASK_INCOMPLETENESS": (
        "Nontrivial target",
        "Licenses interpreting later task success as newly achieved rather than pre-existing or no-op success.",
        "A passing endpoint can be mistaken for implementation even when the requested behavior was already present.",
    ),
    "A2_INSECURE_TASK_COMPLETING_CONTROL": (
        "Insecure completion",
        "Shows that task completion and focal insecurity can coexist, so the harmful endpoint is attainable.",
        "Security failure can be conflated with failure to implement the requested task.",
    ),
    "A3_SECURE_TASK_COMPLETING_CONTROL": (
        "Secure completion",
        "Shows that the requested task can be completed while satisfying the same focal security property.",
        "The design can mistake an impossible security requirement for agent failure or treatment harm.",
    ),
    "A4_FEATURE_RETENTION": (
        "Feature retention",
        "Licenses treating the secure state as a repair of the same task rather than removal of the feature.",
        "Deleting or weakening the requested behavior can masquerade as a secure repair.",
    ),
    "A5_FOCAL_SECURITY_WITNESS": (
        "Focal witness",
        "Makes the security component of task-complete insecurity an independently grounded outcome.",
        "A proxy or nondiscriminating test can label states safe or unsafe without measuring the focal property.",
    ),
    "B1_SOURCE_FUNCTIONAL_CORRECTNESS": (
        "Source correctness",
        "Supports describing the donated procedure as one that worked in its original context.",
        "A broken source episode can be mischaracterized as successful procedural knowledge.",
    ),
    "B2_SOURCE_FOCAL_SAFETY": (
        "Source focal safety",
        "Supports the claim that a focal-safe source procedure, rather than an already unsafe one, is transferred.",
        "Target insecurity can be attributed to lost applicability when the donor was never focal-safe.",
    ),
    "B3_PROCEDURAL_RELEVANCE": (
        "Procedural relevance",
        "Connects the delivered source episode to the operation required by the target task.",
        "Topical or lexical similarity can be mistaken for transfer of the operative procedure.",
    ),
    "B4_EXPLICIT_APPLICABILITY_PREDICATE": (
        "Applicability predicate",
        "States the condition under which the relevant source procedure is expected to transfer safely.",
        "Relevance can silently stand in for applicability, leaving the proposed failure mechanism unspecified.",
    ),
    "B5_SOURCE_TARGET_PSTAR_SHIFT": (
        "Directional predicate shift",
        "Grounds the intended source-to-target change by showing the named predicate true at source and false at target.",
        "A merely asserted context difference can be mistaken for the security-relevant applicability shift.",
    ),
    "B6_NO_SECOND_MAJOR_MISMATCH": (
        "No major co-mismatch",
        "Makes the named applicability shift the salient pair-level incompatibility rather than one of several alternatives.",
        "A second framework, API, or task mismatch can explain failure attributed to the focal predicate.",
    ),
    "C1_MEMORY_OR_SKILL_FIDELITY": (
        "Delivery fidelity",
        "Defines a reproducible assigned intervention and verifies delivery of the intended source episode.",
        "The analyzed treatment can differ from the memory or skill the causal claim names.",
    ),
    "C2_RESOURCE_BALANCED_COMPARISON": (
        "Resource balance",
        "Separates or explicitly defines semantic content effects relative to context, action, tool, and runtime burden.",
        "Resource displacement caused by delivery can be attributed to procedural semantics.",
    ),
    "C3_APPROPRIATE_CONTROL_CONDITION": (
        "Semantic control",
        "Provides the comparator required to isolate relevant memory content from generic extra-context effects.",
        "Any effect of loading additional material can be called an effect of the relevant procedure.",
    ),
    "C4_OUTCOME_BLIND_SOURCE_OR_SKILL_SELECTION": (
        "Outcome-blind source lock",
        "Prevents target outcomes from influencing which donor procedure becomes the treatment.",
        "Outcome-guided treatment selection can be mistaken for prospective causal evidence or frequency.",
    ),
    "D1_UPTAKE_OR_BEHAVIORAL_ENGAGEMENT_MEASURED": (
        "Delivery / uptake separation",
        "Supports mechanism claims by distinguishing assigned and delivered memory from behavioral engagement with it.",
        "Delivery alone can be reported as procedural use, or post-treatment uptake can be treated as baseline eligibility.",
    ),
    "D2_TASK_AND_SECURITY_JOINTLY_INTERPRETABLE": (
        "Joint task-security outcome",
        "Identifies task-complete insecurity directly without conditioning security on a treatment-responsive success variable.",
        "Separate marginals or selected successful runs can answer a different causal question.",
    ),
    "D3_UNIT_AND_REPLICATION_VALIDITY": (
        "Valid units and replication",
        "Aligns uncertainty and evidence strength with distinct tasks or genuinely varying executions.",
        "Deterministic duplicates can be counted as independent evidence and yield spurious precision.",
    ),
}


def _yaml_load(path: Path) -> Any:
    return YAML(typ="safe").load(path.read_text(encoding="utf-8"))


def _yaml_dump(path: Path, data: Any) -> None:
    writer = YAML()
    writer.default_flow_style = False
    writer.width = 100
    writer.indent(mapping=2, sequence=4, offset=2)
    with path.open("w", encoding="utf-8") as stream:
        writer.dump(data, stream)


def _write_csv(path: Path, fieldnames: Sequence[str], rows: Iterable[Mapping[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _sha(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _tex(value: Any) -> str:
    text = str(value)
    replacements = (
        ("\\", r"\textbackslash{}"),
        ("&", r"\&"),
        ("%", r"\%"),
        ("$", r"\$"),
        ("#", r"\#"),
        ("_", r"\_"),
        ("{", r"\{"),
        ("}", r"\}"),
        ("~", r"\textasciitilde{}"),
        ("^", r"\textasciicircum{}"),
        ("→", r"$\rightarrow$"),
    )
    for old, new in replacements:
        text = text.replace(old, new)
    return text


def _write_tex(path: Path, lines: Sequence[str]) -> None:
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _install_yaml_compatibility() -> None:
    """Expose the small PyYAML API used by the frozen control without editing it."""
    try:
        __import__("yaml")
        return
    except ModuleNotFoundError:
        pass
    shim = types.ModuleType("yaml")

    def safe_load(stream: Any) -> Any:
        return YAML(typ="safe").load(stream)

    def safe_dump(data: Any, sort_keys: bool = True) -> str:
        del sort_keys
        output = io.StringIO()
        YAML().dump(data, output)
        return output.getvalue()

    shim.safe_load = safe_load  # type: ignore[attr-defined]
    shim.safe_dump = safe_dump  # type: ignore[attr-defined]
    sys.modules["yaml"] = shim


def _flatten_requirements(protocol: Mapping[str, Any]) -> list[tuple[str, str, str]]:
    rows: list[tuple[str, str, str]] = []
    for group_key, group in protocol["IDENTIFICATION_REQUIREMENTS"].items():
        for criterion, definition in group.items():
            rows.append((group_key, criterion, definition))
    return rows


def build_identification_contract() -> None:
    protocol = _yaml_load(REPO_ROOT / "protocols/external-identification-audit-v1.yaml")
    generic = _yaml_load(
        REPO_ROOT / "audits/external-identification-v1/generic-validity-comparison.yaml"
    )
    source_classifications = generic["REQUIREMENT_CLASSIFICATIONS"]
    rows = []
    for group, criterion, definition in _flatten_requirements(protocol):
        short_name, license_text, false_inference = CONTRACT_DETAILS[criterion]
        source_class = source_classifications[criterion]["CLASSIFICATION"]
        mapping = (
            "GENERIC_BENCHMARK_VALIDITY"
            if source_class == "GENERIC_VALIDITY_PRINCIPLE"
            else "SECURITY_PROCEDURAL_TRANSFER_SPECIALIZATION"
        )
        rows.append(
            {
                "GROUP": GROUP_LABELS[group],
                "REQUIREMENT_ID": criterion,
                "SHORT_NAME": short_name,
                "DEFINITION": definition,
                "CAUSAL_INTERPRETATION_LICENSED": license_text,
                "FALSE_INFERENCE_WHEN_ABSENT": false_inference,
                "VALIDITY_MAPPING": mapping,
                "FROZEN_COMPARISON_CLASSIFICATION": source_class,
            }
        )
    assert len(rows) == 18
    _write_csv(DATA_ROOT / "identification-contract.csv", tuple(rows[0]), rows)

    lines = [
        r"\begingroup",
        r"\scriptsize",
        r"\setlength{\tabcolsep}{2pt}",
        r"\begin{longtable}{@{}p{.055\linewidth}p{.12\linewidth}p{.235\linewidth}p{.225\linewidth}p{.225\linewidth}p{.07\linewidth}@{}}",
        r"\caption{Estimand-derived identification requirements. G denotes generic benchmark validity; S denotes a security procedural-transfer specialization.}\label{tab:contract}\\",
        r"\toprule",
        r"ID & Short name & Definition & Causal interpretation licensed & False inference if absent & Map \\",
        r"\midrule",
        r"\endfirsthead",
        r"\toprule",
        r"ID & Short name & Definition & Causal interpretation licensed & False inference if absent & Map \\",
        r"\midrule",
        r"\endhead",
    ]
    current_group = None
    for row in rows:
        if row["GROUP"] != current_group:
            current_group = row["GROUP"]
            lines.append(
                rf"\multicolumn{{6}}{{@{{}}l}}{{\textbf{{{_tex(current_group)}}}}} \\"
            )
        map_code = "G" if row["VALIDITY_MAPPING"] == "GENERIC_BENCHMARK_VALIDITY" else "S"
        lines.append(
            " & ".join(
                (
                    _tex(row["REQUIREMENT_ID"].split("_")[0]),
                    _tex(row["SHORT_NAME"]),
                    _tex(row["DEFINITION"]),
                    _tex(row["CAUSAL_INTERPRETATION_LICENSED"]),
                    _tex(row["FALSE_INFERENCE_WHEN_ABSENT"]),
                    map_code,
                )
            )
            + r" \\"
        )
    lines.extend((r"\bottomrule", r"\end{longtable}", r"\endgroup"))
    _write_tex(TABLE_ROOT / "identification-contract.tex", lines)


def build_v1_tables() -> None:
    ledger = _yaml_load(PAPER_ROOT / "claim-ledger.yaml")
    evidence = ledger["FROZEN_NUMERIC_EVIDENCE"]["V1_FORMATIVE_AUDIT"]
    metric_rows = [
        ("FUNCTIONALITY_PASS", "V1 functionality pass", "46/48", "Endpoint measured continuity, not requested-task completion."),
        ("EMPTY_FINAL_PATCH", "Empty final patch", "46/48", "Most trajectories made no repository change."),
        ("SECURITY_PASS", "Focal security pass", "0/48", "The focal security endpoint was at floor."),
        ("TREATED_NO_DETECTABLE_UPTAKE", "Treated: no detectable uptake", "22/24", "Post-treatment descriptive coding only."),
        ("TREATED_WEAK_LEXICAL_REFERENCE", "Treated: weak lexical reference", "2/24", "No concrete source fact or procedure was reused."),
        ("SUBSTANTIVE_PROCEDURAL_UPTAKE", "Treated: substantive procedural uptake", "0/24", "No general, source-specific, or faithful procedural uptake."),
        ("CONTEXT_EXHAUSTION", "Context exhaustion", "38/48", "Termination under the fixed physical context."),
        ("PAIRED_SEED_ENDPOINTS_IDENTICAL", "Paired-seed endpoints identical", "24/24", "Nominal seeds added no endpoint variation."),
        ("PAIRED_PATCH_HASHES_IDENTICAL", "Paired-seed patch hashes identical", "24/24", "Nominal seeds added no final-patch variation."),
    ]
    rows = []
    for key, label, display, interpretation in metric_rows:
        assert evidence[key] == display
        numerator, denominator = display.split("/")
        rows.append(
            {
                "METRIC": key,
                "LABEL": label,
                "NUMERATOR": numerator,
                "DENOMINATOR": denominator,
                "DISPLAY": display,
                "INTERPRETATION": interpretation,
                "SUPPORTING_ARTIFACT": "frozen V1 post-primary analysis; hash-bound in artifacts/v2-preflight/v1-immutability.json",
            }
        )
    _write_csv(DATA_ROOT / "v1-evidence.csv", tuple(rows[0]), rows)

    control_rows = []
    controls = evidence["TASK_ORACLE_CONTROLS"]
    for key, label in (
        ("UNTOUCHED_STATE_FUNCTIONALITY", "Untouched state"),
        ("EMPTY_PATCH_FUNCTIONALITY", "Empty patch"),
        ("IRRELEVANT_PATCH_FUNCTIONALITY", "Irrelevant patch"),
        ("NOMINAL_FAITHFUL_REUSE_FUNCTIONALITY", "Nominal faithful-reuse control"),
        ("SAFE_REPAIR_FUNCTIONALITY", "Safe repair"),
    ):
        assert controls[key] == "6/6 PASS"
        control_rows.append(
            {
                "STATE": key,
                "LABEL": label,
                "FUNCTIONALITY": "PASS",
                "FAMILIES_PASS": "6/6",
                "INTERPRETATION": "The V1 functionality oracle accepted this state in every family.",
                "SUPPORTING_ARTIFACT": "artifacts/v2-preflight/control-matrix.json",
            }
        )
    _write_csv(DATA_ROOT / "v1-oracle-controls.csv", tuple(control_rows[0]), control_rows)

    lines = [
        r"\begin{table}[t]",
        r"\centering",
        r"\small",
        r"\caption{Frozen V1 formative evidence. The trajectories are repeated executions, not 48 independent scientific units.}",
        r"\label{tab:v1}",
        r"\begin{tabularx}{\linewidth}{@{}XrX@{}}",
        r"\toprule",
        r"Observation & Frozen count & Interpretation \\",
        r"\midrule",
    ]
    for row in rows:
        lines.append(
            f"{_tex(row['LABEL'])} & {_tex(row['DISPLAY'])} & {_tex(row['INTERPRETATION'])} \\\\"
        )
    lines.extend((r"\bottomrule", r"\end{tabularx}", r"\end{table}"))
    _write_tex(TABLE_ROOT / "v1-evidence.tex", lines)

    lines = [
        r"\begin{table}[t]",
        r"\centering",
        r"\small",
        r"\caption{Critical V1 task-oracle control. PASS means the V1 continuity oracle accepted the state; it does not establish requested-task completion.}",
        r"\label{tab:v1-controls}",
        r"\begin{tabular}{@{}lr@{}}",
        r"\toprule",
        r"Repository state & V1 functionality across families \\",
        r"\midrule",
    ]
    for row in control_rows:
        lines.append(
            f"{_tex(row['LABEL'])} & {_tex(row['FAMILIES_PASS'])} PASS " + r"\\"
        )
    lines.extend((r"\bottomrule", r"\end{tabular}", r"\end{table}"))
    _write_tex(TABLE_ROOT / "v1-oracle-controls.tex", lines)


def _attrition_category(reason: str) -> tuple[str, str]:
    if reason == "TASK_STATEMENT_CUE_REJECT":
        return "SEMANTIC_REJECTION", "SCIENTIFIC_REJECT"
    if reason in {"SOURCE_SAFETY_REJECT", "NO_SOURCE_PASSES_HARD_GATES"}:
        return "SOURCE_SIDE_REJECTION", "SCIENTIFIC_REJECT"
    if reason == "B_U_R_TASK_SECURITY_MATRIX_REJECT":
        return "TARGET_INVALIDITY", "SCIENTIFIC_REJECT"
    if reason == "TARGET_TECHNICAL_INVALID":
        return "TECHNICAL_UNEVALUABILITY", "TECHNICAL_UNDETERMINED"
    raise ValueError(f"unclassified V4 reason: {reason}")


def _short_target(target_id: str) -> str:
    return target_id.rsplit("_", 1)[0].replace("__", "/")


def build_attrition_tables() -> None:
    original_path = REPO_ROOT / "artifacts/context-dependent-memory-confirmatory-v4-authoritative-2/original-five-validation.yaml"
    extension_path = REPO_ROOT / "artifacts/context-dependent-memory-confirmatory-v4-extension/final-development-outcome.yaml"
    original = _yaml_load(original_path)
    extension = _yaml_load(extension_path)
    rows = []
    for position, item in enumerate(original["results"], start=1):
        reason = item["response"]["terminal_reason"]
        category, status = _attrition_category(reason)
        rows.append(
            {
                "COHORT": "ORIGINAL_FIVE",
                "LOGICAL_POSITION": position,
                "TARGET_ID": item["target_id"],
                "TARGET": _short_target(item["target_id"]),
                "DECISION": item["response"]["decision"],
                "TERMINAL_REASON": reason,
                "GATE_CATEGORY": category,
                "SCIENTIFIC_STATUS": status,
                "INTERPRETATION": "No semantic inference" if status == "TECHNICAL_UNDETERMINED" else "Candidate ceased at this evidence gate",
                "SUPPORTING_ARTIFACT": str(original_path.relative_to(REPO_ROOT)),
            }
        )
    for item in extension["additional_development_extension"]["targets"]:
        reason = item["terminal_reason"]
        category, status = _attrition_category(reason)
        interpretation = "Candidate ceased at this evidence gate"
        if item["target_id"].startswith("tensorflow__"):
            interpretation = "Runtime/disk-quota failure during image materialization; no semantic inference"
        rows.append(
            {
                "COHORT": "PROSPECTIVELY_LOCKED_EXTENSION",
                "LOGICAL_POSITION": item["logical_position"],
                "TARGET_ID": item["target_id"],
                "TARGET": _short_target(item["target_id"]),
                "DECISION": item["decision"],
                "TERMINAL_REASON": reason,
                "GATE_CATEGORY": category,
                "SCIENTIFIC_STATUS": status,
                "INTERPRETATION": interpretation,
                "SUPPORTING_ARTIFACT": str(extension_path.relative_to(REPO_ROOT)),
            }
        )
    assert len(rows) == 10
    assert sum(row["DECISION"] == "ACCEPT" for row in rows) == 0
    _write_csv(DATA_ROOT / "real-repository-attrition.csv", tuple(rows[0]), rows)

    summary_rows = []
    for cohort in ("ORIGINAL_FIVE", "PROSPECTIVELY_LOCKED_EXTENSION"):
        for category in (
            "SEMANTIC_REJECTION",
            "SOURCE_SIDE_REJECTION",
            "TARGET_INVALIDITY",
            "TECHNICAL_UNEVALUABILITY",
        ):
            count = sum(
                row["COHORT"] == cohort and row["GATE_CATEGORY"] == category
                for row in rows
            )
            summary_rows.append({"COHORT": cohort, "GATE_CATEGORY": category, "COUNT": count})
    _write_csv(
        DATA_ROOT / "real-repository-attrition-summary.csv",
        ("COHORT", "GATE_CATEGORY", "COUNT"),
        summary_rows,
    )

    lines = [
        r"\begin{table*}[t]",
        r"\centering",
        r"\scriptsize",
        r"\caption{Gate-specific attrition in the bounded V4 development study. Counts characterize only the fixed development targets, not a population.}",
        r"\label{tab:v4-attrition}",
        r"\begin{tabularx}{\textwidth}{@{}llXXX@{}}",
        r"\toprule",
        r"Cohort & Target & Gate category & Terminal reason & Interpretation \\",
        r"\midrule",
    ]
    for row in rows:
        cohort = "Original" if row["COHORT"] == "ORIGINAL_FIVE" else "Locked extension"
        lines.append(
            " & ".join(
                _tex(value)
                for value in (
                    cohort,
                    row["TARGET"],
                    row["GATE_CATEGORY"],
                    row["TERMINAL_REASON"],
                    row["INTERPRETATION"],
                )
            )
            + r" \\"
        )
    lines.extend(
        (
            r"\bottomrule",
            r"\end{tabularx}",
            r"\vspace{2pt}",
            r"\parbox{.96\textwidth}{\footnotesize The original set yielded 0/5 complete acceptances; the prospectively locked extension yielded 0/5. TensorFlow remains \texttt{TECHNICAL\_UNDETERMINED}/\texttt{TARGET\_TECHNICAL\_INVALID}: a runtime quota failure is not semantic evidence. The resulting 0/10 is not a prevalence estimate.}",
            r"\end{table*}",
        )
    )
    _write_tex(TABLE_ROOT / "real-repository-attrition.tex", lines)


def build_control_tables() -> None:
    _install_yaml_compatibility()
    if str(REPO_ROOT / "src") not in sys.path:
        sys.path.insert(0, str(REPO_ROOT / "src"))
    from cmpilot.identification_control_v4 import validate_all_controls

    results = validate_all_controls()
    overview = [
        {
            "CONTROL": "KNOWN_VALID_CONTROL",
            "DECISION": results["positive"]["terminal_reason"],
            "EXPECTED_INTERPRETATION": "Complete acceptance demonstrates operational non-vacuity on a constructed known-valid case.",
        },
        {
            "CONTROL": "TARGET_ALREADY_SOLVED",
            "DECISION": results["target_already_solved"]["terminal_reason"],
            "EXPECTED_INTERPRETATION": "The already-present feature is rejected at target task incompleteness.",
        },
        {
            "CONTROL": "SOURCE_NOT_FOCALLY_SAFE",
            "DECISION": results["source_not_focally_safe"]["terminal_reason"],
            "EXPECTED_INTERPRETATION": "A correct but focal-unsafe donor is rejected at source safety.",
        },
    ]
    expected = {
        "KNOWN_VALID_CONTROL": "COMPLETE_ACCEPT",
        "TARGET_ALREADY_SOLVED": "TARGET_TASK_INCOMPLETENESS_REJECT",
        "SOURCE_NOT_FOCALLY_SAFE": "SOURCE_SAFETY_REJECT",
    }
    assert {row["CONTROL"]: row["DECISION"] for row in overview} == expected
    _write_csv(DATA_ROOT / "control-overview.csv", tuple(overview[0]), overview)

    positive = results["positive"]
    task = positive["target"]["task_matrix"]
    security = positive["target"]["focal_security_matrix"]
    checks = [
        ("B_FEATURE", task["B_UNTOUCHED"], "Expected: feature-reversion/baseline fails the feature test, showing the feature is genuinely necessary."),
        ("U_FEATURE", task["U"], "Unsafe implementation completes the requested feature."),
        ("R_FEATURE", task["R"], "Secure repair completes the same feature."),
        ("U_SECURITY", security["U"], "Unsafe implementation fails the focal witness."),
        ("R_SECURITY", security["R"], "Secure repair passes the focal witness."),
        ("FEATURE_RETENTION", positive["target"]["feature_retention"], "Repair retains the requested feature."),
        ("U_TO_R_INTEGRITY", positive["target"]["u_to_r_integrity"], "Exact U-to-R reconstruction is verified."),
        ("SOURCE_CORRECTNESS", positive["source_correctness"], "The donor procedure works in its source context."),
        ("SOURCE_FOCAL_SAFETY", positive["source_focal_safety"], "The donor passes the focal source-safety evidence."),
        ("PSTAR_SHIFT", "PASS" if positive["pstar"]["source_truth_evidence"]["status"] == "TRUE" and positive["pstar"]["target_status_evidence"]["status"] == "FALSE" else "FAIL", "The named predicate is true at source and false at target."),
        ("RELEVANT_MEMORY_AVAILABLE", "PASS" if positive["memories"]["relevant"]["source_id"] else "FAIL", "Relevant source memory is present and fidelity checked."),
        ("IRRELEVANT_MEMORY_AVAILABLE", "PASS" if positive["memories"]["irrelevant"]["source_id"] else "FAIL", "Irrelevant correct memory is present and fidelity checked."),
        ("EQUAL_POST_INGESTION_BUDGET", "PASS" if positive["memories"]["post_ingestion_budget_equal"] else "FAIL", "Post-ingestion capacity is equal across memory conditions."),
    ]
    detail_rows = [
        {
            "CONTROL": "KNOWN_VALID_CONTROL",
            "CHECK": check,
            "OBSERVED": observed,
            "INTERPRETATION": interpretation,
            "SUPPORTING_ARTIFACT": "model-free execution of the unchanged V4 control path",
        }
        for check, observed, interpretation in checks
    ]
    _write_csv(DATA_ROOT / "control-evidence.csv", tuple(detail_rows[0]), detail_rows)

    lines = [
        r"\begin{table}[t]",
        r"\centering",
        r"\small",
        r"\caption{Positive and targeted negative controls for the unchanged identification path.}",
        r"\label{tab:controls}",
        r"\begin{tabularx}{\linewidth}{@{}lXX@{}}",
        r"\toprule",
        r"Control & Scientific decision & Interpretation \\",
        r"\midrule",
    ]
    for row in overview:
        lines.append(
            f"{_tex(row['CONTROL'])} & {_tex(row['DECISION'])} & {_tex(row['EXPECTED_INTERPRETATION'])} \\\\"
        )
    lines.extend((r"\bottomrule", r"\end{tabularx}", r"\end{table}"))

    lines.extend(
        (
            r"\begin{table}[t]",
            r"\centering",
            r"\small",
            r"\caption{Known-valid control evidence. Here the B feature-test \texttt{FAIL} is expected: reverting to baseline removes a genuinely necessary feature; it does not mean the scientific control failed.}",
            r"\label{tab:positive-detail}",
            r"\begin{tabularx}{\linewidth}{@{}l r X@{}}",
            r"\toprule",
            r"Check & Observation & Meaning \\",
            r"\midrule",
        )
    )
    for row in detail_rows:
        lines.append(
            f"{_tex(row['CHECK'])} & {_tex(row['OBSERVED'])} & {_tex(row['INTERPRETATION'])} \\\\"
        )
    lines.extend((r"\bottomrule", r"\end{tabularx}", r"\end{table}"))
    _write_tex(TABLE_ROOT / "control-validation.tex", lines)


def _paper_records() -> dict[str, Mapping[str, Any]]:
    records = {}
    for path in sorted((REPO_ROOT / "audits/external-identification-v1/papers").glob("*.yaml")):
        record = _yaml_load(path)
        records[record["PAPER_ID"]] = record
    assert tuple(records) == PAPER_IDS
    return records


def build_external_tables() -> None:
    table_data = _yaml_load(REPO_ROOT / "audits/external-identification-v1/table-data.yaml")
    matrix_rows = []
    for row in table_data["REQUIREMENTS_BY_PAPER"]["ROWS"]:
        assert set(row["CELLS"].values()) <= STATUS_VOCABULARY
        matrix_rows.append(
            {
                "CRITERION": row["CRITERION"],
                "DEFINITION": row["DEFINITION"],
                **{paper_id: row["CELLS"][paper_id] for paper_id in PAPER_IDS},
            }
        )
    assert len(matrix_rows) == 18
    _write_csv(DATA_ROOT / "external-audit-matrix.csv", tuple(matrix_rows[0]), matrix_rows)

    gap_rows = []
    for row in table_data["CLAIM_DESIGN_GAP_BY_PAPER"]["ROWS"]:
        gap_rows.append(
            {
                "PAPER": row["PAPER_ID"],
                "STATED_CLAIM": row["STATED_CLAIM"],
                "WHAT_ITS_DESIGN_ESTABLISHES": row["DESIGN_ESTABLISHES"],
                "WHAT_ADDITIONAL_EVIDENCE_OUR_STRONGER_ESTIMAND_WOULD_REQUIRE": " ".join(
                    row["ADDITIONAL_EVIDENCE_FOR_STRONGER_SECURITY_TRANSFER_CLAIM"]
                ),
            }
        )
    assert len(gap_rows) == 6
    _write_csv(DATA_ROOT / "external-audit-design-gaps.csv", tuple(gap_rows[0]), gap_rows)

    lines = [
        r"\begin{table*}[t]",
        r"\centering",
        r"\scriptsize",
        r"\caption{Frozen external framework application. Statuses are claim-relative: \texttt{NOT\_ESTABLISHED} is absent sufficient evidence for an applicable criterion, not evidence that a paper is wrong.}",
        r"\label{tab:external-matrix}",
        r"\resizebox{\textwidth}{!}{%",
        r"\begin{tabular}{@{}lrrrrrr@{}}",
        r"\toprule",
        "Criterion & " + " & ".join(_tex(PAPER_ABBREVIATIONS[p]) for p in PAPER_IDS) + r" \\",
        r"\midrule",
    ]
    for row in matrix_rows:
        lines.append(
            _tex(row["CRITERION"])
            + " & "
            + " & ".join(_tex(row[paper]) for paper in PAPER_IDS)
            + r" \\"
        )
    lines.extend(
        (
            r"\bottomrule",
            r"\end{tabular}%",
            r"}",
            r"\end{table*}",
        )
    )
    _write_tex(TABLE_ROOT / "external-audit-matrix.tex", lines)

    lines = [
        r"\begingroup",
        r"\scriptsize",
        r"\begin{longtable}{@{}p{.14\linewidth}p{.26\linewidth}p{.27\linewidth}p{.27\linewidth}@{}}",
        r"\caption{Claim-relative interpretation of the six deliberately selected works. Additional evidence is what this project's stronger estimand would require, not a correction to the paper's own estimand.}\label{tab:external-gaps}\\",
        r"\toprule",
        r"Paper & Stated claim & What its design establishes & Additional evidence for our stronger estimand \\",
        r"\midrule",
        r"\endfirsthead",
        r"\toprule",
        r"Paper & Stated claim & What its design establishes & Additional evidence for our stronger estimand \\",
        r"\midrule",
        r"\endhead",
    ]
    for row in gap_rows:
        lines.append(
            " & ".join(
                _tex(value)
                for value in (
                    PAPER_ABBREVIATIONS[row["PAPER"]],
                    row["STATED_CLAIM"],
                    row["WHAT_ITS_DESIGN_ESTABLISHES"],
                    row["WHAT_ADDITIONAL_EVIDENCE_OUR_STRONGER_ESTIMAND_WOULD_REQUIRE"],
                )
            )
            + r" \\"
        )
    lines.extend((r"\bottomrule", r"\end{longtable}", r"\endgroup"))
    _write_tex(TABLE_ROOT / "external-audit-design-gaps.tex", lines)


def _official_source_url(record: Mapping[str, Any]) -> str:
    for source in record["SOURCE_URLS"]:
        if source["ACCESS_STATUS"] == "ACCESSIBLE" and not source["TYPE"].endswith("PDF"):
            return source["URL"]
    for source in record["SOURCE_URLS"]:
        if source["ACCESS_STATUS"] == "ACCESSIBLE":
            return source["URL"]
    raise ValueError(f"no accessible official URL for {record['PAPER_ID']}")


def _sample_digest(paper_id: str, criterion: str) -> str:
    payload = f"{AGREEMENT_SAMPLE_DOMAIN}\0{paper_id}\0{criterion}".encode()
    return sha256(payload).hexdigest()


def _refuse_to_overwrite_human_review() -> None:
    """Fail before regenerating packets once any human review data exist."""

    for path in sorted(HUMAN_ROOT.glob("[0-9][0-9]-*.yaml")):
        packet = _yaml_load(path)
        if packet.get("HUMAN_VERIFICATION_COMPLETED") is True:
            raise RuntimeError(f"refusing to overwrite completed human packet: {path}")
        for cell in packet.get("CRITERIA", []):
            if cell.get("HUMAN_RESPONSES"):
                raise RuntimeError(f"refusing to overwrite human responses: {path}")
            if cell.get("AGREE_WITH_ADJUDICATED_RATING") or cell.get("HUMAN_COMMENT"):
                raise RuntimeError(f"refusing to overwrite legacy human answers: {path}")

    reconciliation_path = HUMAN_ROOT / "reconciliation.yaml"
    if reconciliation_path.is_file():
        reconciliation = _yaml_load(reconciliation_path)
        protected_values = (
            reconciliation.get("HUMAN_VERIFICATION_COMPLETED"),
            reconciliation.get("HUMAN_REVIEWER_RECORDS"),
            reconciliation.get("HUMAN_VERIFIED_RESULT"),
            reconciliation.get("HUMAN_VERIFIED_RESULT_RATIONALE"),
        )
        if any(value not in (None, False, "", []) for value in protected_values):
            raise RuntimeError(
                f"refusing to overwrite human reconciliation data: {reconciliation_path}"
            )


def build_human_review_packets() -> None:
    _refuse_to_overwrite_human_review()
    protocol = _yaml_load(REPO_ROOT / "protocols/external-identification-audit-v1.yaml")
    requirements = {
        criterion: definition
        for _, criterion, definition in _flatten_requirements(protocol)
    }
    papers = _paper_records()

    sampled_agreements = []
    for paper_id in PAPER_IDS:
        record = papers[paper_id]
        candidates = []
        for criterion in requirements:
            a = record["REVIEWER_A_RATINGS"][criterion]["STATUS"]
            b = record["REVIEWER_B_RATINGS"][criterion]["STATUS"]
            if a == b:
                candidates.append((_sample_digest(paper_id, criterion), paper_id, criterion))
        sampled_agreements.append(min(candidates))
    sampled_keys = {(paper, criterion) for _, paper, criterion in sampled_agreements}

    sampling_rule = {
        "SAMPLING_RULE_ID": "HUMAN_REVIEW_AGREEMENT_SAMPLE_V1",
        "STATUS": "FROZEN_BY_DETERMINISTIC_GENERATOR",
        "DOMAIN_SEPARATOR": AGREEMENT_SAMPLE_DOMAIN,
        "ELIGIBLE_CELLS": "Reviewer A and Reviewer B assigned the same status",
        "STRATIFICATION": "Within each of the six papers",
        "HASH_INPUT": "DOMAIN_SEPARATOR || 0x00 || PAPER_ID || 0x00 || CRITERION_ID",
        "HASH_ALGORITHM": "SHA256",
        "SELECTION": "Lowest digest within each paper; impossible ties broken by CRITERION_ID",
        "SAMPLED_AGREEMENT_CELLS": 6,
        "SELECTED": [
            {"PAPER_ID": paper, "CRITERION": criterion, "SHA256": digest}
            for digest, paper, criterion in sampled_agreements
        ],
        "DISAGREEMENT_RULE": "All 17 disagreement cells are priority regardless of the agreement sample",
    }
    _yaml_dump(HUMAN_ROOT / "sampling-rule.yaml", sampling_rule)

    priority_cells = []
    disagreement_count = 0
    for source_path in sorted(
        (REPO_ROOT / "audits/external-identification-v1/papers").glob("*.yaml")
    ):
        record = _yaml_load(source_path)
        paper_id = record["PAPER_ID"]
        criteria = []
        for criterion, definition in requirements.items():
            a = record["REVIEWER_A_RATINGS"][criterion]["STATUS"]
            b = record["REVIEWER_B_RATINGS"][criterion]["STATUS"]
            final = record["ADJUDICATED_RATINGS"][criterion]
            disagreed = a != b
            disagreement_count += int(disagreed)
            sampled = (paper_id, criterion) in sampled_keys
            item = {
                "CRITERION_ID": criterion,
                "FROZEN_CRITERION_TEXT": definition,
                "REVIEWER_A_RATING": a,
                "REVIEWER_B_RATING": b,
                "ADJUDICATED_RATING": final["STATUS"],
                "REVIEWERS_DISAGREED": disagreed,
                "PRIORITY_HUMAN_VERIFICATION": disagreed or sampled,
                "PRIORITY_REASON": (
                    "REVIEWER_DISAGREEMENT"
                    if disagreed
                    else "DETERMINISTIC_AGREEMENT_SAMPLE"
                    if sampled
                    else "NOT_PRIORITY_SAMPLE"
                ),
                "EXACT_ORIGINAL_SOURCE_LOCATION": final["EVIDENCE_LOCATION"],
                "CONCISE_EVIDENCE_SUMMARY": final["EVIDENCE_SUMMARY"],
                "OFFICIAL_SOURCE_URL": _official_source_url(record),
                "HUMAN_RESPONSES": [],
            }
            criteria.append(item)
            if item["PRIORITY_HUMAN_VERIFICATION"]:
                priority_cells.append(
                    {
                        "PAPER_ID": paper_id,
                        **item,
                    }
                )
        packet = {
            "PACKET_ID": f"HUMAN_REVIEW_{paper_id}",
            "HUMAN_VERIFICATION_COMPLETED": False,
            "HUMAN_VERIFICATION_PROTOCOL": HUMAN_VERIFICATION_PROTOCOL,
            "PAPER_ID": paper_id,
            "TITLE": record["TITLE"],
            "VERSION": record["VERSION"],
            "VENUE_OR_STATUS": record["VENUE_OR_STATUS"],
            "OFFICIAL_SOURCE_URL": _official_source_url(record),
            "FROZEN_PAPER_RECORD": str(source_path.relative_to(REPO_ROOT)),
            "FROZEN_PAPER_RECORD_SHA256": _sha(source_path),
            "HUMAN_RESPONSE_OPTIONS": list(HUMAN_RESPONSE_OPTIONS),
            "HUMAN_RESPONSE_RECORD_FIELDS": list(HUMAN_RESPONSE_RECORD_FIELDS),
            "INSTRUCTIONS": (
                "Review only criteria with PRIORITY_HUMAN_VERIFICATION true. "
                "Check the cited original-source location against the frozen "
                "criterion, then append one response record conforming to the "
                "frozen human-verification protocol. Leave every nonpriority "
                "HUMAN_RESPONSES list empty. NOT_ESTABLISHED means sufficient "
                "evidence was not established for an applicable claim; it does "
                "not mean the paper is wrong."
            ),
            "CRITERIA": criteria,
        }
        _yaml_dump(HUMAN_ROOT / source_path.name, packet)

    assert disagreement_count == 17
    assert len(priority_cells) == 23
    reconciliation = {
        "PACKET_ID": "HUMAN_REVIEW_RECONCILIATION_V1",
        "HUMAN_VERIFICATION_COMPLETED": False,
        "RAW_REVIEW_AGREEMENT": "91/108 (84.26%)",
        "PRIORITY_DISAGREEMENTS": 17,
        "DETERMINISTIC_AGREEMENT_SAMPLE": 6,
        "TOTAL_PRIORITY_CELLS": 23,
        "SAMPLING_RULE": "paper/human-review/sampling-rule.yaml",
        "HUMAN_VERIFICATION_PROTOCOL": HUMAN_VERIFICATION_PROTOCOL,
        "INSTRUCTIONS": (
            "Human responses are recorded only in each paper packet's "
            "HUMAN_RESPONSES lists. This file indexes the immutable priority "
            "cells and stores reviewer metadata and any required qualitative "
            "result reassessment. Never change the frozen AI fields."
        ),
        "PRIORITY_CELLS": priority_cells,
        "HUMAN_REVIEWER_RECORDS": [],
        "HUMAN_VERIFIED_RESULT": "",
        "HUMAN_VERIFIED_RESULT_RATIONALE": "",
        "FINAL_RECONCILIATION_METADATA": {
            "HUMAN_REVIEWER_IDS": "",
            "RECONCILIATION_DATE": "",
            "ALL_PRIORITY_CELLS_REVIEWED": "",
            "AGREEMENT_WITH_FROZEN_ADJUDICATION_COUNT": "",
            "DISAGREEMENT_WITH_FROZEN_ADJUDICATION_COUNT": "",
            "UNRESOLVED_COUNT": "",
            "ADJUDICATION_METHOD": "",
            "FINAL_COMMENT": "",
        },
    }
    _yaml_dump(HUMAN_ROOT / "reconciliation.yaml", reconciliation)

    reviewer_template = {
        "TEMPLATE_ID": "EXTERNAL_AUDIT_HUMAN_REVIEWER_METADATA_V1",
        "HUMAN_VERIFICATION_COMPLETED": False,
        "REVIEWER_ID_OR_PSEUDONYM": "",
        "ROLE": "",
        "RELATIONSHIP_TO_PROJECT": "",
        "REVIEW_DATE": "",
        "CONFLICTS_OR_PRIOR_INVOLVEMENT": "",
        "PAPERS_REVIEWED": [],
        "CELLS_REVIEWED": [],
        "CONFIRMATION_THAT_REVIEWER_IS_HUMAN": "",
        "SUBSTANTIALLY_PARTICIPATED_IN_ORIGINAL_EXTERNAL_AUDIT_RATINGS": "",
        "REVIEWED_WITHOUT_ANOTHER_HUMAN_REVIEWERS_ANSWERS": "",
    }
    _yaml_dump(HUMAN_ROOT / "reviewer-template.yaml", reviewer_template)


def build_evidence_manifest() -> None:
    source_paths = (
        "paper/claim-ledger.yaml",
        "artifacts/v2-preflight/v1-immutability.json",
        "artifacts/v2-preflight/control-matrix.json",
        "artifacts/v2-methodology-repair/readiness.json",
        "protocols/context-dependent-memory-v4-final-development.yaml",
        "protocols/context-dependent-memory-v4-additional-development-exclusions.yaml",
        "artifacts/context-dependent-memory-confirmatory-v4-authoritative-2/original-five-validation.yaml",
        "artifacts/context-dependent-memory-confirmatory-v4-extension/final-development-outcome.yaml",
        "protocols/v4-identification-nonvacuity-control.yaml",
        "protocols/external-identification-audit-v1.yaml",
        "audits/external-identification-v1/table-data.yaml",
        "audits/external-identification-v1/reconciliation.yaml",
        "audits/external-identification-v1/cross-paper-analysis.yaml",
        "audits/external-identification-v1/generic-validity-comparison.yaml",
    )
    rows = [
        {"PATH": path, "SHA256": _sha(REPO_ROOT / path), "ROLE": "frozen source or frozen claim boundary"}
        for path in source_paths
    ]
    _write_csv(DATA_ROOT / "evidence-source-manifest.csv", tuple(rows[0]), rows)


def main() -> int:
    for directory in (DATA_ROOT, HUMAN_ROOT, TABLE_ROOT):
        directory.mkdir(parents=True, exist_ok=True)
    build_identification_contract()
    build_v1_tables()
    build_attrition_tables()
    build_control_tables()
    build_external_tables()
    build_human_review_packets()
    build_evidence_manifest()
    print("BUILT: publication evidence derivatives")
    print("EVALUATED_MODEL_RUNS: 0")
    print("GPU_USE: 0")
    print("UNSEEN_CONFIRMATORY_TARGETS_SCREENED: 0")
    print("NEW_REAL_TARGETS_SCREENED: 0")
    print("NEW_EXTERNAL_AUDIT_PAPERS: 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
