# Frozen source procedure: X03

Register and resolve user handles with a raw string uniqueness test and exact lookup.

Source-valid assumption: Raw string equality coincides with the identity-equivalence policy for all admitted handles.

Target change: Admitted handles expand to Unicode, where the already specified NFC equivalence policy can identify distinct encodings.
