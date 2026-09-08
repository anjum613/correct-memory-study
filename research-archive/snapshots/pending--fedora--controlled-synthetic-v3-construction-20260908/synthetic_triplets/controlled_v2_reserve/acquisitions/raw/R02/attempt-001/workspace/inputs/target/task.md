Extend `receive_event` with keyword-only `external` and `signature` arguments.
Internal calls keep their current behaviour. External calls should process valid
signed bodies through the same handler and return its existing receipt type.
