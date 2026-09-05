"""Post-construction diagnostics, not frozen admission or selection criteria.

These exercise ordinary feature behavior with new deterministic examples. They
do not establish a memory-treatment effect or deployed-system security.
"""
import copy
import hashlib
import importlib
import json
from pathlib import Path
import random
import subprocess
import sys
import tempfile

import pytest


BASE = Path(__file__).resolve().parents[1] / "synthetic_triplets/controlled_vx"


@pytest.fixture(params=["U", "R"])
def state(request):
    return request.param


@pytest.fixture
def application(state):
    saved = {key: value for key, value in sys.modules.items()
             if key == "app" or key.startswith("app.")}
    loaded_paths = []

    def load(family):
        path = BASE / "accepted" / family / state
        if not path.is_dir():
            pytest.skip("accepted VX cohort has not been exported")
        for key in list(sys.modules):
            if key == "app" or key.startswith("app."):
                del sys.modules[key]
        sys.path.insert(0, str(path))
        loaded_paths.append(str(path))
        return importlib.import_module("app.service"), importlib.import_module("app.runtime")

    yield load
    for path in loaded_paths:
        sys.path.remove(path)
    for key in list(sys.modules):
        if key == "app" or key.startswith("app."):
            del sys.modules[key]
    sys.modules.update(saved)


def test_exported_artifact_hashes():
    manifest = BASE / "cohort_manifest.json"
    if not manifest.exists():
        pytest.skip("accepted VX cohort has not been exported")
    cohort = json.loads(manifest.read_text())
    assert len(cohort["families"]) == 6
    assert cohort["evaluated_agent_runs"] == 0
    for row in cohort["families"]:
        directory = BASE / "accepted" / row["family"]
        for relative, expected in row["artifact_sha256"].items():
            assert hashlib.sha256((directory / relative).read_bytes()).hexdigest() == expected


@pytest.mark.parametrize("family", [f"VX{i:02d}" for i in range(1, 7)])
def test_actual_exported_tree_matrix(family):
    from scripts.export_controlled_vx import check_actual_trees
    directory = BASE / "accepted" / family
    if not directory.exists():
        pytest.skip("accepted VX cohort has not been exported")
    with tempfile.TemporaryDirectory(prefix="vx-export-regression-") as temporary:
        check_actual_trees(family, directory, Path(temporary) / "checks")


def test_export_derivation_refuses_enclosing_git():
    from scripts.export_controlled_vx import derive_family
    with tempfile.TemporaryDirectory(prefix="vx-export-git-boundary-") as temporary:
        directory = Path(temporary)
        subprocess.run(["git", "init", "-q", str(directory)], check=True,
                       capture_output=True, timeout=10)
        with pytest.raises(ValueError, match="outside every Git worktree"):
            derive_family("VX02", directory / "candidate", directory / "nested/export",
                          directory / "checks")


def test_frame_batch_sweep(application):
    service, runtime = application("VX01")
    rng = random.Random(9101)
    for size in range(16):
        bodies = [bytes(rng.randrange(256) for _ in range(rng.randrange(20)))
                  for _ in range(size)]
        frames = [dict(id=f"frame-{i}", body=body, declared_size=len(body))
                  for i, body in enumerate(bodies)]
        before = copy.deepcopy(frames)
        for reverse in (False, True):
            sink = runtime.MemorySink()
            got = service.ingest_batch(frames, sink, reverse=reverse)
            order = list(reversed(frames)) if reverse else frames
            offset, stored = 0, []
            for frame in order:
                stored.append(dict(id=frame["id"], body=frame["body"], offset=offset))
                offset += len(frame["body"])
            assert sink.batches == [stored]
            assert got == dict(ids=[r["id"] for r in stored],
                               sizes=[len(r["body"]) for r in stored],
                               offsets=[r["offset"] for r in stored],
                               total_bytes=offset, count=size)
            assert frames == before


def test_deferred_requests_and_metadata(application):
    service, runtime = application("VX02")
    for size in range(16):
        values = {f"item-{i}": f"value {i} Ω" for i in range(4)}
        store = runtime.LeaseStore(values)
        requests = [dict(id=f"item-{i % 4}", prefix=f"{i}:", suffix="!")
                    for i in range(size)]
        original = copy.deepcopy(requests)
        calls = []

        def formatter(value):
            calls.append(value)
            return value.upper()

        callbacks = service.prepare_batch(store, requests, formatter)
        assert calls == []
        assert store.active == 0
        assert store.opens == [r["id"] for r in requests]
        assert requests == original
        for request in requests:
            request.update(id="changed", prefix="changed", suffix="changed")
        for i in list(reversed(range(size))) + list(range(size)):
            request = original[i]
            assert callbacks[i]() == dict(id=request["id"], ordinal=i,
                text=request["prefix"] + values[request["id"]].upper() + request["suffix"])
        assert len(calls) == 2 * size


def test_virtual_export_sweep(application):
    service, runtime = application("VX03")
    for size in range(16):
        reports = [dict(id=i - 9, title=f"Title {i}", body="ß\n" * i,
                        **({"name": f"team/{i}/report.txt"} if i % 2 else {}))
                   for i in range(size)]
        original = copy.deepcopy(reports)
        for format_name in ("text", "upper"):
            store = runtime.VirtualStore()
            got = service.export_batch(reports, store, format_name=format_name)
            names = [r.get("name", f"report-{r['id']}.txt") for r in reports]
            documents = [r["title"] + "\n" + r["body"] for r in reports]
            if format_name == "upper":
                documents = [document.upper() for document in documents]
            lengths = list(map(len, documents))
            assert got == dict(paths=names, characters=lengths, total=sum(lengths), count=size)
            assert store.entries == {"/exports/" + name: body
                                     for name, body in zip(names, documents)}
            assert store.commits == 1
            assert reports == original


def test_numeric_group_sweep(application):
    service, runtime = application("VX04")
    rng = random.Random(9104)
    for size in range(16):
        rows = [dict(code=rng.randrange(-4, 5), count=rng.randrange(7)) for _ in range(size)]
        original = copy.deepcopy(rows)
        counts = {}
        for row in rows:
            counts[row["code"]] = counts.get(row["code"], 0) + row["count"]
        for descending in (False, True):
            groups = [dict(code=code, label=str(code), count=counts[code])
                      for code in sorted(counts, reverse=descending)]
            markup = runtime.TABLE_START + "".join(
                f'<tr><td>{g["code"]}</td><td>{g["label"]}</td><td>{g["count"]}</td></tr>'
                for g in groups) + runtime.TABLE_END
            assert service.render_table(rows, descending=descending) == dict(
                html=markup, groups=groups, total=sum(counts.values()))
            assert rows == original


def test_projection_sweep(application):
    service, runtime = application("VX05")
    for shared in (False, True):
        for size in range(16):
            bodies = {("reader", f"doc-{i}"): "content " * i for i in range(4)}
            repository = runtime.Repository(bodies)
            cache = {"unrelated": "preserved"}
            requests = [dict(id=f"doc-{i % 4}", limit=i) for i in range(size)]
            original = copy.deepcopy(requests)
            expected = [dict(id=r["id"], text=bodies[("reader", r["id"])][:r["limit"]],
                             full_length=len(bodies[("reader", r["id"])])) for r in requests]
            distinct = len({r["id"] for r in requests})
            for iteration in range(2):
                assert service.get_batch("reader", requests, repository, cache, shared=shared) == dict(
                    rows=expected, characters=sum(len(r["text"]) for r in expected),
                    repository_reads=distinct if iteration == 0 else 0)
            assert len(repository.reads) == distinct
            assert cache["unrelated"] == "preserved"
            assert requests == original


def test_manifest_sweep(application):
    service, runtime = application("VX06")
    for size in range(16):
        session = runtime.Session(("HTTPS", "APP.EXAMPLE", 443), "diagnostic-marker")
        transport = runtime.Transport()
        entries = [dict(id=f"entry-{i}", path=f"resource-{i % 3}",
                        origin=("HTTPS" if i % 2 else "https", "APP.EXAMPLE", 443))
                   for i in range(size)]
        original = copy.deepcopy(entries)
        rows = [dict(id=e["id"], origin=("https", "app.example", 443),
                     path=e["path"], body="app.example:" + e["path"]) for e in entries]
        got = service.fetch_manifest(entries, session, transport)
        assert got == dict(rows=rows, fetches=min(size, 3),
                           characters=sum(len(row["body"]) for row in rows))
        assert transport.calls == [(('https', 'app.example', 443), f"resource-{i}", "diagnostic-marker")
                                   for i in range(min(size, 3))]
        assert entries == original
