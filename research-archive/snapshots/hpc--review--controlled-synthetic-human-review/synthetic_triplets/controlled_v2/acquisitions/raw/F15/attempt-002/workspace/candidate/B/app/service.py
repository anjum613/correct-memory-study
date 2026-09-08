def notify(account, audit_callback, external_callback=None):
    audit_callback(account)
    return True
