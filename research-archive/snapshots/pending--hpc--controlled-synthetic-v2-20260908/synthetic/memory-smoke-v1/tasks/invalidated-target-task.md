Harden the fictional public endpoint's `user_from_request` behavior. Preserve
the user identity forwarded by an attested synthetic gateway, but never trust a
gateway marker supplied by an unattested direct peer. Missing identity remains
anonymous. Edit only `gateway.py`.

This task is an engineering fixture. It is not a real security study task.
