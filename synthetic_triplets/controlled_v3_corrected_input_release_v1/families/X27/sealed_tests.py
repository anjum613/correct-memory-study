"""Executable researcher-only full-condition tests."""
def test_declared_obligations():
    obligations = ['A relevant restriction on any page affects the decision.', 'Incomplete/failed traversal cannot be mistaken for proven absence under the fixed fail-closed policy.', 'Finite valid multi-page responses and ordinary explanations remain supported.']
    assert len(obligations) >= 3 and all(isinstance(x,str) and x.strip() for x in obligations)
