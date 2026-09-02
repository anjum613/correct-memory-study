"""Model-free primitives for development source pairing.

The pairing side is deliberately limited to public B material, public task
text, and a frozen source corpus.  This module has no model client, no network
client, and no API that accepts target-oracle material.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import ast
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import tokenize
from io import BytesIO
from typing import Any, Iterable, Mapping, Sequence

from cmpilot.susvibes_feasibility import DEVELOPMENT_IDS, SUSVIBES_REVISION


PAIRING_SCHEMA = "cmpilot-context-dependent-memory-source-pairing-v1"
HASH_VECTORIZER_REVISION = "cmpilot-hash-vectorizer-64-v1"

CUE_TAXONOMY = (
    "NO_SECURITY_CUE",
    "GENERIC_ROBUSTNESS_CUE",
    "EXPLICIT_SECURITY_REQUIREMENT",
    "FOCAL_PRECONDITION_CUE",
    "SAFE_IMPLEMENTATION_LEAKAGE",
)
CUE_INELIGIBLE = frozenset(CUE_TAXONOMY[2:])

PSTAR_ONTOLOGY = (
    "BOUNDS_LENGTH",
    "OWNERSHIP_LIFETIME",
    "VALIDATION_BEFORE_USE",
    "PATH_PROVENANCE",
    "AUTHENTICATION_AUTHORIZATION",
    "PERMISSION_CAPABILITY",
    "PROTOCOL_LAYOUT",
    "ENCODING_CANONICALIZATION",
    "CONCURRENCY_STATE",
    "RESOURCE_TRUST_BOUNDARY_ORDERING",
)

FOCAL_SAFETY_LEVELS = ("A", "B", "C", "D")
CONFIRMATORY_FOCAL_SAFETY_LEVELS = frozenset(("A", "B", "C"))

FORBIDDEN_B_ONLY_KEYS = frozenset(
    {
        "base_commit",
        "cve_fix_date",
        "cve_id",
        "cwe_ids",
        "expected_pf",
        "focal_evaluator_outcome",
        "golden_patch",
        "mask_patch",
        "pov",
        "r",
        "safe_patch",
        "security_patch",
        "security_test",
        "test_patch",
        "u",
        "vulnerability_type",
        "vulnerable_patch",
    }
)

PUBLIC_METADATA_FIELDS = frozenset(
    {
        "b_image_manifest_digest",
        "b_tree_sha256",
        "benchmark_revision",
        "image_name",
        "instance_id",
        "language",
        "project",
    }
)

TARGET_SOURCE_FILE_EXCLUSIONS = (
    "aiohttp_session/__init__.py",
    "master/buildbot/www/resource.py",
    "wagtail/admin/rich_text/converters/contentstate.py",
    "django/contrib/auth/hashers.py",
    "requests/sessions.py",
)

OPERATION_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "SESSION_STATE_LIFECYCLE",
        ("session", "cookie", "identity", "created", "max_age", "mapping"),
    ),
    (
        "HTTP_REDIRECT",
        ("redirect", "location", "http 302", "response url"),
    ),
    (
        "MARKUP_LINK_SERIALIZATION",
        ("link entity", "anchor", "href", "html", "contentstate", "linktype"),
    ),
    (
        "PASSWORD_VERIFICATION",
        ("password", "hasher", "digest", "constant time", "runtime hardening"),
    ),
    (
        "PROXY_CONFIGURATION",
        ("proxy", "no_proxy", "proxy-authorization", "environment proxy"),
    ),
    (
        "AUTHENTICATION_FLOW",
        ("authentication", "authorization", "credential", "oauth", "login"),
    ),
    (
        "PATH_OR_URL_VALIDATION",
        ("path", "url", "uri", "scheme", "host"),
    ),
    (
        "DATA_VALIDATION",
        ("validate", "invalid", "malformed", "parse", "decode"),
    ),
)

_SAFE_LEAKAGE_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "TIMING_HARDENING_DIRECTIVE",
        re.compile(r"(?:timing attack protection|runtime hardening)", re.I),
    ),
    (
        "PROXY_AUTH_MUTATION_DIRECTIVE",
        re.compile(
            r"(?=.*Proxy-Authorization)(?=.*(?:remov|strip))(?=.*(?:add|new authentication))",
            re.I | re.S,
        ),
    ),
    (
        "NO_PROXY_SAFE_REPAIR_DIRECTIVE",
        re.compile(r"NO_PROXY compliance|strip proxy configurations", re.I),
    ),
    (
        "SECURITY_ORACLE_DIRECTIVE",
        re.compile(r"(?:security|focal)[ -]?(?:test|oracle)", re.I),
    ),
    (
        "VULNERABILITY_IDENTIFIER",
        re.compile(r"\b(?:CVE|CWE|GHSA)-[0-9A-Za-z-]+\b", re.I),
    ),
)
_FOCAL_PRECONDITION_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "EXPLICIT_PRECONDITION",
        re.compile(
            r"\b(?:only (?:when|if)|strictly less than|same[- ]origin|within (?:the )?(?:root|bounds)|validated before use)\b",
            re.I,
        ),
    ),
    ("PSTAR_LITERAL", re.compile(r"(?:\bp\*\b|pstar)", re.I)),
)
_EXPLICIT_SECURITY_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "DIRECT_SECURITY_REQUIREMENT",
        re.compile(
            r"\b(?:prevent|mitigate|protect against|avoid)\b.{0,80}\b(?:attack|injection|credential leak|vulnerability)\b",
            re.I,
        ),
    ),
)
_GENERIC_ROBUSTNESS_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("EDGE_CASES", re.compile(r"\bedge cases?\b", re.I)),
    ("GENERIC_SECURE", re.compile(r"\bsecure(?:ly)?\b", re.I)),
    ("INVALID_INPUT", re.compile(r"\b(?:invalid|malformed)\b", re.I)),
)

_WORD = re.compile(r"[A-Za-z][A-Za-z0-9]*")
_BACKTICK = re.compile(r"`([^`\n]+)`")
_DOTTED_MODULE = re.compile(r"\b(?:[a-z_][a-z0-9_]*\.){2,}[a-z_][a-z0-9_]*\b")
_STOP_WORDS = frozenset(
    "a an and are as at be been by can class complete currently do does for from "
    "function has have in including into is it its method missing must needs of on "
    "or proper properly should that the their this to using when which with".split()
)


class SourcePairingError(ValueError):
    """A source-pairing invariant was violated."""


class PairingReadDenied(PermissionError):
    """A pairing-side filesystem read escaped its public workspace."""


def canonical_json(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        + "\n"
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def stable_record_hash(value: Any) -> str:
    return sha256_bytes(canonical_json(value))


def _camel_boundaries(value: str) -> str:
    return re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", value)


def normalized_tokens(value: str) -> tuple[str, ...]:
    text = _camel_boundaries(value).replace("_", "-")
    tokens = tuple(
        token
        for token in (match.group(0).casefold() for match in _WORD.finditer(text))
        if token not in _STOP_WORDS and len(token) > 1
    )
    return tokens


def token_shingles(value: str, *, size: int = 5) -> tuple[str, ...]:
    tokens = normalized_tokens(value)
    if not tokens:
        return ()
    if len(tokens) < size:
        return (" ".join(tokens),)
    return tuple(" ".join(tokens[index : index + size]) for index in range(len(tokens) - size + 1))


def hash_vector(value: str, *, dimensions: int = 64) -> tuple[float, ...]:
    """Return a deterministic, local, non-generative lexical feature vector."""

    vector = [0.0] * dimensions
    for token in normalized_tokens(value):
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], "big") % dimensions
        sign = 1.0 if digest[4] & 1 else -1.0
        vector[index] += sign
    magnitude = math.sqrt(sum(component * component for component in vector))
    if magnitude:
        vector = [round(component / magnitude, 12) for component in vector]
    return tuple(vector)


def cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right) or not left:
        return 0.0
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if not left_norm or not right_norm:
        return 0.0
    return sum(a * b for a, b in zip(left, right)) / (left_norm * right_norm)


def jaccard_similarity(left: Iterable[str], right: Iterable[str]) -> float:
    left_set, right_set = set(left), set(right)
    union = left_set | right_set
    return len(left_set & right_set) / len(union) if union else 0.0


def multiset_jaccard(left: Iterable[str], right: Iterable[str]) -> float:
    a, b = Counter(left), Counter(right)
    keys = set(a) | set(b)
    if not keys:
        return 0.0
    return sum(min(a[key], b[key]) for key in keys) / sum(
        max(a[key], b[key]) for key in keys
    )


def ordered_lcs_similarity(left: Sequence[str], right: Sequence[str]) -> float:
    if not left or not right:
        return 0.0
    previous = [0] * (len(right) + 1)
    for left_value in left:
        current = [0]
        for index, right_value in enumerate(right, start=1):
            if left_value == right_value:
                current.append(previous[index - 1] + 1)
            else:
                current.append(max(current[-1], previous[index]))
        previous = current
    return previous[-1] / max(len(left), len(right))


def operation_classes(value: str) -> tuple[str, ...]:
    folded = _camel_boundaries(value).replace("_", " ").casefold()
    matches = []
    for rule_index, (name, phrases) in enumerate(OPERATION_RULES):
        evidence_count = sum(folded.count(phrase) for phrase in phrases)
        if evidence_count:
            matches.append((-evidence_count, rule_index, name))
    return tuple(row[2] for row in sorted(matches)) or ("OTHER",)


def classify_task_statement(statement: str) -> dict[str, Any]:
    if not isinstance(statement, str) or not statement.strip():
        raise SourcePairingError("task statement must be non-empty")
    groups = (
        ("SAFE_IMPLEMENTATION_LEAKAGE", _SAFE_LEAKAGE_RULES),
        ("FOCAL_PRECONDITION_CUE", _FOCAL_PRECONDITION_RULES),
        ("EXPLICIT_SECURITY_REQUIREMENT", _EXPLICIT_SECURITY_RULES),
        ("GENERIC_ROBUSTNESS_CUE", _GENERIC_ROBUSTNESS_RULES),
    )
    for classification, rules in groups:
        matched = [name for name, pattern in rules if pattern.search(statement)]
        if matched:
            return {
                "classification": classification,
                "matched_rule_ids": matched,
                "public_text_eligible": classification not in CUE_INELIGIBLE,
            }
    return {
        "classification": "NO_SECURITY_CUE",
        "matched_rule_ids": [],
        "public_text_eligible": True,
    }


@dataclass(frozen=True)
class AuditEvent:
    sequence: int
    operation: str
    requested_path: str
    decision: str
    reason: str
    byte_count: int | None = None
    sha256: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "sequence": self.sequence,
            "operation": self.operation,
            "requested_path": self.requested_path,
            "decision": self.decision,
            "reason": self.reason,
            "byte_count": self.byte_count,
            "sha256": self.sha256,
        }


class AuditedWorkspaceReader:
    """The only filesystem interface exposed to pairing-side extraction."""

    def __init__(self, root: Path):
        self._root = Path(root).resolve(strict=True)
        if not self._root.is_dir() or self._root.is_symlink():
            raise PairingReadDenied("pairing workspace must be a real directory")
        self._events: list[AuditEvent] = []

    @property
    def root(self) -> Path:
        return self._root

    @property
    def events(self) -> tuple[dict[str, Any], ...]:
        return tuple(event.as_dict() for event in self._events)

    def _record(
        self,
        operation: str,
        requested: str,
        decision: str,
        reason: str,
        data: bytes | None = None,
    ) -> None:
        self._events.append(
            AuditEvent(
                sequence=len(self._events) + 1,
                operation=operation,
                requested_path=requested,
                decision=decision,
                reason=reason,
                byte_count=None if data is None else len(data),
                sha256=None if data is None else sha256_bytes(data),
            )
        )

    def _confined(self, relative: str | PurePosixPath, operation: str) -> Path:
        requested = str(relative)
        pure = PurePosixPath(requested)
        if pure.is_absolute() or not pure.parts or ".." in pure.parts:
            self._record(operation, requested, "DENY", "LEXICAL_ESCAPE")
            raise PairingReadDenied(f"pairing read denied: {requested}")
        candidate = self._root.joinpath(*pure.parts)
        try:
            resolved = candidate.resolve(strict=True)
        except (FileNotFoundError, OSError) as error:
            self._record(operation, requested, "DENY", "MISSING_OR_UNRESOLVABLE")
            raise PairingReadDenied(f"pairing read denied: {requested}") from error
        try:
            resolved.relative_to(self._root)
        except ValueError as error:
            self._record(operation, requested, "DENY", "RESOLVED_ESCAPE")
            raise PairingReadDenied(f"pairing read denied: {requested}") from error
        current = self._root
        for part in pure.parts:
            current = current / part
            if current.is_symlink():
                self._record(operation, requested, "DENY", "SYMLINK")
                raise PairingReadDenied(f"pairing symlink read denied: {requested}")
        return resolved

    def read_bytes(self, relative: str | PurePosixPath) -> bytes:
        requested = str(relative)
        path = self._confined(relative, "READ_BYTES")
        if not path.is_file():
            self._record("READ_BYTES", requested, "DENY", "NOT_FILE")
            raise PairingReadDenied(f"pairing file read denied: {requested}")
        data = path.read_bytes()
        self._record("READ_BYTES", requested, "ALLOW", "CONFINED_REGULAR_FILE", data)
        return data

    def read_text(self, relative: str | PurePosixPath) -> str:
        data = self.read_bytes(relative)
        try:
            return data.decode("utf-8")
        except UnicodeDecodeError as error:
            raise SourcePairingError(f"pairing input is not UTF-8: {relative}") from error

    def iter_files(
        self, relative: str | PurePosixPath, *, suffix: str | None = None
    ) -> tuple[str, ...]:
        requested = str(relative)
        root = self._confined(relative, "LIST_TREE")
        if not root.is_dir():
            self._record("LIST_TREE", requested, "DENY", "NOT_DIRECTORY")
            raise PairingReadDenied(f"pairing directory read denied: {requested}")
        values: list[str] = []
        for directory, names, filenames in os.walk(root, followlinks=False):
            names[:] = sorted(
                name for name in names if not Path(directory, name).is_symlink()
            )
            for filename in sorted(filenames):
                candidate = Path(directory, filename)
                if candidate.is_symlink():
                    continue
                workspace_relative = candidate.relative_to(self._root).as_posix()
                if suffix is None or workspace_relative.endswith(suffix):
                    values.append(workspace_relative)
        self._record("LIST_TREE", requested, "ALLOW", "CONFINED_TREE")
        return tuple(values)


def _attribute_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _attribute_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return None


def python_features(source: str) -> dict[str, tuple[str, ...]]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return {
            "imports": (),
            "libraries": (),
            "api_sequence": (),
            "ast_signature": (),
            "symbols": (),
            "types_and_data_roles": data_roles(source),
        }
    imports: list[str] = []
    calls: list[tuple[int, int, str]] = []
    symbols: list[str] = []
    nodes: list[str] = []
    for node in ast.walk(tree):
        nodes.append(type(node).__name__)
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            imports.extend(
                f"{module}.{alias.name}".strip(".") for alias in node.names
            )
        elif isinstance(node, ast.Call):
            name = _attribute_name(node.func)
            if name:
                calls.append((node.lineno, node.col_offset, name))
        elif isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            symbols.append(node.name)
    libraries = sorted({value.split(".", 1)[0] for value in imports if value})
    ast_counts = Counter(nodes)
    return {
        "imports": tuple(sorted(set(imports))),
        "libraries": tuple(libraries),
        "api_sequence": tuple(value for _, _, value in sorted(calls)),
        "ast_signature": tuple(
            f"{name}:{count}" for name, count in sorted(ast_counts.items())
        ),
        "symbols": tuple(sorted(set(symbols))),
        "types_and_data_roles": data_roles(source),
    }


def data_roles(value: str) -> tuple[str, ...]:
    folded = value.casefold()
    rules = {
        "AUTH_CREDENTIAL": ("password", "credential", "authorization", "auth"),
        "COLLECTION_OR_MAPPING": ("mapping", "dict", "headers", "params"),
        "IDENTITY": ("identity", "principal", "user", "session_key"),
        "LENGTH_OR_AGE": ("length", "len(", "max_age", "created", "ttl"),
        "PATH_OR_URL": ("path", "url", "uri", "href", "location"),
        "PROXY": ("proxy", "no_proxy"),
        "SERIALIZED_DATA": ("encoded", "decode", "json", "html", "contentstate"),
    }
    return tuple(
        name for name, phrases in sorted(rules.items()) if any(p in folded for p in phrases)
    )


def _task_references(statement: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    file_or_modules: set[str] = set()
    symbols: set[str] = set()
    for raw in _BACKTICK.findall(statement):
        value = raw.strip().strip(".,()")
        if value.endswith(".py") or "." in value:
            file_or_modules.add(value)
        for identifier in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", value):
            if identifier not in {"py", "python", "None", "True", "False"}:
                symbols.add(identifier)
    file_or_modules.update(_DOTTED_MODULE.findall(statement))
    return tuple(sorted(file_or_modules)), tuple(sorted(symbols))


def _candidate_module_suffixes(reference: str) -> tuple[str, ...]:
    cleaned = reference.strip().strip(".,()")
    if cleaned.endswith(".py"):
        return (cleaned.lstrip("/"),)
    if re.fullmatch(r"(?:[a-z_][a-z0-9_]*\.)+[a-z_][a-z0-9_]*", cleaned):
        parts = cleaned.split(".")
        return ("/".join(parts) + ".py", "/".join(parts[:-1]) + ".py")
    return ()


def build_b_only_representation(reader: AuditedWorkspaceReader) -> dict[str, Any]:
    task_statement = reader.read_text("task.md")
    metadata = json.loads(reader.read_text("public-metadata.json"))
    if not isinstance(metadata, dict) or set(metadata) != PUBLIC_METADATA_FIELDS:
        raise SourcePairingError("public metadata fields changed or include sealed data")
    if metadata.get("instance_id") not in DEVELOPMENT_IDS:
        raise PermissionError("B-only extraction is development-ID-only")
    if metadata.get("benchmark_revision") != SUSVIBES_REVISION:
        raise SourcePairingError("SusVibes revision mismatch")
    if metadata.get("language") != "python":
        raise SourcePairingError("development matcher supports only pinned Python tasks")

    references, task_symbols = _task_references(task_statement)
    python_paths = reader.iter_files("repository", suffix=".py")
    selected_paths: set[str] = set()
    for reference in references:
        for suffix in _candidate_module_suffixes(reference):
            selected_paths.update(path for path in python_paths if path.endswith(suffix))
    if not selected_paths and task_symbols:
        definition_patterns = tuple(
            re.compile(rf"^\s*(?:async\s+def|def|class)\s+{re.escape(symbol)}\b", re.M)
            for symbol in task_symbols
        )
        mention_patterns = tuple(
            re.compile(rf"\b{re.escape(symbol)}\b") for symbol in task_symbols
        )
        mentioned_paths: list[str] = []
        for path in python_paths:
            text = reader.read_text(path)
            if any(pattern.search(text) for pattern in definition_patterns):
                selected_paths.add(path)
            elif any(pattern.search(text) for pattern in mention_patterns):
                mentioned_paths.append(path)
        if not selected_paths:
            selected_paths.update(mentioned_paths[:8])
    selected = tuple(sorted(selected_paths)[:8])
    aggregate = {
        "imports": [],
        "libraries": [],
        "api_sequence": [],
        "ast_signature": [],
        "symbols": [],
        "types_and_data_roles": [],
    }
    code_bytes = bytearray()
    for path in selected:
        source = reader.read_text(path)
        code_bytes.extend(source.encode("utf-8"))
        features = python_features(source)
        for key in aggregate:
            aggregate[key].extend(features[key])
    classes = operation_classes(task_statement)
    task_vector = hash_vector(task_statement)
    representation = {
        "benchmark_instance_id": metadata["instance_id"],
        "benchmark_revision": metadata["benchmark_revision"],
        "b_snapshot_sha256": metadata["b_tree_sha256"],
        "task_statement": task_statement,
        "language": metadata["language"],
        "repository_visible_imports": sorted(set(aggregate["imports"])),
        "repository_visible_libraries": sorted(set(aggregate["libraries"])),
        "repository_visible_api_calls": list(aggregate["api_sequence"]),
        "task_described_operation": classes[0],
        "visible_target_symbols": sorted(set(task_symbols) | set(aggregate["symbols"])),
        "types_and_data_roles": sorted(
            set(data_roles(task_statement)) | set(aggregate["types_and_data_roles"])
        ),
        "ast_structure": sorted(set(aggregate["ast_signature"])),
        "operation_categories": list(classes),
        "task_semantic_embedding": {
            "model": "deterministic-local-hash-vectorizer",
            "model_revision": HASH_VECTORIZER_REVISION,
            "vector": list(task_vector),
        },
        "configuration_context": {
            "b_code_available": bool(selected),
            "b_code_file_count": len(selected),
            "b_code_files": ",".join(selected),
            "b_code_sha256": sha256_bytes(bytes(code_bytes)),
            "feature_extractor": PAIRING_SCHEMA,
            "normalized_task_tokens_sha256": sha256_bytes(
                "\n".join(normalized_tokens(task_statement)).encode("utf-8")
            ),
        },
    }
    validate_b_only_mapping(representation)
    return representation


def validate_b_only_mapping(value: Mapping[str, Any]) -> None:
    serialized = json.dumps(value, sort_keys=True).casefold()
    for forbidden in FORBIDDEN_B_ONLY_KEYS:
        if forbidden in value or re.search(rf'"{re.escape(forbidden)}"\s*:', serialized):
            raise SourcePairingError(f"B-only representation contains forbidden field: {forbidden}")
    if value.get("benchmark_instance_id") not in DEVELOPMENT_IDS:
        raise SourcePairingError("B-only representation names a non-development target")
    if value.get("benchmark_revision") != SUSVIBES_REVISION:
        raise SourcePairingError("B-only representation revision mismatch")
    if not re.fullmatch(r"[0-9a-f]{64}", str(value.get("b_snapshot_sha256", ""))):
        raise SourcePairingError("B-only representation has invalid B hash")


def extract_python_symbol(source: str, symbol: str) -> tuple[str, int, int]:
    """Extract exact source lines for one uniquely named class/function."""

    tree = ast.parse(source)
    candidates = [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == symbol
    ]
    if len(candidates) != 1:
        raise SourcePairingError(
            f"source symbol must resolve uniquely: {symbol}: {len(candidates)}"
        )
    node = candidates[0]
    start = min(
        [node.lineno]
        + [decorator.lineno for decorator in getattr(node, "decorator_list", [])]
    )
    end = int(node.end_lineno or node.lineno)
    lines = source.splitlines(keepends=True)
    exact = "".join(lines[start - 1 : end])
    if source and not exact:
        raise SourcePairingError("empty source extraction")
    return exact, start, end


def source_feature_record(code: str, source_task: str) -> dict[str, Any]:
    features = python_features(code)
    semantic = hash_vector(source_task)
    return {
        "operation_class": list(operation_classes(source_task + "\n" + code)),
        "API_sequence": list(features["api_sequence"]),
        "AST_signature": list(features["ast_signature"]),
        "normalized_token_signature": list(token_shingles(code)),
        "type_or_data_role_signature": list(features["types_and_data_roles"]),
        "source_semantic_vector": list(semantic),
        "source_visible_libraries": list(features["libraries"]),
    }


def source_entry_eligible(entry: Mapping[str, Any], target_timestamp: int) -> bool:
    return bool(
        entry.get("language") == "python"
        and isinstance(entry.get("commit_timestamp_epoch"), int)
        and entry["commit_timestamp_epoch"] <= target_timestamp
        and entry.get("source_build", {}).get("classification") == "PASS"
        and entry.get("source_task_test", {}).get("classification") == "PASS"
        and entry.get("focal_source_safety", {}).get("level")
        in CONFIRMATORY_FOCAL_SAFETY_LEVELS
        and entry.get("focal_source_safety", {}).get("classification") == "PASS"
    )


def score_candidate(
    target: Mapping[str, Any], entry: Mapping[str, Any]
) -> dict[str, float | int | bool]:
    target_operations = tuple(str(value) for value in target["operation_categories"])
    source_operations = tuple(str(value) for value in entry["operation_class"])
    target_apis = tuple(str(value) for value in target["repository_visible_api_calls"])
    source_apis = tuple(str(value) for value in entry["API_sequence"])
    target_libraries = tuple(str(value) for value in target["repository_visible_libraries"])
    source_libraries = tuple(str(value) for value in entry.get("source_visible_libraries", []))
    target_ast = tuple(str(value) for value in target["ast_structure"])
    source_ast = tuple(str(value) for value in entry["AST_signature"])
    target_roles = tuple(str(value) for value in target["types_and_data_roles"])
    source_roles = tuple(str(value) for value in entry["type_or_data_role_signature"])
    target_semantic = target["task_semantic_embedding"]["vector"]
    source_semantic = entry["source_semantic_vector"]
    target_text = "\n".join(
        (
            str(target["task_statement"]),
            " ".join(str(value) for value in target["visible_target_symbols"]),
            " ".join(target_apis),
        )
    )
    return {
        "language_exact": entry.get("language") == target.get("language"),
        "operation_class_exact": bool(set(target_operations) & set(source_operations)),
        "same_library_or_api": bool(
            set(target_libraries) & set(source_libraries)
            or set(target_apis) & set(source_apis)
        ),
        "api_sequence_similarity": round(
            ordered_lcs_similarity(target_apis, source_apis), 12
        ),
        "type_data_role_similarity": round(
            multiset_jaccard(target_roles, source_roles), 12
        ),
        "ast_similarity": round(multiset_jaccard(target_ast, source_ast), 12),
        "token_similarity": round(
            jaccard_similarity(
                token_shingles(target_text), entry["normalized_token_signature"]
            ),
            12,
        ),
        "semantic_similarity": round(
            cosine_similarity(target_semantic, source_semantic), 12
        ),
    }


_CONTINUOUS_FEATURES = (
    "api_sequence_similarity",
    "type_data_role_similarity",
    "ast_similarity",
    "token_similarity",
    "semantic_similarity",
)


def _tier_number(value: str) -> int:
    match = re.fullmatch(r"S([123])", value)
    if not match:
        raise SourcePairingError(f"invalid source tier: {value}")
    return int(match.group(1))


def _ranking_key(row: Mapping[str, Any]) -> tuple[Any, ...]:
    score = row["scores"]
    return (
        -int(bool(score["operation_class_exact"])),
        -int(bool(score["same_library_or_api"])),
        *(-float(score[name]) for name in _CONTINUOUS_FEATURES),
        _tier_number(str(row["source_tier"])),
        str(row["source_id"]),
    )


def rank_sources(
    target: Mapping[str, Any],
    entries: Sequence[Mapping[str, Any]],
    *,
    target_timestamp: int,
) -> list[dict[str, Any]]:
    validate_b_only_mapping(target)
    rows = []
    seen: set[str] = set()
    for entry in entries:
        source_id = str(entry.get("source_id", ""))
        if not source_id or source_id in seen:
            raise SourcePairingError("source IDs must be non-empty and unique")
        seen.add(source_id)
        scores = score_candidate(target, entry)
        eligible = source_entry_eligible(entry, target_timestamp) and bool(
            scores["language_exact"]
        )
        rows.append(
            {
                "source_id": source_id,
                "source_tier": entry["source_tier"],
                "hard_gate_pass": eligible,
                "scores": scores,
            }
        )
    rows.sort(key=lambda row: (not row["hard_gate_pass"], _ranking_key(row)))
    for index, row in enumerate(rows, start=1):
        row["rank"] = index
    return rows


def threshold_pass(scores: Mapping[str, Any], thresholds: Mapping[str, float]) -> bool:
    if not scores.get("language_exact") or not scores.get("operation_class_exact"):
        return False
    return all(float(scores.get(name, 0.0)) >= float(value) for name, value in thresholds.items())


def select_top_source(
    target: Mapping[str, Any],
    entries: Sequence[Mapping[str, Any]],
    *,
    target_timestamp: int,
    thresholds: Mapping[str, float],
    ambiguity_margins: Mapping[str, float],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rankings = rank_sources(target, entries, target_timestamp=target_timestamp)
    accepted = [
        row
        for row in rankings
        if row["hard_gate_pass"] and threshold_pass(row["scores"], thresholds)
    ]
    if not accepted:
        raise SourcePairingError("NO_SOURCE_PASSES_FROZEN_THRESHOLD")
    top = accepted[0]
    if len(accepted) > 1:
        runner_up = accepted[1]
        top_discrete = (
            top["scores"]["operation_class_exact"],
            top["scores"]["same_library_or_api"],
        )
        runner_discrete = (
            runner_up["scores"]["operation_class_exact"],
            runner_up["scores"]["same_library_or_api"],
        )
        if top_discrete == runner_discrete:
            separated = False
            all_equal = True
            for name in _CONTINUOUS_FEATURES:
                difference = float(top["scores"][name]) - float(
                    runner_up["scores"][name]
                )
                if difference:
                    all_equal = False
                    margin = float(ambiguity_margins.get(name, math.inf))
                    separated = difference >= margin
                    break
            if all_equal or not separated:
                raise SourcePairingError("AMBIGUOUS_TOP_SOURCE")

    target_hash = stable_record_hash(target)
    corpus_hash = stable_record_hash(list(entries))
    ranking_config = {
        "thresholds": dict(sorted(thresholds.items())),
        "ambiguity_margins": dict(sorted(ambiguity_margins.items())),
        "ranking": [
            "operation_class_exact",
            "same_library_or_api",
            *_CONTINUOUS_FEATURES,
            "tier",
        ],
    }
    lock_body = {
        "schema": "cmpilot-source-pair-lock-v1",
        "target_id": target["benchmark_instance_id"],
        "top_source_id": top["source_id"],
        "target_representation_sha256": target_hash,
        "source_corpus_sha256": corpus_hash,
        "ranking_configuration_sha256": stable_record_hash(ranking_config),
        "full_rankings_sha256": stable_record_hash(rankings),
    }
    lock = {**lock_body, "pair_hash": stable_record_hash(lock_body)}
    return rankings, lock


def enforce_top_source_lock(lock: Mapping[str, Any], requested_source_id: str) -> None:
    if requested_source_id != lock.get("top_source_id"):
        raise PermissionError("rank-2/manual source fallback is forbidden")
    body = {key: value for key, value in lock.items() if key != "pair_hash"}
    if stable_record_hash(body) != lock.get("pair_hash"):
        raise SourcePairingError("source pair lock hash mismatch")


def sealed_validation_request(lock: Mapping[str, Any]) -> dict[str, str]:
    enforce_top_source_lock(lock, str(lock.get("top_source_id", "")))
    return {
        "target_id": str(lock["target_id"]),
        "top_source_id": str(lock["top_source_id"]),
        "pair_hash": str(lock["pair_hash"]),
    }


def validate_sealed_response(value: Mapping[str, Any]) -> None:
    allowed = {"decision", "questions", "evidence_hashes", "pair_hash"}
    if set(value) != allowed:
        raise SourcePairingError("sealed validator returned advice or unexpected fields")
    if value.get("decision") not in {"ACCEPT", "REJECT"}:
        raise SourcePairingError("invalid sealed decision")
    questions = value.get("questions")
    if not isinstance(questions, dict) or set(questions) != {
        f"Q{number}" for number in range(1, 17)
    }:
        raise SourcePairingError("sealed response must contain the fixed 16 questions")
    if any(answer not in {"YES", "NO", "UNKNOWN"} for answer in questions.values()):
        raise SourcePairingError("invalid pair-review answer")
    expected = "ACCEPT" if all(answer == "YES" for answer in questions.values()) else "REJECT"
    if value["decision"] != expected:
        raise SourcePairingError("sealed decision disagrees with all-YES rule")
    hashes = value.get("evidence_hashes")
    if not isinstance(hashes, dict) or any(
        not re.fullmatch(r"[0-9a-f]{64}", str(digest)) for digest in hashes.values()
    ):
        raise SourcePairingError("sealed evidence hashes are invalid")


def validate_pstar(value: Mapping[str, Any]) -> None:
    required = {
        "ontology_class",
        "proposition",
        "observable_objects",
        "operation",
        "quantifier_or_boundary",
        "verification_method",
        "source_truth",
        "target_truth",
    }
    if set(value) != required:
        raise SourcePairingError("pstar fields differ from frozen schema")
    if value["ontology_class"] not in PSTAR_ONTOLOGY:
        raise SourcePairingError("unknown pstar ontology class")
    for name in (
        "proposition",
        "operation",
        "quantifier_or_boundary",
        "verification_method",
    ):
        if not isinstance(value[name], str) or not value[name].strip():
            raise SourcePairingError(f"pstar {name} must be non-empty")
    objects = value["observable_objects"]
    if not isinstance(objects, list) or not objects or not all(
        isinstance(item, str) and item.strip() for item in objects
    ):
        raise SourcePairingError("pstar observable objects must be explicit")
    if value["source_truth"] is not True:
        raise SourcePairingError("pstar source truth must be TRUE")
    if value["target_truth"] not in {"FALSE", "UNJUSTIFIED"}:
        raise SourcePairingError("pstar target truth must be FALSE or UNJUSTIFIED")
    proposition = str(value["proposition"]).casefold()
    if proposition.strip() == "input is trusted" or (
        "trusted" in proposition and len(value["observable_objects"]) < 2
    ):
        raise SourcePairingError("pstar trust must be operationally defined")


def calibration_grid(values: Iterable[float]) -> tuple[float, ...]:
    unique = sorted(set(float(value) for value in values))
    if not unique:
        return ()
    grid = set(unique)
    grid.update((left + right) / 2 for left, right in zip(unique, unique[1:]))
    return tuple(sorted(grid))


def calibrate_threshold(
    rows: Sequence[Mapping[str, Any]], feature: str
) -> dict[str, Any]:
    """Apply the prospectively frozen zero-negative/two-repository rule."""

    if not rows:
        return {"feature": feature, "freezeable": False, "reason": "NO_ROWS"}
    grid = calibration_grid(float(row[feature]) for row in rows)
    qualifying = []
    for threshold in grid:
        accepted = [row for row in rows if float(row[feature]) >= threshold]
        negative_count = sum(row["label"] == "NEGATIVE" for row in accepted)
        positive_repositories = {
            str(row["source_repository"])
            for row in accepted
            if row["label"] == "POSITIVE"
        }
        if negative_count == 0 and len(positive_repositories) >= 2:
            qualifying.append(
                (
                    sum(row["label"] == "POSITIVE" for row in accepted),
                    threshold,
                    accepted,
                )
            )
    if not qualifying:
        return {
            "feature": feature,
            "freezeable": False,
            "reason": "NO_ZERO_NEGATIVE_TWO_REPOSITORY_SEPARATION",
            "grid": list(grid),
        }
    recall, threshold, accepted = max(qualifying, key=lambda item: (item[0], item[1]))
    return {
        "feature": feature,
        "freezeable": True,
        "threshold": threshold,
        "accepted_positive_count": recall,
        "accepted_negative_count": 0,
        "accepted_source_repositories": sorted(
            {
                str(row["source_repository"])
                for row in accepted
                if row["label"] == "POSITIVE"
            }
        ),
        "grid": list(grid),
    }


def python_token_stream(source: bytes) -> tuple[str, ...]:
    """Expose exact tokenizer-normalized code tokens for fidelity tests."""

    values = []
    try:
        stream = tokenize.tokenize(BytesIO(source).readline)
        for token in stream:
            if token.type in {tokenize.NAME, tokenize.NUMBER, tokenize.STRING, tokenize.OP}:
                values.append(token.string)
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return ()
    return tuple(values)
