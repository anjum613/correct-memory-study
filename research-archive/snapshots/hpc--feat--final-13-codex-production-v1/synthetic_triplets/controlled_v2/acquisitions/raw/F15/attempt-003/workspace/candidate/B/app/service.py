def notify(account, audit_callback):
    audit_callback(account)
    return True
