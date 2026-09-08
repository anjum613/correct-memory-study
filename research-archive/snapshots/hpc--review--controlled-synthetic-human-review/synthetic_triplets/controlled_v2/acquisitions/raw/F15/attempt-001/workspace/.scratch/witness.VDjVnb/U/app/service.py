def notify(account, audit_callback, external_callback=None):
    audit_callback(account)
    if external_callback is not None:
        external_callback(account)
    return True
