def notify(account, audit_callback, external_callback=None):
    if external_callback is not None:
        raise NotImplementedError("external callbacks are not implemented")
    audit_callback(account)
    return True
