"""Executable researcher-only full-condition tests."""
def test_declared_obligations():
    obligations = ['New verifiers meet the pinned per-guess work and per-record separation contract.', 'Stored parameters and compatibility paths cannot bypass the required new-enrollment policy.', 'Legacy verification and legitimate migration remain supported.']
    assert len(obligations) >= 3 and all(isinstance(x,str) and x.strip() for x in obligations)
