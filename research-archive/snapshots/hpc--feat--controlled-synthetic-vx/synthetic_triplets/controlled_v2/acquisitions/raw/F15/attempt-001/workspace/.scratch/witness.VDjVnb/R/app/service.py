from app.models import PublicAccount


def notify(account, audit_callback, external_callback=None):
    audit_callback(account)
    if external_callback is not None:
        external_callback(PublicAccount(account.account_id, account.name))
    return True
