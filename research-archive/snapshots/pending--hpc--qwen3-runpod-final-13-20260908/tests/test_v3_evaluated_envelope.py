"""Information-flow tests only: no constructor, model or human review is invoked."""
from __future__ import annotations

import ast
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from scripts import v3_evaluated_envelope as e

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT / e.DIRECTORY


def load(name):
    return json.loads((DIRECTORY / name).read_text())


def manifest_hash():
    return e.digest((DIRECTORY / "contract_manifest.json").read_bytes())


def packet_semantics(rendered):
    return rendered.split("\n\n[NEUTRAL_PADDING]", 1)[0]


def dummy_service(family):
    # File-boundary test bytes, not a constructed/scientifically validated candidate.
    return b"def boot():\n    return 0\n" if family == "X02" else b"def run(*args, **kwargs):\n    return None\n"


def context(family="X01", condition="NO_MEMORY"):
    data = dummy_service(family)
    return e.load_bound_context(ROOT, family, condition, data,
        expected_b_sha256=e.digest(data), expected_contract_sha256=manifest_hash())


def broker(family="X01"):
    _messages, files = context(family)
    index = load("export_index.json")[family]
    return e.FileTools(files, expected_public_hashes=index["public_files"],
        service_path=index["service_path"], expected_b_sha256=e.digest(dummy_service(family)), family=family)


def test_scientific_release_and_contract_unchanged():
    result = e.verify_contract(ROOT, expected_manifest_sha256=manifest_hash())
    assert result["scientific_release_commit"] == e.RELEASE_COMMIT
    assert result["constructor_attempts"] == result["evaluated_agent_outcomes"] == result["actual_v3_human_reviews"] == 0


def test_generation_is_exact_and_reproducible():
    generated = e.generate_contract(ROOT)
    for relative, data in generated.items():
        assert (DIRECTORY / relative).read_bytes() == data, relative


@pytest.mark.parametrize("family", e.IN_SCOPE)
def test_four_conditions_exact_isolation_and_boundary(family):
    index = load("export_index.json")[family]
    packets = load("memory_packets.json")
    target = (DIRECTORY / f"exports/{family}/target_request.txt").read_text()
    messages = {c: e.render_messages(family, c, target, packets) for c in e.CONDITIONS}
    for condition, message in messages.items():
        assert [m["role"] for m in message] == ["system", "user"]
        assert message[0] == {"role": "system", "content": e.SYSTEM}
        assert e.digest(e.canonical(message)) == index["messages_sha256"][condition]
        assert message[1]["content"].startswith(target)
        assert condition not in message[1]["content"]
    assert messages["NO_MEMORY"][1]["content"] == target
    relevant = e.render_memory(packets[family], boundary=False)
    boundary = e.render_memory(packets[family], boundary=True)
    assert packet_semantics(boundary) == packet_semantics(relevant) + "\n\n" + e.BOUNDARY
    assert boundary.count(e.BOUNDARY) == 1
    assert e.BOUNDARY not in relevant
    irrelevant = e.render_memory(packets[e.IRRELEVANT_PAIRING[family]], boundary=False)
    assert len(relevant.encode()) == len(boundary.encode()) == len(irrelevant.encode()) == 4096
    assert messages[e.CONDITIONS[1]][1]["content"] == target + "\n" + relevant
    assert messages[e.CONDITIONS[2]][1]["content"] == target + "\n" + irrelevant
    assert messages[e.CONDITIONS[3]][1]["content"] == target + "\n" + boundary


@pytest.mark.parametrize("family", e.IN_SCOPE)
def test_source_packet_and_task_are_positive_projections(family):
    specs = {s["family_id"]: s for s in json.loads((ROOT / e.SPEC_FILE).read_text())["specifications"]}
    spec = specs[family]
    packet = load("memory_packets.json")[family]
    assert packet == {"schema": "v3-source-procedure-packet/1", "procedure": spec["source_procedure"],
                      "source_valid_reason": spec["source_valid_assumption"]}
    target = (DIRECTORY / f"exports/{family}/target_request.txt").read_text()
    assert spec["requested_feature"] in target
    noisy_spec = {**spec, **{key: "FORBIDDEN_RESEARCHER_SENTINEL" for key in e.FORBIDDEN_FIELDS}}
    assert e.target_task(noisy_spec, family) == target
    for condition in e.CONDITIONS:
        visible = str(e.render_messages(family, condition, target, load("memory_packets.json")))
        for field in ("target_change", "unsafe_reuse", "secure_adaptation"):
            assert field not in visible
            assert spec[field] not in visible
        assert "FORBIDDEN_RESEARCHER_SENTINEL" not in visible
    assert spec["source_valid_assumption"] not in target


@pytest.mark.parametrize("family", e.IN_SCOPE)
def test_export_contains_only_same_family_public_code(family):
    index = load("export_index.json")[family]
    root = DIRECTORY / f"exports/{family}/repository"
    names = {str(p.relative_to(root)) for p in root.rglob("*") if p.is_file()}
    assert names == set(index["public_files"])
    for name in names:
        e.safe_path(name)
        data = (root / name).read_bytes()
        assert e.digest(data) == index["public_files"][name]
        if name.endswith('.py'):
            tree = ast.parse(data)
            for n in ast.walk(tree):
                if isinstance(n, (ast.FunctionDef, ast.ClassDef)):
                    assert not n.name.endswith(("_source", "_base", "_repair", "_target_invariant"))
                    for other in e.IN_SCOPE:
                        if other != family:
                            assert not n.name.lower().startswith(other.lower())
    assert not any(name.endswith(("task.json", "feature.patch", "security.patch")) for name in names)
    assert "app/service.py" not in names and "app/service.csirpy" not in names
    if family in e.CRYPTO_SYMBOLS:
        vectors = json.loads((root / "fixture_api/public_vectors.json").read_text())
        assert set(vectors) == ({"rsa_public", "payloads", "x22"} if family == "X22" else
                                {"ed25519_public_hex", family.lower()})


@pytest.mark.parametrize("family", e.IN_SCOPE)
def test_public_function_and_fixture_bodies_unchanged(family):
    shared = ROOT / e.RELEASE / "agent_inputs/shared"
    test_origin = "public_crypto.py" if family in e.CRYPTO_SYMBOLS else "x02_public.py" if family == "X02" else "public_suite.py"
    sources = [shared / test_origin, shared / "public_harness.py", shared / "contracts.py"]
    if family in e.RUNTIME_SYMBOLS:
        sources += [shared / "agent_runtime.py"]
    elif family in e.CRYPTO_SYMBOLS:
        sources += [shared / "agent_crypto.py"]
    else:
        sources += [shared / "x02_lowering.py", shared / "x02_machine.py", ROOT / e.RELEASE / "x02_oracle.py"]
    originals = {}
    for source in sources:
        for n in ast.parse(source.read_text()).body:
            if isinstance(n, (ast.FunctionDef, ast.ClassDef)):
                originals[n.name] = ast.dump(n, include_attributes=False)
    for output in (DIRECTORY / f"exports/{family}/repository").rglob('*.py'):
        for n in ast.parse(output.read_text()).body:
            if isinstance(n, (ast.FunctionDef, ast.ClassDef)):
                assert originals[n.name] == ast.dump(n, include_attributes=False)


def test_irrelevant_control_is_complete_fixed_derangement():
    pairing = load("irrelevant_pairing.json")
    assert pairing == e.IRRELEVANT_PAIRING
    assert set(pairing) == set(pairing.values()) == set(e.IN_SCOPE)
    specs = {s['family_id']: s for s in json.loads((ROOT / e.SPEC_FILE).read_text())["specifications"]}
    for family, source in pairing.items():
        assert family != source and pairing[source] == family
        assert specs[family]['mechanism'] != specs[source]['mechanism']
        assert specs[family]['source_procedure'] != specs[source]['source_procedure']


@pytest.mark.parametrize('field', sorted(e.FORBIDDEN_FIELDS | {'source_valid_assumption', 'extra'}))
def test_packet_rejects_extra_fields(field):
    packet = dict(load('memory_packets.json')['X01'])
    packet[field] = 'forbidden content'
    with pytest.raises(e.EnvelopeError):
        e.render_memory(packet, boundary=False)


@pytest.mark.parametrize('value', ['a\n' + e.BOUNDARY, '[END_MEMORY_CONTEXT]', 'a' * 1025, '', None])
def test_packet_rejects_delimiter_boundary_and_bound_spoofing(value):
    packet = dict(load('memory_packets.json')['X01'])
    packet['procedure'] = value
    with pytest.raises(e.EnvelopeError):
        e.render_memory(packet, boundary=False)


@pytest.mark.parametrize('path', ['../task.json', '/etc/passwd', 'fixture_api/../../sealed/test.py',
    '.git/config', 'researcher_tests/witness.py', 'feature.patch', 'security.patch',
    'fixture_api//runtime.py', 'fixture_api/./runtime.py', 'fixture_api\\runtime.py',
    'fixture_api/missing.py', 'task.json', '.env', 'proc/self/environ'])
def test_tool_cannot_read_forbidden_or_unexported_paths(path):
    with pytest.raises(e.EnvelopeError):
        broker().read_file(path)


@pytest.mark.parametrize('operation,arguments', [('shell', {'cmd': 'pwd'}), ('git', {}),
    ('network', {}), ('run_public_tests', {'selector': 'sealed'}),
    ('read_file', {'path': 'AGENTS.md', 'host': True}), ('list_files', {'root': '/'}),
    ('run_public_tests', {})])
def test_unapproved_tools_and_execution_are_disabled(operation, arguments):
    with pytest.raises(e.EnvelopeError):
        broker().dispatch(operation, arguments)


def test_public_files_readonly_and_service_edit_digest_checked():
    tool = broker()
    with pytest.raises(e.EnvelopeError):
        tool.edit_service('public_tests.py', e.digest(tool.read_file('public_tests.py').encode()), b'changed')
    with pytest.raises(e.EnvelopeError):
        tool.edit_service('app/service.py', '0' * 64, b'def run(): return None\n')
    new = b'def run(*args, **kwargs):\n    return False\n'
    result = tool.edit_service('app/service.py', e.digest(dummy_service('X01')), new)
    assert result == {'sha256': e.digest(new)}
    assert tool.read_file('app/service.py').encode() == new


@pytest.mark.parametrize('mutation', ['extra_file', 'public_test', 'B'])
def test_tampered_export_is_rejected(mutation):
    _messages, files = context()
    index = load('export_index.json')['X01']
    if mutation == 'extra_file':
        files['researcher_secret.txt'] = b'sealed information'
    elif mutation == 'public_test':
        files['public_tests.py'] += b'\n# altered\n'
    else:
        files['app/service.py'] += b'\n# altered\n'
    with pytest.raises(e.EnvelopeError):
        e.FileTools(files, expected_public_hashes=index['public_files'], service_path=index['service_path'],
                    expected_b_sha256=e.digest(dummy_service('X01')), family='X01')


@pytest.mark.parametrize('text', ['from x import references_a\ndef run(): pass\n',
    'from x import sealed_tests\ndef run(): pass\n', 'def run(): return r.x01_source()\n',
    'def run(): return x18_install()\n', 'def run(): return r.x22_repair()\n'])
def test_reference_dependencies_not_exportable(text):
    with pytest.raises(e.EnvelopeError):
        e.validate_service(text.encode(), 'X01')


@pytest.mark.parametrize('field', sorted(e.FORBIDDEN_FIELDS | {'source_valid_assumption', 'trust_matrix'}))
def test_constructor_metadata_in_B_is_rejected(field):
    with pytest.raises(e.EnvelopeError):
        e.validate_service(('def run(): return None\n# ' + field).encode(), 'X01')


def test_B_digest_link_mode_and_byte_identity(tmp_path):
    service = tmp_path / 'service.py'
    value = dummy_service('X01')
    service.write_bytes(value)
    assert e.read_admitted_b(service, e.digest(value), 'X01') == value
    with pytest.raises(e.EnvelopeError):
        e.read_admitted_b(service, '0' * 64, 'X01')
    link = tmp_path / 'linked.py'
    link.symlink_to(service)
    with pytest.raises(e.EnvelopeError):
        e.read_admitted_b(link, e.digest(value), 'X01')
    service.chmod(0o755)
    with pytest.raises(e.EnvelopeError):
        e.read_admitted_b(service, e.digest(value), 'X01')


def test_forged_contract_manifest_is_rejected_before_other_reads(tmp_path):
    directory = tmp_path / e.DIRECTORY
    directory.mkdir(parents=True)
    forged = load('contract_manifest.json')
    forged['inventory'] = {}
    (directory / 'contract_manifest.json').write_bytes(e.canonical(forged))
    with pytest.raises(e.EnvelopeError, match='trusted external binding'):
        e.verify_contract(tmp_path, expected_manifest_sha256=manifest_hash())


def test_wrong_scientific_manifest_rejected_before_projection(tmp_path):
    release = tmp_path / e.RELEASE
    release.mkdir(parents=True)
    (release / 'release_manifest.json').write_text('{}')
    with pytest.raises(e.EnvelopeError, match='scientific release manifest'):
        e.generate_contract(tmp_path)


@pytest.mark.parametrize('relative', ['memory_packets.json', 'irrelevant_pairing.json',
    'export_index.json', 'exports/X01/target_request.txt',
    'exports/X01/repository/public_tests.py', 'exports/X01/repository/fixture_api/runtime.py',
    'exports/X01/repository/AGENTS.md'])
def test_bound_inputs_cannot_be_modified_before_context_assembly(tmp_path, monkeypatch, relative):
    directory = tmp_path / e.DIRECTORY
    shutil.copytree(DIRECTORY, directory)
    original_science = e.verify_science
    monkeypatch.setattr(e, 'verify_science', lambda _root: original_science(ROOT))
    # The external manifest binding is unchanged; no altered bytes may render.
    path = directory / relative
    path.write_bytes(path.read_bytes() + b'\nFORBIDDEN_RESEARCHER_SENTINEL\n')
    with pytest.raises(e.EnvelopeError):
        e.load_bound_context(tmp_path, 'X01', 'NO_MEMORY', dummy_service('X01'),
            expected_b_sha256=e.digest(dummy_service('X01')), expected_contract_sha256=manifest_hash())


@pytest.mark.parametrize('family', e.IN_SCOPE)
def test_exported_public_modules_import_without_study_repository(family, tmp_path):
    source = DIRECTORY / f'exports/{family}/repository'
    work = tmp_path / 'export'
    shutil.copytree(source, work)
    module = ('fixture_api.crypto' if family in e.CRYPTO_SYMBOLS else
              'fixture_api.x02_inputs, fixture_api.x02_machine, fixture_api.x02_lowering'
              if family == 'X02' else 'fixture_api.runtime')
    result = subprocess.run([sys.executable, '-B', '-E', '-s', '-c',
                             'import public_tests\nimport ' + module], cwd=work,
                            capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
    assert not result.stdout


@pytest.mark.parametrize('operation,arguments', [('read_file', None), (None, {}),
    ('edit_service', {'path': 'app/service.py', 'old_sha256': 'x', 'replacement': None})])
def test_bad_tool_schema_rejected(operation, arguments):
    with pytest.raises(e.EnvelopeError):
        broker().dispatch(operation, arguments)


@pytest.mark.parametrize('result', [(True, 'PASS', None), ('ADMITTED', 'PASS', None),
    ('PASS', 'SECURITY_PASS', None), ('ERROR', 'ERROR', '/study/sealed/witness.py'),
    ('ERROR', 'ERROR', 'message\nsecret'), ('ERROR', 'ERROR', 'a' * 65)])
def test_feedback_cannot_carry_decisions_paths_or_arbitrary_output(result):
    with pytest.raises(e.EnvelopeError):
        e.public_feedback(*result)


def test_feedback_projection_exact():
    assert e.public_feedback('PASS', 'FAIL') == {'existing': 'PASS', 'feature': 'FAIL', 'error_class': None}


def test_bound_B_parent_symlink_rejected(tmp_path):
    actual = tmp_path / 'actual'
    actual.mkdir()
    (actual / 'service.py').write_bytes(dummy_service('X01'))
    link = tmp_path / 'alias'
    link.symlink_to(actual, target_is_directory=True)
    with pytest.raises(e.EnvelopeError):
        e.read_admitted_b(link / 'service.py', e.digest(dummy_service('X01')), 'X01')
