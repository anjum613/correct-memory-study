"""Render manually inspected case annotations with exact original-file links."""

from pathlib import Path

from audit_extract import HERE, load


def validate_annotations():
    rows = {r["key"]:r for r in load(HERE/"runs.json")}
    ts = {t["key"]:t for t in load(HERE/"transcripts.json")}
    cases = load(HERE/"case_annotations.json")
    for case in cases:
        for ref in case["runs"]:
            t = ts[ref["key"]]
            assert t["run_id"] == rows[ref["key"]]["run_id"]
            for i in ref["messages"]:
                assert 0 <= i < len(t["messages"])
            for q in ref.get("quotes", []):
                assert q["text"] in t["messages"][q["index"]]["content"], (case["id"], ref["key"], q)
    return rows, ts, cases


def render():
    rows, _, cases = validate_annotations()
    out = ["# Transcript and evaluator casebook", "", "Exploratory, outcome-aware close reading. No claim of blinded coding, exhaustive manual reading, causal mediation, or deliberate evaluator gaming. All excerpts are verified against the saved transcript. Full original traces remain linked; mN means `trajectory.json` → `messages[N]` (zero-based).", ""]
    for case in cases:
        out += [f"## {case['id']}", "", f"### {case['title']}", "", case["scope"], "", case["note"], ""]
        for ref in case["runs"]:
            r = rows[ref["key"]]
            p = Path(r["local_dir"]).relative_to(HERE).as_posix()
            out += [f"**{r['key']} — `{r['run_id']}`**", "", f"Recorded outcome: `{r['outcome']}`; termination: `{r['termination']}`.", ""]
            if ref["messages"]:
                out += ["Relevant message indices: " + ", ".join(f"m{i}" for i in ref["messages"]) + ".", ""]
            out += [" · ".join(f"[{label}]({p}/{file})" for label, file in [("Full transcript", "trajectory.json"), ("Final patch", "final.patch"), ("Evaluator", "evaluation.json"), ("Run result", "result.json"), ("Frozen prompt", "frozen-messages.json"), ("Command history", "patch-history.jsonl"), ("Adapter events", "adapter-events.jsonl")]), ""]
            for q in ref.get("quotes", []):
                out += [f"m{q['index']}:", "", "> " + q["text"], ""]
    (HERE/"casebook.md").write_text("\n".join(out))
    print(f"Rendered {len(cases)} case cards; checked all message indices and exact quotations.")


if __name__ == "__main__":
    render()
