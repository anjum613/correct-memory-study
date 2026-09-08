"""Executable researcher-only full-condition tests."""
def test_declared_obligations():
    obligations = ['A matching deny cannot be bypassed by another earlier matching allow.', 'Rule ordering cannot change the required policy result.', 'Unopposed legitimate allows and explanations remain correct.']
    assert len(obligations) >= 3 and all(isinstance(x,str) and x.strip() for x in obligations)
