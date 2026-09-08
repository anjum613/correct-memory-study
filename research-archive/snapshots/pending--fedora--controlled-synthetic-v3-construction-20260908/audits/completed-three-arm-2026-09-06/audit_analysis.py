"""Exploratory summaries of saved data; never execute evaluated code or tests.

All writes are derived audit files next to this script. The snapshot inventory
created by audit_extract.py is checked before analysis to detect local changes.
"""

import itertools
import json
import random
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from statistics import mean

from audit_extract import ARMS, HERE, REPO, SNAP, load, sha

FAMILIES = ["F01", "F02", "F04", "F08", "F17", "F20", "X02", "X05", "X06", "X11", "X20", "X24", "X28"]
CONDITIONS = ["N", "C", "I", "B"]
CONTRASTS = {"C-N": ("C", "N"), "I-N": ("I", "N"), "B-C": ("B", "C"), "B-N": ("B", "N")}
SYMBOL = {"SAFE_COMPLETION": "s", "UNSAFE_COMPLETION": "u", "INCOMPLETE_SECURITY_PASS": "p", "INCOMPLETE_SECURITY_FAIL": "f", "INVALID": "x"}
BOOTSTRAPS = 50000
RNG_SEED = 20260906
ACCOUNTING_FLAGS = ["Dev/X05/B/1", "Dev/X28/C/2", "Dev/X28/I/1", "Dev/X28/I/2"]


def paired_units(rows, a, b, metric="unsafe", reps=(1, 2)):
    """Complete family-within-model pairs; average seeds, never count as iid."""
    index = {(r["model"], r["family"], r["condition"], r["rep"]): r for r in rows}
    units = []
    for model in ARMS:
        for family in FAMILIES:
            ra = [index.get((model, family, a, rep)) for rep in reps]
            rb = [index.get((model, family, b, rep)) for rep in reps]
            if not all(r and r["valid"] for r in ra + rb):
                continue
            av, bv = mean(r[metric] for r in ra), mean(r[metric] for r in rb)
            units.append(dict(model=model, family=family, a=av, b=bv, delta=av-bv,
                              a_keys=[r["key"] for r in ra], b_keys=[r["key"] for r in rb]))
    return units


def quantile(values, fraction):
    ordered = sorted(values)
    position = fraction * (len(ordered) - 1)
    low = int(position)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (position-low) * (ordered[high]-ordered[low])


def exact_sign_flip(values):
    """Exploratory exchangeability diagnostic, not a population causal test."""
    nonzero = [v for v in values if v]
    observed = abs(sum(values))
    statistics = [abs(sum(s*v for s, v in zip(signs, nonzero)))
                  for signs in itertools.product((-1, 1), repeat=len(nonzero))]
    return sum(x >= observed-1e-12 for x in statistics) / len(statistics)


def describe_units(units, bootstrap=True):
    by_family = defaultdict(list)
    for u in units:
        by_family[u["family"]].append(u["delta"])
    point = mean(u["delta"] for u in units)
    # Cluster all models and both seeds by the same family on pooled estimates.
    clusters = [(sum(ds), len(ds)) for ds in by_family.values()]
    samples = []
    if bootstrap:
        rng = random.Random(RNG_SEED)
        for _ in range(BOOTSTRAPS):
            selected = rng.choices(clusters, k=len(clusters))
            samples.append(sum(x for x, _ in selected)/sum(n for _, n in selected))
    return dict(family_model_units=len(units), family_clusters=len(clusters), delta_pp=100*point,
                a_rate_pp=100*mean(u["a"] for u in units), b_rate_pp=100*mean(u["b"] for u in units),
                ci95_pp=[100*quantile(samples, q) for q in (.025, .975)] if samples else None,
                sign_flip_p=exact_sign_flip([sum(ds) for ds in by_family.values()]),
                family_direction_counts=dict(Counter("increase" if u["delta"] > 0 else "decrease" if u["delta"] < 0 else "unchanged" for u in units)),
                leave_one_family_out_pp={f:100*mean(u["delta"] for u in units if u["family"] != f) for f in by_family},
                units=units)


def validate_artifacts():
    errors, json_count, jsonl_count, jsonl_lines, raw_changes = [], 0, 0, 0, []
    for rec in load(HERE / "inventory.json"):
        p = HERE / rec["path"]
        if "sha256" in rec and (not p.is_file() or sha(p.read_bytes()) != rec["sha256"]):
            raw_changes.append(rec["path"])
        elif "symlink" in rec and (not p.is_symlink() or str(p.readlink()) != rec["symlink"]):
            raw_changes.append(rec["path"])
        if p.is_symlink() or p.suffix not in (".json", ".jsonl"):
            continue
        if p.suffix == ".json":
            json_count += 1
            try:
                load(p)
            except (ValueError, UnicodeError) as exc:
                errors.append(dict(path=rec["path"], error=str(exc)))
        else:
            jsonl_count += 1
            for line, text in enumerate(p.read_text().splitlines(), 1):
                if text.strip():
                    jsonl_lines += 1
                    try:
                        json.loads(text)
                    except ValueError as exc:
                        errors.append(dict(path=rec["path"], line=line, error=str(exc)))
    assert not raw_changes, raw_changes
    inventory = load(REPO / "synthetic_triplets/controlled_synthetic_final_13_v1/artifact_inventory.json")
    frozen_mismatches = []
    for name, expected in inventory["files"].items():
        p = REPO / name
        if not p.is_file() or sha(p.read_bytes()) != expected["sha256"]:
            frozen_mismatches.append(name)
    bindings = {b["family_id"]:b for b in load(REPO/"protocols/controlled-synthetic-final-13-experiment-v1/evaluation_bindings.json")["families"]}
    condition_names = dict(zip(CONDITIONS, ["NO_MEMORY", "SOURCE_CORRECT_MEMORY", "MATCHED_IRRELEVANT_MEMORY", "SOURCE_MEMORY_PLUS_APPLICABILITY_BOUNDARY"]))
    message_mismatches, source_attestation_failures = [], []
    for r in load(HERE/"runs.json"):
        dr = Path(r["local_dir"])
        expected = bindings[r["family"]]["messages_sha256"][condition_names[r["condition"]]]
        if sha((dr/"frozen-messages.json").read_bytes()) != expected:
            message_mismatches.append(r["key"])
        if not load(dr/"mini-swe-source-manifest.json")["all_match"]:
            source_attestation_failures.append(r["key"])
    return dict(json_files=json_count, jsonl_files=jsonl_count, jsonl_records=jsonl_lines,
                parse_errors=errors, local_snapshot_changes=raw_changes, frozen_inventory_count=inventory["file_count"],
                frozen_local_mismatches=frozen_mismatches, frozen_message_file_hash_mismatches=message_mismatches,
                mini_swe_source_attestation_failures=source_attestation_failures)


def ngrams(text, n=8):
    tokens = re.findall(r"[a-z0-9_]+", text.lower())
    return {tuple(tokens[i:i+n]) for i in range(len(tokens)-n+1)}


def memory_phrase_screen(rows):
    """Exploratory candidate retrieval, NOT the frozen behavioral codebook.

    Match exact eight-token sequences in provided memory, excluding sequences
    present in target instructions or initial visible files. Absence is not
    evidence of ignoring memory; matches are not causal mediation evidence.
    """
    transcripts = {t["key"]:t for t in load(HERE / "transcripts.json")}
    candidates = []
    for r in rows:
        dr = Path(r["local_dir"])
        user = next(x["content"] for x in load(dr/"frozen-messages.json") if x["role"] == "user")
        if "[BEGIN_MEMORY_CONTEXT]" not in user:
            continue
        memory = user.split("[BEGIN_MEMORY_CONTEXT]")[1].split("[END_MEMORY_CONTEXT]")[0].split("[NEUTRAL_PADDING]")[0]
        memory = memory.split("Before reusing the procedure,")[0]
        nonmemory = user.split("[BEGIN_MEMORY_CONTEXT]")[0]
        for p in (dr/"initial-repository").rglob("*"):
            if p.is_file() and not p.is_symlink() and ".git" not in p.parts and p.suffix in (".py", ".csirpy", ".md"):
                nonmemory += "\n" + p.read_text()
        memory_grams = ngrams(memory) - ngrams(nonmemory)
        for msg in transcripts[r["key"]]["messages"]:
            if msg["role"] != "assistant":
                continue
            for kind, text in [("recorded_content", msg["content"]), ("tool_arguments", json.dumps(msg["tool_calls"] or msg["actions"] or ""))]:
                shared = memory_grams & ngrams(text)
                if shared:
                    candidates.append(dict(key=r["key"], message_index=msg["index"], kind=kind,
                                            matched_8grams=[" ".join(g) for g in sorted(shared)],
                                            transcript=str((dr/"trajectory.json").relative_to(HERE))))
    (HERE/"memory-phrase-candidates.json").write_text(json.dumps(candidates, indent=2)+"\n")
    return dict(method="exploratory eight-token exact match; subtract initial visible files and task; excludes boundary/padding",
                candidate_runs=len({c["key"] for c in candidates}), candidate_messages=len({(c["key"],c["message_index"]) for c in candidates}),
                keys=sorted({c["key"] for c in candidates}), file="memory-phrase-candidates.json")


def log_census():
    records = []
    paths = list(SNAP.rglob("*.log")) + list(SNAP.rglob("agent-stderr.txt")) + list(SNAP.rglob("agent-stdout.txt")) + list((HERE/"scheduler-logs").glob("*.out"))
    pattern = re.compile(r"traceback|exception|\berror\b|warning|out.of.memory|\boom\b|timed.out|cancelled", re.I)
    for p in sorted(paths):
        text = p.read_text(errors="replace")
        matches = [i for i, line in enumerate(text.splitlines(), 1) if pattern.search(line)]
        records.append(dict(file=str(p.relative_to(HERE)), bytes=p.stat().st_size, lines=len(text.splitlines()),
                            diagnostic_candidate_lines=matches))
    (HERE/"log-index.json").write_text(json.dumps(records, indent=2)+"\n")
    return dict(files=len(records), nonempty=sum(r["bytes"] > 0 for r in records),
                candidate_files=sum(bool(r["diagnostic_candidate_lines"]) for r in records), file="log-index.json")


def historical_census():
    groups = []
    for root in sorted((HERE / "historical").iterdir()):
        if not root.is_dir() or "codex" in root.name or root.name in ARMS.values():
            continue
        results, parse_errors = [], []
        for p in root.glob("*/result.json"):
            try:
                d = load(p)
                results.append(dict(file=str(p.relative_to(HERE)), status=d.get("status"),
                                    technical_valid=d.get("technical_valid"), cell=d.get("cell"),
                                    error=d.get("error"), termination=(d.get("trajectory_metrics") or {}).get("termination_reason")))
            except ValueError as exc:
                parse_errors.append(dict(file=str(p.relative_to(HERE)), error=str(exc), bytes=p.stat().st_size))
        groups.append(dict(root=root.name, result_count=len(results),
                           statuses=dict(Counter(str(r["status"]) for r in results)),
                           results=results, parse_errors=parse_errors))
    return groups


def missing_bounds(rows, a, b):
    """Worst-case bounds, not imputation; original outcomes remain unchanged."""
    av, bv = [r for r in rows if r["condition"] == a], [r for r in rows if r["condition"] == b]
    assert len(av) == len(bv) == 26
    sa, sb = sum(r["unsafe"] for r in av if r["valid"]), sum(r["unsafe"] for r in bv if r["valid"])
    ma, mb = sum(not r["valid"] for r in av), sum(not r["valid"] for r in bv)
    return dict(unknown_a=ma, unknown_b=mb, lower_pp=100*(sa-sb-mb)/26, upper_pp=100*(sa+ma-sb)/26)


def analyse():
    rows = load(HERE / "runs.json")
    index = {r["key"]: r for r in rows}
    transcripts = {t["key"]:t for t in load(HERE/"transcripts.json")}
    events = load(HERE/"events.json")
    output = {"method": dict(exploratory=True, bootstraps=BOOTSTRAPS, rng_seed=RNG_SEED,
                              inference_unit="family within model, repetitions averaged; pooled bootstrap clusters by family",
                              original_scores_preserved=True, evaluated_code_executed=False),
              "artifact_validation": validate_artifacts(), "contrasts": {}, "metrics_primary": {},
              "common_12_primary": {}, "seed_primary": {}, "seed_agreement": {}, "missing_bounds": {},
              "transitions_primary": {}, "process": {}, "models": {}, "invalids": [],
              "historical": historical_census(), "accounting_flags": ACCOUNTING_FLAGS}
    output["memory_phrase_screen"] = memory_phrase_screen(rows)
    output["log_census"] = log_census()
    for label, (a, b) in CONTRASTS.items():
        units = paired_units(rows, a, b)
        output["contrasts"][label] = {"pooled_descriptive": describe_units(units)}
        for model in ARMS:
            output["contrasts"][label][model] = describe_units([u for u in units if u["model"] == model])
    for model, root_name in ARMS.items():
        rr = [r for r in rows if r["model"] == model]
        batch = load(SNAP / root_name / "batch.json")
        elapsed = datetime.fromisoformat(batch["finished_at_utc"])-datetime.fromisoformat(batch["started_at_utc"])
        output["models"][model] = dict(model_id=batch["model_id"], revision=batch["model_revision"],
                                        start=batch["started_at_utc"], finish=batch["finished_at_utc"],
                                        elapsed_seconds=elapsed.total_seconds(), concurrency=batch["concurrency"],
                                        batch_file=str((SNAP/root_name/"batch.json").relative_to(HERE)))
        output["metrics_primary"][model] = {metric: describe_units([u for u in paired_units(rr, "C", "N", metric) if u["model"] == model], bootstrap=False)
                                             for metric in ["unsafe", "safe", "fun", "sec"]}
        output["common_12_primary"][model] = describe_units([u for u in paired_units(rr, "C", "N") if u["family"] != "X02"], bootstrap=False)
        output["seed_primary"][model] = {str(rep): describe_units(paired_units(rr, "C", "N", reps=(rep,)), bootstrap=False) for rep in [1, 2]}
        pairs = [(index[f"{model}/{f}/{c}/1"], index[f"{model}/{f}/{c}/2"]) for f in FAMILIES for c in CONDITIONS]
        pairs = [(x, y) for x, y in pairs if x["valid"] and y["valid"]]
        output["seed_agreement"][model] = dict(complete_pairs=len(pairs),
                                               outcomes_disagree=sum(x["outcome"] != y["outcome"] for x, y in pairs),
                                               unsafe_disagree=sum(x["unsafe"] != y["unsafe"] for x, y in pairs),
                                               disagreement_keys=[[x["key"], y["key"]] for x, y in pairs if x["outcome"] != y["outcome"]])
        output["missing_bounds"][model] = {label: missing_bounds(rr, a, b) for label, (a, b) in CONTRASTS.items()}
        transitions = defaultdict(list)
        for u in paired_units(rr, "C", "N"):
            for ak, bk in zip(u["a_keys"], u["b_keys"]):
                transitions[index[bk]["outcome"] + " -> " + index[ak]["outcome"]].append([bk, ak])
        output["transitions_primary"][model] = {k:dict(count=len(v), pairs=v) for k, v in transitions.items()}
        terminations = {}
        for term in sorted({r["termination"] for r in rr}):
            group = [r for r in rr if r["termination"] == term]
            terminations[term] = dict(n=len(group), outcomes=dict(Counter(r["outcome"] for r in group)), keys=[r["key"] for r in group])
        configs = Counter()
        for r in rr:
            for cfg, n in r["request_configs"].items():
                d = json.loads(cfg)
                d.pop("seed", None)
                configs[json.dumps(d, sort_keys=True)] += n
        policy_events = [e for e in events if e["key"].startswith(model+"/") and e["event"]["event"] == "ACTION_POLICY_VIOLATION"]
        first_action_testbed = []
        for r in rr:
            m = next(x for x in transcripts[r["key"]]["messages"] if x["role"] == "assistant")
            if "/testbed" in json.dumps(m["tool_calls"] or m["actions"] or m["content"]):
                first_action_testbed.append(r["key"])
        output["process"][model] = dict(terminations=terminations,
                                         no_final_change=[r["key"] for r in rr if r["no_final_change"]],
                                         max_prompt_tokens=max(r["max_prompt_tokens"] for r in rr),
                                         completion_limits=sorted({r["min_completion_limit"] for r in rr}),
                                         length_finish_runs=[r["key"] for r in rr if r["finish_reasons"].get("length")],
                                         configs=dict(configs),
                                         policy_rules=dict(Counter(e["event"]["matched_rule"] for e in policy_events)),
                                         testbed_policy_events=sum("/testbed" in e["event"].get("prohibited_command", "") for e in policy_events),
                                         first_action_testbed=first_action_testbed,
                                         elided_tool_observations=[dict(key=r["key"], message_index=m["index"])
                                                                  for r in rr for m in transcripts[r["key"]]["messages"]
                                                                  if m["role"] == "tool" and "<elided_chars>" in m["content"]],
                                         final_public_vs_function_contradictions=[r["key"] for r in rr if r["last_public_pass"] is True and r["valid"] and not r["fun"]])
    for r in rows:
        if not r["valid"]:
            error = r["evaluator"]["checks"]["existing"]["transport"]["stderr"].splitlines()[-1]
            output["invalids"].append(dict(key=r["key"], run_id=r["run_id"], error=error,
                                            file=str((Path(r["local_dir"])/"evaluation.json").relative_to(HERE))))
    (HERE/"robustness.json").write_text(json.dumps(output, indent=2)+"\n")
    markdown = ["# Complete run evidence ledger", "", "Original saved scores; no post-hoc rescoring. Message indices use trajectory.json messages[0..].", "",
                "Models: Next = Qwen3-Coder-Next-FP8; Q30 = Qwen3-Coder-30B-A3B-Instruct-FP8; Dev = Devstral-Small-2507.", "",
                "Conditions: N = no memory; C = source-correct; I = matched irrelevant; B = correct plus applicability boundary.", "",
                "Codes: s = functionality + focal-security pass; u = unsafe completion; p = incomplete/security pass; f = incomplete/security fail; x = technical invalid.", "",
                "## Full family matrix", "", "Each two-character entry gives repetitions 1, 2. Security passes are recorded witness outcomes, not general security guarantees.", "",
                "| Family | Model | N | C | I | B |", "|---|---|---|---|---|---|"]
    for f in FAMILIES:
        for m in ARMS:
            states = ["".join(SYMBOL[index[f"{m}/{f}/{c}/{rep}"]["outcome"]] for rep in (1, 2)) for c in CONDITIONS]
            markdown.append("| " + " | ".join([f, m]+states) + " |")
    markdown += ["", "## Per-run original evidence", "", "Authoritative HPC prefix: `/home/s224049759/projects/final-experiment-runs/`. Each linked local snapshot retains the corresponding arm directory and run ID.", ""]
    for f in FAMILIES:
        markdown += [f"### {f}", "", "| Key | Run ID | Outcome | Requests / commands | Termination | Original files |", "|---|---|---|---:|---|---|"]
        for m in ARMS:
            for c in CONDITIONS:
                for rep in (1, 2):
                    r = index[f"{m}/{f}/{c}/{rep}"]
                    path = Path(r["local_dir"]).relative_to(HERE).as_posix()
                    links = " · ".join(f"[{label}]({path}/{name})" for label, name in [("result", "result.json"), ("evaluation", "evaluation.json"), ("transcript", "trajectory.json"), ("patch", "final.patch"), ("events", "adapter-events.jsonl"), ("commands", "patch-history.jsonl"), ("requests", "model-transport.jsonl"), ("prompt", "frozen-messages.json")])
                    marker = " †" if r["key"] in ACCOUNTING_FLAGS else ""
                    markdown.append(f"| {r['key']}{marker} | `{r['run_id']}` | {SYMBOL[r['outcome']]} | {r['requests']} / {r['commands']} | {r['termination']} | {links} |")
        markdown.append("")
    markdown += ["† Static audit flags an unobserved accounting-dependent security outcome. This flag does not alter the original score.", ""]
    (HERE/"run-ledger.md").write_text("\n".join(markdown))
    print("VALIDATION", json.dumps(output["artifact_validation"]))
    for label, values in output["contrasts"].items():
        print("CONTRAST", label, {m:{k:v[k] for k in ["family_model_units", "delta_pp", "ci95_pp", "sign_flip_p"]} for m,v in values.items()})
    print("SEED AGREEMENT", {m:{k:v for k,v in d.items() if k != "disagreement_keys"} for m,d in output["seed_agreement"].items()})
    print("PRIMARY METRICS", {m:{k:(v["b_rate_pp"], v["a_rate_pp"], v["delta_pp"]) for k,v in d.items()} for m,d in output["metrics_primary"].items()})


if __name__ == "__main__":
    analyse()
