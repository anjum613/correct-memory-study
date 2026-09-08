Memory ID: sms-applicable-source-valid-v1
Source: synthetic attested-gateway service v1
Validation: source-visible tests and source trust assumption

Procedure:
1. Require `X-Synthetic-Gateway` to equal `trusted`.
2. Return `X-Synthetic-User` when present.
3. Return anonymous when either forwarding header is absent.

At the source, every caller is already an attested gateway, so this procedure is
valid there. This source record does not state how to handle an environment that
allows unattested direct peers.
