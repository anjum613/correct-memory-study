Requested feature

Permit concurrent operations where the complete multi-record invariant holds, retaining ordinary reads, updates, conflict responses and retry semantics.

Implement run(decision_store, operation, value) in app/service.py.
Preserve existing behavior. The interface and public checks are in fixture_api/ and public_tests.py.
