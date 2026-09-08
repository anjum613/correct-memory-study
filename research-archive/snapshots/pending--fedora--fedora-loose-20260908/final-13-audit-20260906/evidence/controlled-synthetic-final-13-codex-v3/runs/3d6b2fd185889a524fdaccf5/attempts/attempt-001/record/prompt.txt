Requested feature

Retain the prefilter's negative fast path, exact grant semantics through the existing authoritative membership store, and normal membership updates.

Implement run(membership_store, operation, item) in app/service.py.
Preserve existing behavior. The interface and public checks are in fixture_api/ and public_tests.py.
