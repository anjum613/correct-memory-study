Requested feature

Allow all workers to encrypt and decrypt with the same fixed key and wire format, retaining restart recovery and a defined exhaustion response.

Implement run(system, worker, payload_bytes) in app/service.py.
Preserve existing behavior. The interface and public checks are in fixture_api/ and public_tests.py.
