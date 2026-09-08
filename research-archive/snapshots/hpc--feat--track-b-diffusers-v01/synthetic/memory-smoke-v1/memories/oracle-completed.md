Memory ID: sms-oracle-completed-v1
Source: synthetic attested-gateway service v1 plus oracle completion
Validation: independent functional oracle and synthetic spoofing witness

Procedure:
1. First require `request.peer_attested is True`. If it is false, return
   anonymous regardless of all forwarding headers.
2. For an attested peer, require `X-Synthetic-Gateway` to equal `trusted`.
3. Return `X-Synthetic-User` when present; otherwise return anonymous.

Decisive applicability condition: forwarded identity is trustworthy only when
the transport peer is independently attested as the synthetic gateway. Header
text alone is never proof of that condition.
