"""Prospective, target-independent source-corpus construction for V2.

This module only inspects ordinary upstream repository snapshots.  It has no
SusVibes row reader, target workspace reader, oracle reader, model client, or
network client.  Callers must materialize exact, protocol-eligible Git objects
before invoking discovery.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
import ast
import hashlib
from pathlib import Path, PurePosixPath
import re
from typing import Any, Iterable, Mapping, Sequence

from cmpilot.source_pairing import (
    TARGET_SOURCE_FILE_EXCLUSIONS,
    sha256_bytes,
    source_feature_record,
    stable_record_hash,
)


PROTOCOL_ID = "SOURCE_PAIRING_DEVELOPMENT_SUCCESSOR_V2"
SUCCESSOR_PROTOCOL_COMMIT = "9bf08a16241eac92e79a36c2bc3421adfa1623de"
SUSVIBES_REVISION = "7e1b4b05240e56dc2b4e8253b2cc5c9481d016f3"
SUSVIBES_DATASET_SHA256 = (
    "0cb5fbffe7ba59a8e16d42c293944bdd8e1e23795941a4b496ac1043722b9550"
)
SOURCE_ONLY_PARTITION_USED = False
INHERITED_V1_ENTRIES = 12
CORPUS_SIZE_CHOICES = (50, 100, 200)
PILOT_NEW_ATTEMPTS = 10
MACHINE_HOUR_CAP = 4.0
REVIEWER_HOUR_CAP = 4.0
REVIEW_MINUTES_PER_QUALIFIED_ENTRY = 5.0
MATERIALIZATION_GIB_CAP = 50.0
NEW_CANDIDATE_ATTEMPT_CAP = 400

_SHA1 = re.compile(r"^[0-9a-f]{40}$")
_INSTANCE = re.compile(
    r"^(?P<owner>.+?)__(?P<repository>.+)_(?P<anchor>[0-9a-f]{40})$"
)
_SAFE_FRAGMENT = re.compile(r"[^a-z0-9]+")


class SourceCorpusV2Error(ValueError):
    """A frozen V2 source-universe or extraction invariant failed."""


@dataclass(frozen=True, order=True)
class RepositoryAnchor:
    """Metadata-only repository identity derived from a SusVibes instance ID."""

    ordering_sha256: str
    repository_url: str
    anchor_commit: str
    source_commit_rule: str = "STRICT_FIRST_PARENT"

    def as_dict(self) -> dict[str, str]:
        return {
            "repository_url": self.repository_url,
            "anchor_commit": self.anchor_commit,
            "source_commit_rule": self.source_commit_rule,
            "ordering_sha256": self.ordering_sha256,
        }


@dataclass(frozen=True)
class _Definition:
    module: str
    path: str
    symbol: str
    node: ast.FunctionDef | ast.AsyncFunctionDef
    text: str


@dataclass(frozen=True)
class _TestNode:
    path: str
    qualified_name: str
    node: ast.FunctionDef | ast.AsyncFunctionDef
    module_tree: ast.Module
    text: str


OPERATION_RULES_V2: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "AUTHENTICATION_AUTHORIZATION",
        (
            "authentication",
            "authorization",
            "credential",
            "permission",
            "password",
            "login",
            "token",
            "signature",
        ),
    ),
    (
        "PATH_OR_URL_VALIDATION",
        ("path", "url", "uri", "redirect", "location", "host", "scheme", "slug"),
    ),
    (
        "ENCODING_CANONICALIZATION",
        ("encode", "decode", "unicode", "bytes", "base64", "quote", "escape"),
    ),
    (
        "SESSION_STATE_LIFECYCLE",
        ("session", "cookie", "state", "cache", "invalidate", "identity"),
    ),
    (
        "MARKUP_SERIALIZATION",
        ("html", "markup", "link", "anchor", "template", "render", "xml"),
    ),
    (
        "FILE_RESOURCE_IO",
        ("file", "stream", "storage", "read", "write", "load", "dump"),
    ),
    (
        "PROTOCOL_LAYOUT",
        ("header", "parse", "format", "split", "join", "field", "request", "response"),
    ),
    (
        "TIME_BOUNDARY",
        ("time", "date", "ttl", "expiry", "expires", "timeout", "epoch", "timezone"),
    ),
    (
        "NUMERIC_BOUNDS",
        ("length", "size", "bounds", "index", "count", "maximum", "minimum"),
    ),
    (
        "COLLECTION_MAPPING",
        ("mapping", "dictionary", "dict", "collection", "keys", "values", "merge"),
    ),
    (
        "MODEL_OBJECT_RESOLUTION",
        ("model", "object", "resolve", "lookup", "registry", "import"),
    ),
    (
        "COMMAND_PROCESS_EXECUTION",
        ("command", "process", "shell", "executable", "argument", "subprocess"),
    ),
)

_PSTAR_BY_OPERATION: Mapping[str, str] = {
    "AUTHENTICATION_AUTHORIZATION": "AUTHENTICATION_AUTHORIZATION",
    "PATH_OR_URL_VALIDATION": "PATH_PROVENANCE",
    "ENCODING_CANONICALIZATION": "ENCODING_CANONICALIZATION",
    "SESSION_STATE_LIFECYCLE": "RESOURCE_TRUST_BOUNDARY_ORDERING",
    "MARKUP_SERIALIZATION": "PROTOCOL_LAYOUT",
    "FILE_RESOURCE_IO": "RESOURCE_TRUST_BOUNDARY_ORDERING",
    "PROTOCOL_LAYOUT": "PROTOCOL_LAYOUT",
    "TIME_BOUNDARY": "BOUNDS_LENGTH",
    "NUMERIC_BOUNDS": "BOUNDS_LENGTH",
    "COLLECTION_MAPPING": "BOUNDS_LENGTH",
    "MODEL_OBJECT_RESOLUTION": "VALIDATION_BEFORE_USE",
    "COMMAND_PROCESS_EXECUTION": "VALIDATION_BEFORE_USE",
}

_OBSERVABLES_BY_OPERATION: Mapping[str, tuple[str, ...]] = {
    "AUTHENTICATION_AUTHORIZATION": ("input principal or credential", "authorization result"),
    "PATH_OR_URL_VALIDATION": ("input path or URL", "returned path, URL, or rejection"),
    "ENCODING_CANONICALIZATION": ("input representation", "decoded or encoded representation"),
    "SESSION_STATE_LIFECYCLE": ("input session state", "returned or persisted session state"),
    "MARKUP_SERIALIZATION": ("input markup data", "rendered or parsed markup"),
    "FILE_RESOURCE_IO": ("input resource", "read, written, or rejected resource state"),
    "PROTOCOL_LAYOUT": ("input fields", "parsed or formatted protocol value"),
    "TIME_BOUNDARY": ("input time value", "bounded temporal result"),
    "NUMERIC_BOUNDS": ("input numeric or sized value", "bounded result or rejection"),
    "COLLECTION_MAPPING": ("input collection", "returned collection mapping"),
    "MODEL_OBJECT_RESOLUTION": ("input model identifier", "resolved object or rejection"),
    "COMMAND_PROCESS_EXECUTION": ("input command arguments", "constructed or executed command"),
}


def parse_instance_repository_anchor(instance_id: str) -> RepositoryAnchor:
    """Parse only the public instance identifier; no task row is accepted."""

    if not isinstance(instance_id, str):
        raise SourceCorpusV2Error("instance ID must be text")
    match = _INSTANCE.fullmatch(instance_id)
    if not match:
        raise SourceCorpusV2Error(f"invalid SusVibes instance ID: {instance_id}")
    owner = match.group("owner")
    repository = match.group("repository")
    if not owner or not repository or "/" in owner or "/" in repository:
        raise SourceCorpusV2Error("instance ID cannot form a canonical repository URL")
    url = f"https://github.com/{owner}/{repository}.git"
    anchor = match.group("anchor")
    ordering = hashlib.sha256(
        f"{PROTOCOL_ID}|S2|{url}|{anchor}".encode("utf-8")
    ).hexdigest()
    return RepositoryAnchor(ordering, url, anchor)


def build_s2_universe(instance_ids: Iterable[str]) -> tuple[dict[str, str], ...]:
    """Return the frozen, de-duplicated S2 queue in protocol order."""

    identities: dict[tuple[str, str], RepositoryAnchor] = {}
    for instance_id in instance_ids:
        anchor = parse_instance_repository_anchor(instance_id)
        identities[(anchor.repository_url, anchor.anchor_commit)] = anchor
    if not identities:
        raise SourceCorpusV2Error("S2 universe cannot be empty")
    return tuple(item.as_dict() for item in sorted(identities.values()))


def source_only_partition_assessment(instance_ids: Iterable[str]) -> dict[str, Any]:
    """Record the frozen non-use decision without exposing or assigning rows."""

    values = tuple(sorted(set(instance_ids)))
    hypothetical = tuple(
        value
        for value in values
        if int(
            hashlib.sha256(f"{PROTOCOL_ID}|{value}".encode("utf-8")).hexdigest(),
            16,
        )
        % 5
        == 0
    )
    return {
        "schema": "cmpilot-source-only-partition-assessment-v2",
        "protocol_id": PROTOCOL_ID,
        "source_only_partition_used": False,
        "implemented_assignment": None,
        "unseen_input_count": len(values),
        "hypothetical_rule": "SHA256(PROTOCOL_ID|INSTANCE_ID) MOD 5 == 0",
        "hypothetical_source_only_count": len(hypothetical),
        "hypothetical_future_target_count": len(values) - len(hypothetical),
        "hypothetical_source_ids_sha256": sha256_bytes(
            ("\n".join(hypothetical) + "\n").encode("utf-8")
        ),
        "decision": "NOT_USED",
        "candidate_specific_fields_read": ["instance_id"],
    }


def _is_test_path(relative: PurePosixPath) -> bool:
    parts = set(relative.parts)
    return bool(
        parts & {"test", "tests"}
        or relative.name.startswith("test_")
        or relative.name.endswith("_test.py")
    )


def _module_name(relative: PurePosixPath) -> str:
    parts = list(relative.with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _node_text(text: str, node: ast.AST) -> tuple[str, int, int]:
    line = int(getattr(node, "lineno"))
    decorators = getattr(node, "decorator_list", ())
    start = min([line, *(int(item.lineno) for item in decorators)])
    end = int(getattr(node, "end_lineno", line) or line)
    exact = "".join(text.splitlines(keepends=True)[start - 1 : end])
    if not exact.strip():
        raise SourceCorpusV2Error("AST node extraction produced empty bytes")
    return exact, start, end


def _test_nodes(tree: ast.Module, text: str, path: str) -> tuple[_TestNode, ...]:
    values: list[_TestNode] = []

    def visit(body: Sequence[ast.stmt], prefix: tuple[str, ...] = ()) -> None:
        for node in body:
            if isinstance(node, ast.ClassDef):
                visit(node.body, (*prefix, node.name))
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                qualified = ".".join((*prefix, node.name))
                if node.name.startswith("test") and _has_executable_assertion(node):
                    values.append(_TestNode(path, qualified, node, tree, text))

    visit(tree.body)
    return tuple(values)


def _has_executable_assertion(node: ast.AST) -> bool:
    for candidate in ast.walk(node):
        if isinstance(candidate, ast.Assert):
            return True
        if isinstance(candidate, ast.Call):
            name = _call_name(candidate.func)
            if name and (
                name.split(".")[-1].startswith(("assert", "fail"))
                or name.split(".")[-1] == "raises"
            ):
                return True
        if isinstance(candidate, (ast.With, ast.AsyncWith)):
            if any(
                (_call_name(item.context_expr) or "").split(".")[-1]
                in {"raises", "assertRaises", "assertRaisesRegex"}
                for item in candidate.items
            ):
                return True
    return False


def _call_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _call_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    if isinstance(node, ast.Call):
        return _call_name(node.func)
    return None


def _referenced_names(node: ast.AST) -> set[str]:
    names = {candidate.id for candidate in ast.walk(node) if isinstance(candidate, ast.Name)}
    names.update(
        candidate.attr
        for candidate in ast.walk(node)
        if isinstance(candidate, ast.Attribute)
    )
    return names


def _direct_imports(test: _TestNode) -> tuple[tuple[str, str, str], ...]:
    imports: set[tuple[str, str, str]] = set()
    scopes: tuple[ast.AST, ...] = (test.module_tree, test.node)
    for scope in scopes:
        for node in ast.walk(scope):
            if isinstance(node, ast.ImportFrom) and node.module:
                for alias in node.names:
                    if alias.name != "*":
                        imports.add(
                            (node.module, alias.name, alias.asname or alias.name)
                        )
    return tuple(sorted(imports))


def _resolve_module(
    requested: str, modules: Mapping[str, tuple[_Definition, ...]]
) -> tuple[_Definition, ...] | None:
    matches = [
        definitions
        for module, definitions in modules.items()
        if module == requested or module.endswith(f".{requested}")
    ]
    return matches[0] if len(matches) == 1 else None


def operation_classes_v2(value: str) -> tuple[str, ...]:
    folded = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", value).replace("_", " ").casefold()
    matches: list[tuple[int, int, str]] = []
    for index, (name, terms) in enumerate(OPERATION_RULES_V2):
        count = sum(folded.count(term) for term in terms)
        if count:
            matches.append((-count, index, name))
    return tuple(item[2] for item in sorted(matches)) or ("OTHER",)


def _mechanical_pstar(
    *, operation_class: str, symbol: str, test_name: str
) -> dict[str, Any]:
    if operation_class not in _PSTAR_BY_OPERATION:
        raise SourceCorpusV2Error("mechanical pstar requires a controlled operation")
    observables = list(_OBSERVABLES_BY_OPERATION[operation_class])
    return {
        "ontology_class": _PSTAR_BY_OPERATION[operation_class],
        "proposition": (
            f"For every invocation of {symbol} exercised by upstream test "
            f"{test_name}, the named observable result or rejection satisfies "
            "that test node's exact executable assertions."
        ),
        "observable_objects": observables,
        "operation": symbol,
        "quantifier_or_boundary": (
            f"every {symbol} invocation executed by the exact {test_name} test node"
        ),
        "verification_method": (
            "execute the recorded upstream test command and preserve its exact "
            "assertion-bearing test-node hash"
        ),
        "source_truth": True,
        "target_truth": "UNJUSTIFIED",
    }


def _source_id(repository_url: str, path: str, symbol: str, identity: str) -> str:
    repository = repository_url.removesuffix(".git").rsplit("/", 1)[-1].casefold()
    fragment = _SAFE_FRAGMENT.sub("-", f"{repository}-{Path(path).stem}-{symbol}".casefold())
    fragment = fragment.strip("-")[:52].rstrip("-")
    return f"src-v2-{fragment}-{identity[:12]}"


def discover_source_candidates(
    snapshot: Path,
    *,
    repository_url: str,
    repository_commit: str,
    tier: str,
    excluded_paths: Iterable[str] = TARGET_SOURCE_FILE_EXCLUSIONS,
) -> dict[str, Any]:
    """Discover exact production/test pairs without target-side inputs."""

    root = Path(snapshot).resolve(strict=True)
    if not root.is_dir() or root.is_symlink():
        raise SourceCorpusV2Error("source snapshot must be a real directory")
    if not repository_url.startswith("https://github.com/") or not repository_url.endswith(
        ".git"
    ):
        raise SourceCorpusV2Error("source repository URL is not canonical")
    if not _SHA1.fullmatch(repository_commit):
        raise SourceCorpusV2Error("source repository commit is invalid")
    if tier not in {"S1", "S2"}:
        raise SourceCorpusV2Error("V2 discovery accepts only S1 or S2")

    exclusions = {PurePosixPath(value).as_posix() for value in excluded_paths}
    modules: dict[str, tuple[_Definition, ...]] = {}
    tests: list[_TestNode] = []
    parse_failures: list[dict[str, str]] = []
    file_count = 0
    for path in sorted(root.rglob("*.py")):
        if path.is_symlink():
            continue
        relative = PurePosixPath(path.relative_to(root).as_posix())
        file_count += 1
        try:
            text = path.read_text(encoding="utf-8")
            tree = ast.parse(text, filename=relative.as_posix())
        except (OSError, UnicodeError, SyntaxError) as error:
            parse_failures.append(
                {"path": relative.as_posix(), "error_type": type(error).__name__}
            )
            continue
        if _is_test_path(relative):
            tests.extend(_test_nodes(tree, text, relative.as_posix()))
            continue
        if relative.as_posix() in exclusions:
            continue
        definitions: list[_Definition] = []
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                exact, _, _ = _node_text(text, node)
                definitions.append(
                    _Definition(
                        _module_name(relative),
                        relative.as_posix(),
                        node.name,
                        node,
                        exact,
                    )
                )
        if definitions:
            module = _module_name(relative)
            if module in modules:
                raise SourceCorpusV2Error(f"duplicate module identity: {module}")
            modules[module] = tuple(definitions)

    mappings: dict[tuple[str, str], list[_TestNode]] = defaultdict(list)
    for test in sorted(tests, key=lambda item: (item.path, item.qualified_name)):
        referenced = _referenced_names(test.node)
        for requested_module, imported_symbol, local_name in _direct_imports(test):
            if local_name not in referenced:
                continue
            definitions = _resolve_module(requested_module, modules)
            if definitions is None:
                continue
            matches = [item for item in definitions if item.symbol == imported_symbol]
            if len(matches) == 1:
                mappings[(matches[0].path, matches[0].symbol)].append(test)

    candidate_rows: list[dict[str, Any]] = []
    excluded_rows: list[dict[str, str]] = []
    for (source_path, symbol), mapped_tests in sorted(mappings.items()):
        definitions = [
            item
            for values in modules.values()
            for item in values
            if item.path == source_path and item.symbol == symbol
        ]
        if len(definitions) != 1:
            raise SourceCorpusV2Error("mapped production definition is not unique")
        definition = definitions[0]
        selected_test = min(mapped_tests, key=lambda item: (item.path, item.qualified_name))
        source_task, test_start, test_end = _node_text(
            selected_test.text, selected_test.node
        )
        operation_classes = operation_classes_v2(
            "\n".join((symbol, definition.text, source_task))
        )
        if operation_classes == ("OTHER",):
            excluded_rows.append(
                {
                    "source_file": source_path,
                    "source_symbol": symbol,
                    "reason": "NO_CONTROLLED_OPERATION_CLASS",
                }
            )
            continue
        implementation_sha256 = sha256_bytes(definition.text.encode("utf-8"))
        task_sha256 = sha256_bytes(source_task.encode("utf-8"))
        identity_body = {
            "tier": tier,
            "repository_url": repository_url,
            "repository_commit": repository_commit,
            "source_file": source_path,
            "source_symbol": symbol,
            "test_path": selected_test.path,
            "test_symbol": selected_test.qualified_name,
            "implementation_sha256": implementation_sha256,
            "source_task_sha256": task_sha256,
        }
        identity = stable_record_hash(identity_body)
        feature_record = source_feature_record(definition.text, source_task)
        feature_record["operation_class"] = list(operation_classes)
        candidate_rows.append(
            {
                "source_id": _source_id(repository_url, source_path, symbol, identity),
                "candidate_identity_sha256": identity,
                "tier": tier,
                "repository_url": repository_url,
                "repository_commit": repository_commit,
                "source_file": source_path,
                "source_symbol": symbol,
                "source_implementation_or_patch": definition.text,
                "source_implementation_sha256": implementation_sha256,
                "source_task_description": source_task,
                "source_task_sha256": task_sha256,
                "source_task_provenance": {
                    "kind": "UPSTREAM_TEST",
                    "path": selected_test.path,
                    "symbol": selected_test.qualified_name,
                    "line_start": test_start,
                    "line_end": test_end,
                    "sha256": task_sha256,
                },
                "additional_mapped_tests": [
                    {"path": item.path, "symbol": item.qualified_name}
                    for item in sorted(
                        mapped_tests, key=lambda item: (item.path, item.qualified_name)
                    )[1:]
                ],
                **feature_record,
                "mechanical_focal_safety_level": "C",
                "mechanical_pstar": _mechanical_pstar(
                    operation_class=operation_classes[0],
                    symbol=symbol,
                    test_name=selected_test.qualified_name,
                ),
                "candidate_generation_uses_target": False,
                "candidate_generation_uses_oracle": False,
                "candidate_generation_uses_model": False,
            }
        )

    ordered = sorted(
        candidate_rows,
        key=lambda item: (
            item["source_file"],
            item["source_symbol"],
            item["source_task_provenance"]["path"],
            item["source_task_provenance"]["symbol"],
        ),
    )
    deduplicated: list[dict[str, Any]] = []
    implementation_hashes: set[str] = set()
    for candidate in ordered:
        digest = candidate["source_implementation_sha256"]
        if digest in implementation_hashes:
            excluded_rows.append(
                {
                    "source_file": candidate["source_file"],
                    "source_symbol": candidate["source_symbol"],
                    "reason": "DUPLICATE_IMPLEMENTATION_SHA256",
                }
            )
            continue
        implementation_hashes.add(digest)
        deduplicated.append(candidate)
    return {
        "schema": "cmpilot-source-candidate-discovery-v2",
        "protocol_id": PROTOCOL_ID,
        "successor_protocol_commit": SUCCESSOR_PROTOCOL_COMMIT,
        "repository_url": repository_url,
        "repository_commit": repository_commit,
        "tier": tier,
        "python_file_count": file_count,
        "parsed_module_count": len(modules),
        "assertion_test_count": len(tests),
        "parse_failures": sorted(parse_failures, key=lambda item: item["path"]),
        "excluded": sorted(
            excluded_rows,
            key=lambda item: (item["source_file"], item["source_symbol"], item["reason"]),
        ),
        "candidate_count": len(deduplicated),
        "candidates": deduplicated,
        "discovery_sha256": stable_record_hash(deduplicated),
        "target_side_inputs": [],
    }


def round_robin_candidates(
    discoveries: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, Any], ...]:
    """Interleave repositories without observing qualification outcomes."""

    ordered_discoveries = sorted(
        discoveries,
        key=lambda item: (
            0 if item.get("tier") == "S1" else 1,
            str(item.get("repository_url")),
            str(item.get("repository_commit")),
        ),
    )
    queues = [deque(dict(row) for row in item.get("candidates", ())) for item in ordered_discoveries]
    result: list[dict[str, Any]] = []
    while any(queues):
        for queue in queues:
            if queue:
                result.append(queue.popleft())
    return tuple(result)


def choose_corpus_target(
    *,
    pilot_total_wall_seconds: float,
    pilot_qualified_count: int,
    materialization_gib: float,
    inherited_entries: int = INHERITED_V1_ENTRIES,
) -> dict[str, Any]:
    """Apply the frozen 50/100/200 resource-envelope decision."""

    if pilot_total_wall_seconds < 0 or pilot_qualified_count < 0 or materialization_gib < 0:
        raise SourceCorpusV2Error("pilot cost inputs cannot be negative")
    seconds_per_qualified = (
        float("inf")
        if pilot_qualified_count == 0
        else pilot_total_wall_seconds / pilot_qualified_count
    )
    projections = []
    for target in CORPUS_SIZE_CHOICES:
        increment = max(target - inherited_entries, 0)
        machine_hours = seconds_per_qualified * increment / 3600
        reviewer_hours = REVIEW_MINUTES_PER_QUALIFIED_ENTRY * increment / 60
        feasible = bool(
            machine_hours <= MACHINE_HOUR_CAP
            and reviewer_hours <= REVIEWER_HOUR_CAP
            and materialization_gib <= MATERIALIZATION_GIB_CAP
        )
        projections.append(
            {
                "target": target,
                "increment": increment,
                "projected_machine_hours": machine_hours,
                "projected_reviewer_hours": reviewer_hours,
                "materialization_gib": materialization_gib,
                "feasible": feasible,
            }
        )
    feasible_targets = [row["target"] for row in projections if row["feasible"]]
    selected = max(feasible_targets) if feasible_targets else 50
    return {
        "schema": "cmpilot-source-corpus-size-decision-v2",
        "pilot_new_attempts_required": PILOT_NEW_ATTEMPTS,
        "pilot_total_wall_seconds": pilot_total_wall_seconds,
        "pilot_qualified_count": pilot_qualified_count,
        "seconds_per_qualified": seconds_per_qualified,
        "projections": projections,
        "selected_target": selected,
        "resource_envelope_satisfied": bool(feasible_targets),
    }


def corpus_breadth(
    entries: Sequence[Mapping[str, Any]],
    *,
    minimum_repositories: int = 6,
    minimum_s2_repositories: int = 2,
    minimum_primary_operation_classes: int = 8,
) -> dict[str, Any]:
    repositories = {str(entry["repository_url"]) for entry in entries}
    s2_repositories = {
        str(entry["repository_url"])
        for entry in entries
        if entry.get("source_tier") == "S2" or entry.get("tier") == "S2"
    }
    primary_operations = {
        str(entry["operation_class"][0])
        for entry in entries
        if entry.get("operation_class")
    }
    checks = {
        "repositories": len(repositories) >= minimum_repositories,
        "s2_repositories": len(s2_repositories) >= minimum_s2_repositories,
        "primary_operation_classes": (
            len(primary_operations) >= minimum_primary_operation_classes
        ),
    }
    return {
        "repository_count": len(repositories),
        "s2_repository_count": len(s2_repositories),
        "primary_operation_class_count": len(primary_operations),
        "repositories": sorted(repositories),
        "s2_repositories": sorted(s2_repositories),
        "primary_operation_classes": sorted(primary_operations),
        "minimums": {
            "repositories": minimum_repositories,
            "s2_repositories": minimum_s2_repositories,
            "primary_operation_classes": minimum_primary_operation_classes,
        },
        "checks": checks,
        "pass": all(checks.values()),
    }


def source_universe_design(instance_ids: Iterable[str]) -> dict[str, Any]:
    s2 = build_s2_universe(instance_ids)
    return {
        "schema": "cmpilot-source-universe-design-v2",
        "protocol_id": PROTOCOL_ID,
        "successor_protocol_commit": SUCCESSOR_PROTOCOL_COMMIT,
        "susvibes_revision": SUSVIBES_REVISION,
        "susvibes_dataset_sha256": SUSVIBES_DATASET_SHA256,
        "target_independent": True,
        "s1_snapshot_count": 5,
        "s2_repository_anchor_count": len(s2),
        "s2_repository_count": len({item["repository_url"] for item in s2}),
        "s2_order_sha256": stable_record_hash(s2),
        "s2_entries": list(s2),
        "s3_enabled": False,
        "arbitrary_live_search": False,
        "source_only_partition_used": SOURCE_ONLY_PARTITION_USED,
        "unseen_task_fields_read": ["instance_id"],
    }
