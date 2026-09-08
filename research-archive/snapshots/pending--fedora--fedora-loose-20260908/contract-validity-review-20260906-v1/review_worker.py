"""Trusted offline replay driver; loaded only inside the isolated namespace."""
import importlib
import importlib.util
import json
import os
from pathlib import Path
import resource
import socket
import sys
import traceback

resource.setrlimit(resource.RLIMIT_CPU, (12, 12))
resource.setrlimit(resource.RLIMIT_AS, (1024 * 1024 * 1024, 1024 * 1024 * 1024))
resource.setrlimit(resource.RLIMIT_FSIZE, (16 * 1024 * 1024, 16 * 1024 * 1024))
resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
PREFIX = 'synthetic_triplets.controlled_v3_executable_oracle_release_v1'
ADAPTER = 'synthetic_triplets.controlled_v3_difficulty_amendment_v1'


def load_application():
    spec = importlib.util.spec_from_file_location('v3_candidate_service', '/workspace/app/service.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not callable(module.run):
        raise TypeError('run is not callable')
    return module.run


def simple(value):
    if value is None or type(value) in (str, int, float, bool):
        return value
    if type(value) is bytes:
        return {'type': 'bytes', 'length': len(value), 'nonce_prefix_hex': value[:12].hex()}
    return {'type': type(value).__name__}


def inspect_state(family, args):
    if family == 'X05':
        return {'issued': [simple(v) for v in args[0].issued], 'fail_next': args[0].fail_next}
    if family == 'X28':
        return {'grants': list(args[0].grants), 'exact_reads': args[0].exact_reads,
                'fail_exact': args[0].fail_exact}
    if family == 'X06':
        record, sink = args
        secret = record.get('error') if type(record) is dict else None
        return {'lines': list(sink.lines), 'line_count': len(sink.lines),
                'confidential_output': any('fixture-private' in line for line in sink.lines),
                'secret_representations': getattr(secret, 'representations', None)}
    return {}


def run_candidate(family):
    registry = importlib.import_module(PREFIX + '.candidate_test_registry')
    harness = importlib.import_module(PREFIX + '.harness')
    adapt = importlib.import_module(ADAPTER + '.interface_adapter').adapt_application
    application = adapt(family, load_application())
    existing, feature, focal = registry.checks(family)
    # Match original worker order and application-module lifetime exactly.
    result = {'existing': harness.functional(existing, application),
              'feature': harness.functional(feature, application)}
    observations = []

    def observed(*args, **kwargs):
        item = {'call': len(observations) + 1}
        if family in ('X05', 'X28'):
            item['arguments'] = [simple(a) for a in args[1:]]
        try:
            value = application(*args, **kwargs)
            item['return'] = simple(value)
            return value
        except BaseException as error:
            item['exception'] = type(error).__name__
            item['traceback'] = traceback.format_exc()
            raise
        finally:
            item.update(inspect_state(family, args))
            observations.append(item)

    result['invariant'] = harness.invariant(focal, observed)
    result['observations'] = observations
    return result


def reference_matrix(family):
    catalog = importlib.import_module(PREFIX + '.catalog')
    harness = importlib.import_module(PREFIX + '.harness')
    sealed = importlib.import_module(PREFIX + '.researcher_tests.shared.sealed_suite')
    value = next(f for f in catalog.FAMILIES if f.family_id == family)
    # Canonical references use the original full fixture API. Evaluated/admitted
    # services use the exported API instead; never give these helpers to them.
    sealed.r = importlib.import_module(PREFIX + ('.references_b' if family == 'X28' else '.references_a'))
    # Canonical source checks stay source-specific; target checks use this version.
    value = harness.substitute(value, focal=getattr(sealed, family.lower() + '_target_invariant'))
    return harness.matrix(value)


def observer_checks():
    """Unit checks on observer inputs only; no fabricated candidate programs."""
    suite = importlib.import_module(PREFIX + '.researcher_tests.shared.sealed_suite')
    harness = importlib.import_module(PREFIX + '.harness')
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from synthetic_triplets.controlled_v3_executable_oracle_release_v1.agent_inputs.shared import contracts as k
    nonce = bytes(12)
    packet = nonce + AESGCM(bytes(range(32))).encrypt(nonce, b'ordinary', k.X05_AAD)
    assert suite._x05_packet_nonce(packet, b'ordinary') == nonce
    assert suite._x05_packet_nonce('feature-unavailable', b'ordinary') is None
    try:
        suite._x05_packet_nonce(b'short', b'ordinary')
        raise AssertionError('malformed packet was accepted')
    except harness.ExecutionError:
        pass
    suite._x28_no_authority(False, [], 'test')
    for decision, grants in [(True, []), (False, ['member'])]:
        try:
            suite._x28_no_authority(decision, grants, 'test')
            raise AssertionError('authorization was accepted')
        except harness.InvariantViolation:
            pass
    try:
        suite._x28_no_authority(None, [], 'test')
        raise AssertionError('unspecified result was accepted')
    except harness.ExecutionError:
        pass
    return {'observer_unit_checks': 'PASS', 'checks': 7}


def main():
    mode, family = sys.argv[1:]
    try:
        result = (reference_matrix(family) if mode == 'matrix' else observer_checks()
                  if mode == 'observer' else run_candidate(family))
        result['worker_status'] = 'COMPLETE'
    except BaseException as error:
        result = {'worker_status': 'HARNESS_ERROR', 'error': type(error).__name__,
                  'traceback': traceback.format_exc()}
    result['isolation'] = {'interfaces': socket.if_nameindex(),
        'routes': Path('/proc/net/route').read_text().splitlines(),
        'home_visible': Path('/home/anjum').exists(), 'environment_keys': sorted(os.environ),
        'python': sys.version, 'python_executable': sys.executable}
    print('REVIEW_RESULT=' + json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    main()
