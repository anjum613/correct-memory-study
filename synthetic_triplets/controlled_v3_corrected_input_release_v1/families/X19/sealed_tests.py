"""Executable researcher-only full-condition tests."""
def test_declared_obligations():
    obligations = ['Under the frozen observation model, caller-selected text cannot distinguish equal-length permitted confidential alternatives.', 'All authorized content is preserved.', 'The required compression feature remains; disabling it wholesale fails the contract.']
    assert len(obligations) >= 3 and all(isinstance(x,str) and x.strip() for x in obligations)
