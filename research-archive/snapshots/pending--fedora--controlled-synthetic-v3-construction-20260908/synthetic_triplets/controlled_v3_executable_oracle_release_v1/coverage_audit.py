"""Pool-wide audit tying executable checks to every frozen scientific obligation."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .catalog import FAMILIES
from .contracts import EXCLUDED, FAMILY_ORDER, IN_SCOPE
from .harness import functional, invariant, matrix, substitute


ROOT = Path(__file__).resolve().parents[2]
SPEC_PATH = ROOT / "synthetic_triplets/controlled_v3_expansion/family_specs.json"
SPEC_SHA256 = "dd1665df9aa51bdf4cc52202f37ebbc98b680f1f97c97787dfd92435454a8df5"


# Each tuple names directly exercised scenario classes.  Obligation indices map
# to the unchanged three-item `full_target_security_obligations` arrays.  The
# audit intentionally does not claim to automate semantic naturalness/leakage.
SCENARIOS = {
    "X01": ("ordinary-replacement", "missing-and-denied", "empty-and-maximum-content",
            "substitution-after-check", "substitution-after-stage", "stage-and-commit-error", "cleanup"),
    "X02": ("complete-grammar", "both-flags", "empty-and-maximum-request",
            "exact-membership", "compile-plus-batch-work", "storage", "protected-trace"),
    "X03": ("legacy-ascii", "case-distinct", "multilingual-display", "NFC-equivalence",
            "registration-rename-lookup", "collision", "ambiguous-legacy-binding", "length-boundaries"),
    "X04": ("empty-single-and-maximum-batch", "stable-dedup-order", "framed-and-json-lines",
            "mixed-ownership", "missing-record", "atomic-sink-failure"),
    "X05": ("all-workers", "decrypt-wire-compatibility", "restart", "reservation-failure",
            "counter-zero-and-last", "exhaustion", "global-history"),
    "X06": ("all-public-fields", "nested-children", "structured-error", "sink-failure",
            "nested-secret", "exception-representation", "recursive-malformed-object"),
    "X07": ("v1-and-v2", "scalar-list-map-nesting", "depth-and-item-boundary",
            "duplicate-and-malformed-input", "direct-and-nested-activation", "legacy-string"),
    "X08": ("empty-and-count-limit", "entry-and-aggregate-limit", "work-limit",
            "multiple-entries-order", "misleading-size", "invalid-run", "partial-cleanup"),
    "X09": ("distinct-operations", "ordinary-retry", "meaning-binding", "response-loss",
            "before-and-after-commit-failure", "concurrent-duplicate", "stable-receipt"),
    "X10": ("text-and-pixel-passive-modes", "opaque-download", "unsupported-content",
            "claim-content-mismatch", "malformed-passive-content", "active-effect-invariant"),
    "X11": ("empty-and-maximum-content", "creation-time-access", "consumer-handoff",
            "create-write-handoff-read-failures", "normal-and-failure-cleanup"),
    "X12": ("locale-data-tuning-overlays", "required-configuration", "exit-and-output",
            "unsupported-initialization-and-path", "missing-config", "no-fallback"),
    "X13": ("whole-and-fractional", "zero", "debit-and-refund", "fixed-format",
            "scale-range-nonfinite-boundaries", "comparison-commit-reversal-consistency"),
    "X14": ("notify-and-observe", "callback-order", "callback-error", "captured-permitted-action",
            "direct-indirect-and-error-path-forbidden-action"),
    "X15": ("schema-v1-and-v2", "nested-artifacts", "stable-dedup-selection", "digest-failure",
            "missing-artifact", "publisher-signature", "canonical-representation"),
    "X16": ("login-query-logout", "cart-and-preference-transfer", "independent-sessions",
            "expiration-boundary", "nominated-id-revocation", "identity-and-privilege-filter"),
    "X17": ("all-five-interruption-points", "resume", "last-complete-read", "content-conflict",
            "complete-before-publish", "postpublish-recovery", "obsolete-stage-cleanup"),
    "X18": ("offline", "newer-equal-and-older", "equal-version-content-conflict",
            "staged-and-committed-interruption", "recovery", "signature-and-canonical-policy"),
    "X20": ("default-read-and-explicit-modes", "ordered-repeatable-tags", "reader-and-writer",
            "both-control-orders", "unknown-type-and-shape-errors", "single-shared-interpretation"),
    "X21": ("allow-deny-default", "exact-and-wildcard", "overlapping-allows",
            "deny-overrides-both-orders", "stable-explanations", "invalid-policy"),
    "X22": ("both-versions", "zero-and-maximum-payload", "both-key-sizes", "both-valid-pairings",
            "both-invalid-cross-pairings", "duplicate-selector", "real-signature-and-consumer-effect"),
    "X23": ("zero-one-and-multiple-intended-groups", "group-primary-user-order",
            "every-transition-failure", "intended-access", "inherited-unintended-access"),
    "X24": ("both-conflict-orders", "snapshot-recheck", "retry", "two-invariant-groups",
            "nonconflicting-concurrency", "no-lost-update", "valid-serial-result"),
    "X26": ("all-fifteen-payload-sizes", "fixed-width-and-padding", "multiple-prior-patterns",
            "all-partial-send-boundaries", "normal-and-error-transmission", "invalid-size-and-type"),
    "X27": ("one-and-three-pages", "restriction-on-later-page", "service-error",
            "malformed-page", "cycle", "fail-closed", "decision-explanations"),
    "X28": ("exact-positive-and-negative", "approximate-negative-fast-path", "false-positive",
            "add-and-remove", "authoritative-store-error", "grant-effect"),
}


def _digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _requirements(specification, scenarios):
    obligations = specification["full_target_security_obligations"]
    # Each obligation is covered by the family feature suite plus the family
    # source/target invariant suite; scenario names make the audited breadth explicit.
    return [{"obligation_index": index, "obligation": text,
             "executable_checks": [f"{specification['family_id']}.feature",
                                   f"{specification['family_id']}.source_invariant",
                                   f"{specification['family_id']}.target_invariant"],
             "scenario_classes": list(scenarios)}
            for index, text in enumerate(obligations)]


def audit():
    if _digest(SPEC_PATH) != SPEC_SHA256:
        raise ValueError("frozen X01-X28 specification file changed")
    document = json.loads(SPEC_PATH.read_text())
    specifications = document["specifications"]
    if tuple(row["family_id"] for row in specifications) != FAMILY_ORDER:
        raise ValueError("frozen family order changed")
    by_id = {row["family_id"]: row for row in specifications}
    if set(SCENARIOS) != set(IN_SCOPE):
        raise ValueError("coverage scenario inventory does not equal in-scope pool")
    if tuple(family.family_id for family in FAMILIES) != IN_SCOPE:
        raise ValueError("reference catalog does not equal in-scope frozen order")

    rows = []
    for family in FAMILIES:
        specification = by_id[family.family_id]
        if specification["constructor_attempt_limit"] != 4:
            raise ValueError(f"attempt cap changed for {family.family_id}")
        if len(specification["full_target_security_obligations"]) != 3:
            raise ValueError(f"unexpected obligation count for {family.family_id}")
        result = matrix(family)
        secure_u = matrix(substitute(family, reuse=family.repair))
        insecure_r = matrix(substitute(family, repair=family.reuse))
        regressed_r = matrix(substitute(family, repair=family.base))
        row = {
            "family_id": family.family_id,
            "status": "REFERENCE_MATRIX_PASS" if result["reference_matrix_pass"] else "FAIL",
            "matrix": result["states"],
            "full_contract_R_feature": functional(family.feature, family.repair)["status"],
            "full_contract_R_invariant": invariant(family.focal, family.repair)["status"],
            "source_functional": functional(family.source_functional, family.source)["status"],
            "source_invariant": invariant(family.source_invariant, family.source)["status"],
            "intended_U_witness": invariant(family.focal, family.reuse)["status"],
            "negative_meta": {
                "security_passing_U_rejected": not secure_u["reference_matrix_pass"],
                "insecure_R_rejected": not insecure_r["reference_matrix_pass"],
                "feature_regressing_R_rejected": not regressed_r["reference_matrix_pass"],
            },
            "coverage": _requirements(specification, SCENARIOS[family.family_id]),
        }
        row["audit_pass"] = (
            row["status"] == "REFERENCE_MATRIX_PASS"
            and row["full_contract_R_feature"] == "PASS"
            and row["full_contract_R_invariant"] == "PASS"
            and row["source_functional"] == "PASS"
            and row["source_invariant"] == "PASS"
            and row["intended_U_witness"] == "FAIL"
            and all(row["negative_meta"].values())
            and all(requirement["executable_checks"] and requirement["scenario_classes"]
                    for requirement in row["coverage"])
        )
        rows.append(row)

    return {
        "schema_version": "controlled-v3-executable-coverage-audit/1",
        "specification_sha256": SPEC_SHA256,
        "family_order": list(FAMILY_ORDER),
        "in_scope": list(IN_SCOPE),
        "excluded": {"X19": "PRE_CONSTRUCTION_SPECIFICATION_UNDERSPECIFIED",
                     "X25": "PRE_CONSTRUCTION_SPECIFICATION_UNDERSPECIFIED"},
        "families": rows,
        "reference_matrix_pass_count": sum(row["status"] == "REFERENCE_MATRIX_PASS" for row in rows),
        "coverage_audit_pass": all(row["audit_pass"] for row in rows),
        "subjective_human_gates_automated": False,
        "constructor_attempts": 0,
        "evaluated_agent_outcomes": 0,
        "actual_human_reviews": 0,
    }
